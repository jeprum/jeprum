"""Jeprum — MCP tool call interceptor.

Wraps an MCP ClientSession (or any object with a call_tool method) and
intercepts every tool invocation to provide monitoring, guardrails, and
telemetry shipping.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any

from jeprum.exceptions import AgentKilled, AgentPaused, GuardrailViolation
from jeprum.models import AgentConfig, AgentEvent, AgentStatus
from jeprum.rules import RuleEngine
from jeprum.transport import CloudTransport, ComboTransport, LocalTransport, create_transport

logger = logging.getLogger("jeprum.interceptor")


class JeprumInterceptor:
    """Wraps an MCP ClientSession to intercept every call_tool invocation.

    Provides:
    - Real-time event logging (async, non-blocking)
    - Guardrail enforcement (synchronous, before execution)
    - Kill/pause switch
    - Duration and cost tracking
    """

    def __init__(
        self,
        session: Any,
        config: AgentConfig,
    ) -> None:
        self._session = session
        self._config = config
        self._rule_engine = RuleEngine(rules=config.rules)
        self._transport = create_transport(config)
        self._status = AgentStatus(
            agent_id=config.agent_id,
            status="active",
        )
        self._enabled = config.enabled

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
    ) -> Any:
        """Intercept a tool call: check guardrails, execute, log, ship telemetry.

        This is the core method — a drop-in replacement for session.call_tool().

        Raises:
            AgentKilled: If the agent has been killed.
            AgentPaused: If the agent has been paused.
            GuardrailViolation: If a guardrail rule blocks the call.
        """
        if not self._enabled:
            return await self._session.call_tool(name, arguments)

        # 1. Sync remote status + rules from cloud
        self._sync_remote_status()
        self._sync_remote_rules()
        if self._status.status == "killed":
            raise AgentKilled(self._config.agent_id)
        if self._status.status == "paused":
            raise AgentPaused(self._config.agent_id)

        # 2. Create event
        event = AgentEvent(
            agent_id=self._config.agent_id,
            agent_name=self._config.agent_name,
            event_type="tool_call",
            tool_name=name,
            input_params=arguments or {},
        )

        # 3. Evaluate guardrails (synchronous — must happen before call)
        eval_result = self._rule_engine.evaluate(event)

        if eval_result.action in ("block", "kill"):
            event.guardrail_check = "blocked"
            event.guardrail_details = eval_result.reason
            event.event_type = "guardrail_trigger"
            await self._ship_event(event)
            if eval_result.action == "kill":
                self._status.status = "killed"
            raise GuardrailViolation(
                reason=eval_result.reason or "Blocked by guardrail",
                rule_name=eval_result.rule_name,
                event=event,
            )

        if eval_result.action in ("warn", "alert"):
            event.guardrail_check = "warned"
            event.guardrail_details = eval_result.reason

        # 4. Execute the actual tool call
        start = time.monotonic()
        try:
            response = await self._session.call_tool(name, arguments)
            event.duration_ms = (time.monotonic() - start) * 1000
            event.output_result = self._safe_serialize(response)
            if event.guardrail_check == "skipped":
                event.guardrail_check = "passed"
        except Exception as exc:
            event.duration_ms = (time.monotonic() - start) * 1000
            event.event_type = "error"
            event.output_result = {"error": type(exc).__name__, "message": str(exc)}
            await self._ship_event(event)
            self._rule_engine.record_event(event)
            self._update_status(event)
            raise

        # 5. Record and ship (async, non-blocking)
        self._rule_engine.record_event(event)
        self._update_status(event)
        await self._ship_event(event)

        return response

    async def list_tools(self) -> Any:
        """Pass-through to the original session's list_tools(). No interception."""
        return await self._session.list_tools()

    async def kill(self) -> None:
        """Kill the agent. All subsequent call_tool calls will raise AgentKilled."""
        self._status.status = "killed"
        logger.info("Agent '%s' killed", self._config.agent_id)

    async def pause(self) -> None:
        """Pause the agent. All subsequent call_tool calls will raise AgentPaused."""
        self._status.status = "paused"
        logger.info("Agent '%s' paused", self._config.agent_id)

    async def resume(self) -> None:
        """Resume a paused agent."""
        self._status.status = "active"
        logger.info("Agent '%s' resumed", self._config.agent_id)

    async def close(self) -> None:
        """Flush transport and clean up."""
        await self._transport.close()

    @property
    def status(self) -> AgentStatus:
        """Return current agent status with cumulative stats."""
        return self._status.model_copy()

    def _update_status(self, event: AgentEvent) -> None:
        """Update running status counters."""
        self._status.total_events_today += 1
        self._status.total_cost_today_usd += event.estimated_cost_usd or 0.0
        self._status.last_event_at = event.timestamp

    async def _ship_event(self, event: AgentEvent) -> None:
        """Ship an event via transport. Failures are logged, never raised."""
        try:
            await self._transport.ship(event)
        except Exception as exc:
            logger.warning("Failed to ship event: %s", exc)

    def _sync_remote_status(self) -> None:
        """Check remote status from cloud transport and update local status."""
        if isinstance(self._transport, (CloudTransport, ComboTransport)):
            remote = self._transport.remote_status
            if remote in ("killed", "paused") and self._status.status == "active":
                self._status.status = remote
                logger.info(
                    "Agent '%s' status synced from cloud: %s",
                    self._config.agent_id,
                    remote,
                )

    def _sync_remote_rules(self) -> None:
        """Sync remote rules from cloud transport into the rule engine."""
        if isinstance(self._transport, (CloudTransport, ComboTransport)):
            transport = (
                self._transport._cloud
                if isinstance(self._transport, ComboTransport)
                else self._transport
            )
            remote = transport.remote_rules
            if remote:
                self._rule_engine.set_remote_rules(remote)

    @staticmethod
    def _safe_serialize(obj: Any) -> Any:
        """Best-effort serialization of tool call responses."""
        if obj is None:
            return None
        if isinstance(obj, (str, int, float, bool)):
            return obj
        if isinstance(obj, dict):
            return obj
        if isinstance(obj, (list, tuple)):
            return list(obj)
        # For MCP response objects, try to extract content
        if hasattr(obj, "content"):
            return {"content": str(obj.content)}
        if hasattr(obj, "model_dump"):
            return obj.model_dump()
        return str(obj)
