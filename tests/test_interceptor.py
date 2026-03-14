"""Tests for Jeprum MCP interceptor."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from jeprum.exceptions import AgentKilled, AgentPaused, GuardrailViolation
from jeprum.interceptor import JeprumInterceptor
from jeprum.models import AgentConfig, AgentEvent, Rule


# ---------------------------------------------------------------------------
# Mock MCP Session
# ---------------------------------------------------------------------------

class MockMCPSession:
    """Simulates an MCP ClientSession for testing."""

    def __init__(
        self,
        responses: dict[str, Any] | None = None,
        errors: dict[str, Exception] | None = None,
    ) -> None:
        self.responses = responses or {}
        self.errors = errors or {}
        self.calls: list[tuple[str, dict[str, Any] | None]] = []

    async def call_tool(
        self, name: str, arguments: dict[str, Any] | None = None
    ) -> Any:
        self.calls.append((name, arguments))
        if name in self.errors:
            raise self.errors[name]
        return self.responses.get(name, {"status": "ok", "tool": name})

    async def list_tools(self) -> list[dict[str, str]]:
        return [{"name": "search"}, {"name": "calculator"}]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_config(
    tmp_path: Path,
    rules: list[Rule] | None = None,
    agent_id: str = "test-agent",
) -> AgentConfig:
    """Build an AgentConfig that logs to a temp JSONL file."""
    return AgentConfig(
        agent_id=agent_id,
        agent_name="Test Agent",
        rules=rules or [],
        transport_mode="local",
        local_log_path=str(tmp_path / "events.jsonl"),
    )


def read_events(tmp_path: Path) -> list[dict[str, Any]]:
    """Read events from the JSONL log file."""
    log_file = tmp_path / "events.jsonl"
    if not log_file.exists():
        return []
    lines = log_file.read_text().strip().split("\n")
    return [json.loads(line) for line in lines if line.strip()]


# ---------------------------------------------------------------------------
# Tests: Basic interception
# ---------------------------------------------------------------------------

class TestBasicInterception:
    @pytest.mark.asyncio
    async def test_call_goes_through(self, tmp_path: Path) -> None:
        session = MockMCPSession(responses={"search": {"results": ["a", "b"]}})
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        result = await interceptor.call_tool("search", {"query": "test"})
        await interceptor.close()

        assert result == {"results": ["a", "b"]}
        assert len(session.calls) == 1
        assert session.calls[0] == ("search", {"query": "test"})

    @pytest.mark.asyncio
    async def test_event_logged_to_file(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.call_tool("search", {"query": "test"})
        await interceptor.close()

        events = read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["tool_name"] == "search"
        assert events[0]["agent_id"] == "test-agent"
        assert events[0]["event_type"] == "tool_call"
        assert events[0]["guardrail_check"] == "passed"

    @pytest.mark.asyncio
    async def test_correct_fields_set(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.call_tool("calc", {"expression": "1+1"})
        await interceptor.close()

        events = read_events(tmp_path)
        event = events[0]
        assert event["input_params"] == {"expression": "1+1"}
        assert event["output_result"] is not None
        assert event["agent_name"] == "Test Agent"

    @pytest.mark.asyncio
    async def test_list_tools_passthrough(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        tools = await interceptor.list_tools()
        await interceptor.close()

        assert len(tools) == 2
        assert tools[0]["name"] == "search"


# ---------------------------------------------------------------------------
# Tests: Guardrail blocks
# ---------------------------------------------------------------------------

class TestGuardrailBlocks:
    @pytest.mark.asyncio
    async def test_blocked_tool_raises(self, tmp_path: Path) -> None:
        rules = [
            Rule(
                name="no_delete",
                rule_type="blocked_tool",
                config={"patterns": ["delete_*"]},
                action="block",
            )
        ]
        session = MockMCPSession()
        config = make_config(tmp_path, rules=rules)
        interceptor = JeprumInterceptor(session=session, config=config)

        with pytest.raises(GuardrailViolation) as exc_info:
            await interceptor.call_tool("delete_file", {"path": "/etc/passwd"})
        await interceptor.close()

        assert exc_info.value.rule_name == "no_delete"
        assert len(session.calls) == 0  # Tool was NOT called

        events = read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["guardrail_check"] == "blocked"
        assert events[0]["event_type"] == "guardrail_trigger"

    @pytest.mark.asyncio
    async def test_allowed_tool_passes(self, tmp_path: Path) -> None:
        rules = [
            Rule(
                name="no_delete",
                rule_type="blocked_tool",
                config={"patterns": ["delete_*"]},
                action="block",
            )
        ]
        session = MockMCPSession()
        config = make_config(tmp_path, rules=rules)
        interceptor = JeprumInterceptor(session=session, config=config)

        result = await interceptor.call_tool("read_file", {"path": "/tmp/test"})
        await interceptor.close()

        assert result is not None
        assert len(session.calls) == 1


# ---------------------------------------------------------------------------
# Tests: Spending limit
# ---------------------------------------------------------------------------

class TestSpendingLimit:
    @pytest.mark.asyncio
    async def test_spend_limit_blocks_when_exceeded(self, tmp_path: Path) -> None:
        rules = [
            Rule(
                name="spend_cap",
                rule_type="max_spend",
                config={"max_usd": 0.05},
                action="block",
            )
        ]
        session = MockMCPSession()
        config = make_config(tmp_path, rules=rules)
        interceptor = JeprumInterceptor(session=session, config=config)

        # Make calls with cost until blocked
        # We need the event to have cost info. The interceptor uses event.estimated_cost_usd.
        # Since cost comes from the event itself, and the interceptor creates events
        # without cost by default, we need to verify the rule engine tracks it.
        # For this test, we'll manually set cost on events via the rule engine.
        for i in range(5):
            event = AgentEvent(
                agent_id="test-agent",
                tool_name="search",
                estimated_cost_usd=0.01,
            )
            interceptor._rule_engine.record_event(event)

        # Now the next call should be blocked (spent $0.05, limit is $0.05)
        # Event with $0.01 cost would bring total to $0.06
        blocked_event = AgentEvent(
            agent_id="test-agent",
            tool_name="search",
            estimated_cost_usd=0.01,
        )
        result = interceptor._rule_engine.evaluate(blocked_event)
        assert result.action == "block"

        await interceptor.close()


# ---------------------------------------------------------------------------
# Tests: Kill switch
# ---------------------------------------------------------------------------

class TestKillSwitch:
    @pytest.mark.asyncio
    async def test_kill_raises_on_next_call(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.kill()

        with pytest.raises(AgentKilled):
            await interceptor.call_tool("search", {"query": "test"})
        await interceptor.close()

    @pytest.mark.asyncio
    async def test_kill_status_is_killed(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.kill()
        assert interceptor.status.status == "killed"
        await interceptor.close()


# ---------------------------------------------------------------------------
# Tests: Pause/Resume
# ---------------------------------------------------------------------------

class TestPauseResume:
    @pytest.mark.asyncio
    async def test_pause_raises_on_call(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.pause()

        with pytest.raises(AgentPaused):
            await interceptor.call_tool("search", {"query": "test"})
        await interceptor.close()

    @pytest.mark.asyncio
    async def test_resume_after_pause(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.pause()

        with pytest.raises(AgentPaused):
            await interceptor.call_tool("search")

        await interceptor.resume()

        result = await interceptor.call_tool("search", {"query": "test"})
        assert result is not None
        await interceptor.close()


# ---------------------------------------------------------------------------
# Tests: Error handling
# ---------------------------------------------------------------------------

class TestErrorHandling:
    @pytest.mark.asyncio
    async def test_session_error_still_logged(self, tmp_path: Path) -> None:
        session = MockMCPSession(errors={"bad_tool": RuntimeError("Tool failed")})
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        with pytest.raises(RuntimeError, match="Tool failed"):
            await interceptor.call_tool("bad_tool", {})
        await interceptor.close()

        events = read_events(tmp_path)
        assert len(events) == 1
        assert events[0]["event_type"] == "error"
        assert events[0]["output_result"]["error"] == "RuntimeError"
        assert events[0]["output_result"]["message"] == "Tool failed"


# ---------------------------------------------------------------------------
# Tests: Duration tracking
# ---------------------------------------------------------------------------

class TestDurationTracking:
    @pytest.mark.asyncio
    async def test_duration_is_set(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.call_tool("search", {"query": "test"})
        await interceptor.close()

        events = read_events(tmp_path)
        assert events[0]["duration_ms"] is not None
        assert events[0]["duration_ms"] >= 0


# ---------------------------------------------------------------------------
# Tests: Status tracking
# ---------------------------------------------------------------------------

class TestStatusTracking:
    @pytest.mark.asyncio
    async def test_event_count_increments(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        interceptor = JeprumInterceptor(session=session, config=config)

        await interceptor.call_tool("search")
        await interceptor.call_tool("calc")
        await interceptor.close()

        assert interceptor.status.total_events_today == 2

    @pytest.mark.asyncio
    async def test_disabled_interceptor_passthrough(self, tmp_path: Path) -> None:
        session = MockMCPSession()
        config = make_config(tmp_path)
        config.enabled = False
        interceptor = JeprumInterceptor(session=session, config=config)

        result = await interceptor.call_tool("search")
        await interceptor.close()

        assert result is not None
        assert len(session.calls) == 1
        # No events logged when disabled
        events = read_events(tmp_path)
        assert len(events) == 0
