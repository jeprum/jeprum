"""Jeprum — Transport layer for shipping agent events.

Supports local JSONL file logging, cloud API shipping, or both.
Key principle: transport must NEVER block the agent or raise exceptions
that crash the agent. It's fire-and-forget.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from jeprum.exceptions import TransportError
from jeprum.models import AgentEvent

if TYPE_CHECKING:
    from jeprum.models import AgentConfig

logger = logging.getLogger("jeprum.transport")


class LocalTransport:
    """Ships events to a local JSONL file.

    Each event is appended as a single JSON line. File writes use
    asyncio.to_thread to avoid blocking the event loop.
    """

    def __init__(self, file_path: str = "jeprum_events.jsonl") -> None:
        self._file_path = Path(file_path)
        self._file_path.parent.mkdir(parents=True, exist_ok=True)

    async def ship(self, event: AgentEvent) -> None:
        """Append a single event as a JSON line to the log file."""
        try:
            line = event.to_log_line() + "\n"
            await asyncio.to_thread(self._write_sync, line)
        except Exception as exc:
            logger.warning("LocalTransport failed to write event: %s", exc)

    async def ship_batch(self, events: list[AgentEvent]) -> None:
        """Ship multiple events at once."""
        try:
            lines = "".join(e.to_log_line() + "\n" for e in events)
            await asyncio.to_thread(self._write_sync, lines)
        except Exception as exc:
            logger.warning("LocalTransport failed to write batch: %s", exc)

    def _write_sync(self, data: str) -> None:
        """Synchronous file write, called via asyncio.to_thread."""
        with open(self._file_path, "a", encoding="utf-8") as f:
            f.write(data)

    async def close(self) -> None:
        """No-op for local transport — file handles are opened/closed per write."""


class CloudTransport:
    """Ships events to the Jeprum cloud API in batches.

    Events are queued in memory and flushed periodically or when the
    queue reaches batch_size. HTTP failures are logged but never raised.
    Also polls the cloud for agent status (kill/pause) on a configurable interval.
    """

    def __init__(
        self,
        endpoint: str,
        api_key: str,
        batch_size: int = 10,
        batch_interval: float = 2.0,
        agent_id: str = "",
        poll_interval: float = 10.0,
    ) -> None:
        self._endpoint = endpoint.rstrip("/")
        self._api_key = api_key
        self._batch_size = batch_size
        self._batch_interval = batch_interval
        self._agent_id = agent_id
        self._poll_interval = poll_interval
        self._queue: asyncio.Queue[AgentEvent] = asyncio.Queue()
        self._client: httpx.AsyncClient | None = None
        self._flush_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._closed = False
        self._remote_status: str = "active"

    @property
    def remote_status(self) -> str:
        """The latest status polled from the cloud (active/paused/killed)."""
        return self._remote_status

    async def _ensure_started(self) -> None:
        """Lazily start the HTTP client, flush task, and poll task."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
            )
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_loop())
        if self._poll_task is None and self._agent_id:
            self._poll_task = asyncio.create_task(self._poll_status_loop())

    async def ship(self, event: AgentEvent) -> None:
        """Add an event to the internal queue for batched shipping."""
        try:
            await self._ensure_started()
            self._queue.put_nowait(event)
        except Exception as exc:
            logger.warning("CloudTransport failed to queue event: %s", exc)

    async def ship_batch(self, events: list[AgentEvent]) -> None:
        """Add multiple events to the queue."""
        for event in events:
            await self.ship(event)

    async def _flush_loop(self) -> None:
        """Background task that flushes the queue periodically."""
        while not self._closed:
            try:
                await asyncio.sleep(self._batch_interval)
                await self._flush()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("CloudTransport flush loop error: %s", exc)

    async def _flush(self) -> None:
        """Drain the queue and send events to the cloud API."""
        events: list[AgentEvent] = []
        while not self._queue.empty() and len(events) < self._batch_size:
            try:
                events.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        if not events:
            return

        try:
            payload = {"events": [e.model_dump(mode="json") for e in events]}
            if self._client is not None:
                response = await self._client.post(
                    f"{self._endpoint}/api/v1/events",
                    json=payload,
                )
                if response.status_code >= 400:
                    logger.warning(
                        "CloudTransport API error %d: %s",
                        response.status_code,
                        response.text[:200],
                    )
                    # Re-queue events for retry
                    for event in events:
                        self._queue.put_nowait(event)
        except Exception as exc:
            logger.warning("CloudTransport HTTP error: %s", exc)
            # Re-queue events for retry
            for event in events:
                try:
                    self._queue.put_nowait(event)
                except Exception:
                    pass

    async def _poll_status_loop(self) -> None:
        """Background task that polls the cloud for agent status."""
        while not self._closed:
            try:
                await asyncio.sleep(self._poll_interval)
                await self._poll_status()
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("CloudTransport poll error: %s", exc)

    async def _poll_status(self) -> None:
        """Poll agent status from the cloud API. Fail-open on errors."""
        if self._client is None or not self._agent_id:
            return
        try:
            response = await self._client.get(
                f"{self._endpoint}/api/v1/agents/{self._agent_id}/status",
            )
            if response.status_code == 200:
                data = response.json()
                new_status = data.get("status", "active")
                if new_status != self._remote_status:
                    logger.info(
                        "Agent '%s' remote status changed: %s -> %s",
                        self._agent_id, self._remote_status, new_status,
                    )
                    self._remote_status = new_status
        except Exception as exc:
            logger.warning("Failed to poll agent status: %s", exc)

    async def close(self) -> None:
        """Flush remaining events and shut down."""
        self._closed = True
        for task in (self._flush_task, self._poll_task):
            if task is not None:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        # Final flush
        await self._flush()
        if self._client is not None:
            await self._client.aclose()


class ComboTransport:
    """Ships events to both local file and cloud API simultaneously.

    If cloud fails, local still works.
    """

    def __init__(self, local: LocalTransport, cloud: CloudTransport) -> None:
        self._local = local
        self._cloud = cloud

    @property
    def remote_status(self) -> str:
        """Proxy remote_status from the cloud transport."""
        return self._cloud.remote_status

    async def ship(self, event: AgentEvent) -> None:
        """Ship to both transports. Failures in one don't affect the other."""
        await asyncio.gather(
            self._local.ship(event),
            self._cloud.ship(event),
            return_exceptions=True,
        )

    async def ship_batch(self, events: list[AgentEvent]) -> None:
        """Ship batch to both transports."""
        await asyncio.gather(
            self._local.ship_batch(events),
            self._cloud.ship_batch(events),
            return_exceptions=True,
        )

    async def close(self) -> None:
        """Close both transports."""
        await asyncio.gather(
            self._local.close(),
            self._cloud.close(),
            return_exceptions=True,
        )


def create_transport(
    config: AgentConfig,
) -> LocalTransport | CloudTransport | ComboTransport:
    """Factory function — returns the right transport based on config.transport_mode."""
    if config.transport_mode == "local":
        return LocalTransport(file_path=config.local_log_path)

    if config.transport_mode == "cloud":
        if not config.api_key:
            logger.warning(
                "Cloud transport requested but no api_key provided. Falling back to local."
            )
            return LocalTransport(file_path=config.local_log_path)
        return CloudTransport(
            endpoint=config.cloud_endpoint,
            api_key=config.api_key,
            batch_size=config.batch_size,
            batch_interval=config.batch_interval_seconds,
            agent_id=config.agent_id,
            poll_interval=config.poll_interval_seconds,
        )

    if config.transport_mode == "both":
        local = LocalTransport(file_path=config.local_log_path)
        if not config.api_key:
            logger.warning(
                "Combo transport requested but no api_key provided. Using local only."
            )
            return local
        cloud = CloudTransport(
            endpoint=config.cloud_endpoint,
            api_key=config.api_key,
            batch_size=config.batch_size,
            batch_interval=config.batch_interval_seconds,
            agent_id=config.agent_id,
            poll_interval=config.poll_interval_seconds,
        )
        return ComboTransport(local=local, cloud=cloud)

    return LocalTransport(file_path=config.local_log_path)
