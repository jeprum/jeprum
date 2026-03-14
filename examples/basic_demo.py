"""Jeprum SDK Demo — End-to-end demonstration of monitoring, guardrails, and kill switch.

Run with: uv run python examples/basic_demo.py

This demo uses a mock MCP session to simulate real agent tool calls,
showing how Jeprum intercepts, monitors, and governs every action.
"""

from __future__ import annotations

import asyncio
import random
import sys
from pathlib import Path
from typing import Any

from jeprum import Jeprum, GuardrailViolation, AgentKilled

# ---------------------------------------------------------------------------
# ANSI color codes (no extra dependency needed)
# ---------------------------------------------------------------------------
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


# ---------------------------------------------------------------------------
# Mock MCP Session — simulates a real MCP server with tools
# ---------------------------------------------------------------------------

TOOL_COSTS: dict[str, float] = {
    "web_search": 0.012,
    "calculator": 0.005,
    "read_file": 0.008,
    "send_email": 0.020,
    "delete_file": 0.010,
    "get_weather": 0.007,
    "translate_text": 0.015,
    "summarize": 0.025,
}


class MockMCPSession:
    """Simulates an MCP ClientSession with mock tools and realistic latency."""

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        # Simulate realistic API latency (50-200ms)
        await asyncio.sleep(random.uniform(0.05, 0.20))

        responses: dict[str, dict[str, Any]] = {
            "web_search": {"results": [f"Result for '{arguments.get('query', '')}'"], "count": 3},
            "calculator": {"result": eval(str(arguments.get("expression", "0")))},
            "read_file": {"content": f"Contents of {arguments.get('path', 'unknown')}", "size": 1024},
            "send_email": {"status": "sent", "to": arguments.get("to", ""), "id": "msg_abc123"},
            "delete_file": {"status": "deleted", "path": arguments.get("path", "")},
            "get_weather": {"temp": 72, "condition": "sunny", "city": arguments.get("city", "")},
            "translate_text": {"translated": f"[translated] {arguments.get('text', '')}", "lang": arguments.get("to_lang", "")},
            "summarize": {"summary": f"Summary of: {str(arguments.get('text', ''))[:50]}...", "tokens": 150},
        }
        return responses.get(name, {"status": "ok", "tool": name})

    async def list_tools(self) -> list[dict[str, str]]:
        return [{"name": name} for name in TOOL_COSTS]


# ---------------------------------------------------------------------------
# Demo script
# ---------------------------------------------------------------------------

DEMO_CALLS: list[tuple[str, dict[str, Any]]] = [
    # Phase 1: Normal operations (green — passed)
    ("web_search", {"query": "latest AI agent frameworks 2026"}),
    ("calculator", {"expression": "42 * 17 + 3"}),
    ("get_weather", {"city": "New York"}),
    ("web_search", {"query": "MCP protocol specification"}),
    ("read_file", {"path": "/tmp/config.yaml"}),
    # Phase 2: Dangerous operation blocked by tool restriction (red)
    ("delete_file", {"path": "/etc/important.conf"}),
    # Phase 3: More normal + alert triggers (yellow + green)
    ("calculator", {"expression": "100 / 7"}),
    ("translate_text", {"text": "Hello world", "to_lang": "es"}),
    ("send_email", {"to": "team@example.com", "subject": "Agent report"}),
    ("web_search", {"query": "Python async best practices"}),
    ("summarize", {"text": "A long document about AI safety and governance..."}),
    ("get_weather", {"city": "San Francisco"}),
    # Phase 4: Hit the spending limit (red — budget exceeded)
    ("web_search", {"query": "agent monitoring tools"}),
    ("summarize", {"text": "Another document about MCP interceptors..."}),
    ("translate_text", {"text": "Goodbye", "to_lang": "fr"}),
    ("web_search", {"query": "how to build an SDK"}),
    ("send_email", {"to": "boss@example.com", "subject": "Budget alert"}),
    ("summarize", {"text": "Yet another long document for analysis..."}),
    ("web_search", {"query": "real-time dashboards with React"}),
    ("calculator", {"expression": "999 * 999"}),
]


def print_header() -> None:
    print()
    print(f"{BOLD}{CYAN}{'=' * 70}{RESET}")
    print(f"{BOLD}{CYAN}  JEPRUM SDK DEMO — Live Agent Monitoring & Guardrails{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 70}{RESET}")
    print()
    print(f"{DIM}  Rules configured:{RESET}")
    print(f"{DIM}    • Max spend per day: $0.10 (intentionally low for demo){RESET}")
    print(f"{DIM}    • Blocked tools: delete_* (dangerous operations){RESET}")
    print(f"{DIM}    • Alert on: send_* (flag sensitive actions){RESET}")
    print()
    print(f"{BOLD}  Running {len(DEMO_CALLS)} agent tool calls...{RESET}")
    print(f"{DIM}  {'─' * 66}{RESET}")
    print()


def print_event(
    index: int,
    tool_name: str,
    status: str,
    cost: float,
    duration_ms: float,
    detail: str = "",
) -> None:
    status_colors = {
        "PASSED": GREEN,
        "WARNED": YELLOW,
        "BLOCKED": RED,
    }
    color = status_colors.get(status, RESET)
    cost_str = f"${cost:.3f}" if cost > 0 else "  —  "
    dur_str = f"{duration_ms:6.1f}ms"
    idx_str = f"[{index + 1:2d}/{len(DEMO_CALLS)}]"

    print(f"  {idx_str}  {color}{status:7s}{RESET}  {tool_name:20s}  {cost_str:>7s}  {dur_str}", end="")
    if detail:
        print(f"  {DIM}{detail}{RESET}", end="")
    print()


def print_summary(passed: int, warned: int, blocked: int, total_cost: float, log_path: str) -> None:
    print()
    print(f"{DIM}  {'─' * 66}{RESET}")
    print()
    print(f"{BOLD}  SUMMARY{RESET}")
    print(f"  ├── Total calls attempted: {passed + warned + blocked}")
    print(f"  ├── {GREEN}Passed:{RESET}  {passed}")
    print(f"  ├── {YELLOW}Warned:{RESET}  {warned}")
    print(f"  ├── {RED}Blocked:{RESET} {blocked}")
    print(f"  └── Total cost: ${total_cost:.4f}")
    print()
    print(f"{BOLD}  EVENT LOG{RESET}")
    print(f"  └── {log_path}")
    print()
    print(f"{DIM}  Inspect with:{RESET}")
    print(f"  cat {log_path} | python -m json.tool --json-lines | head -80")
    print()
    print(f"{BOLD}{CYAN}{'=' * 70}{RESET}")
    print()


class CostAwareMCPSession:
    """Wraps MockMCPSession and injects estimated_cost_usd into the interceptor's
    rule engine before each call, simulating cost-aware tool execution."""

    def __init__(self, mock: MockMCPSession, interceptor: Any) -> None:
        self._mock = mock
        self._interceptor = interceptor

    def pre_record_cost(self, tool_name: str) -> None:
        """Record anticipated cost in the rule engine so spend limits work."""
        cost = TOOL_COSTS.get(tool_name, 0.01)
        from jeprum.models import AgentEvent as AE
        evt = AE(
            agent_id=self._interceptor._config.agent_id,
            tool_name=tool_name,
            estimated_cost_usd=cost,
        )
        # Only evaluate — don't record yet. We record after success.
        result = self._interceptor._rule_engine.evaluate(evt)
        return result, cost

    def record_cost(self, tool_name: str, cost: float) -> None:
        from jeprum.models import AgentEvent as AE
        evt = AE(
            agent_id=self._interceptor._config.agent_id,
            tool_name=tool_name,
            estimated_cost_usd=cost,
        )
        self._interceptor._rule_engine.record_event(evt)


async def run_demo() -> None:
    log_path = "jeprum_demo_events.jsonl"

    # Clean up previous demo log
    Path(log_path).unlink(missing_ok=True)

    # Create Jeprum instance with local transport
    jp = Jeprum(transport_mode="local", log_path=log_path)

    # Create mock MCP session
    session = MockMCPSession()

    # Monitor the session with guardrails
    agent = jp.monitor(
        session,
        agent_name="Demo Agent",
        rules={
            "max_spend_per_day": 0.10,
            "blocked_tools": ["delete_*"],
            "alert_on": ["send_*"],
        },
    )

    cost_helper = CostAwareMCPSession(session, agent)

    print_header()

    passed = 0
    warned = 0
    blocked = 0
    total_cost = 0.0

    for i, (tool_name, args) in enumerate(DEMO_CALLS):
        cost = TOOL_COSTS.get(tool_name, 0.01)

        # Pre-check spending limit before making the call
        from jeprum.models import AgentEvent
        cost_check_event = AgentEvent(
            agent_id=agent._config.agent_id,
            tool_name=tool_name,
            estimated_cost_usd=cost,
        )
        spend_result = agent._rule_engine.evaluate(cost_check_event)

        if spend_result.action in ("block", "kill"):
            blocked += 1
            print_event(i, tool_name, "BLOCKED", 0, 0.0, spend_result.reason or "Budget exceeded")
            continue

        try:
            result = await agent.call_tool(tool_name, args)

            # Record cost after successful call
            cost_helper.record_cost(tool_name, cost)
            total_cost += cost

            # Check if it was an alerted tool
            alert_check = AgentEvent(
                agent_id=agent._config.agent_id,
                tool_name=tool_name,
            )
            alert_result = agent._rule_engine.evaluate(alert_check)

            if alert_result.action == "alert":
                warned += 1
                duration = random.uniform(50, 200)
                print_event(i, tool_name, "WARNED", cost, duration, alert_result.reason or "")
            else:
                passed += 1
                duration = random.uniform(50, 200)
                print_event(i, tool_name, "PASSED", cost, duration)

        except GuardrailViolation as exc:
            blocked += 1
            print_event(i, tool_name, "BLOCKED", 0, 0.0, exc.reason)

        except AgentKilled:
            blocked += 1
            print_event(i, tool_name, "BLOCKED", 0, 0.0, "Agent killed")
            break

    await agent.close()
    await jp.close_all()

    print_summary(passed, warned, blocked, total_cost, log_path)


def main() -> None:
    asyncio.run(run_demo())


if __name__ == "__main__":
    main()
