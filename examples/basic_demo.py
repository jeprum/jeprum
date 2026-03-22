"""Jeprum SDK Demo — Full-stack demonstration: SDK → Cloud Backend → Dashboard.

Run with:
    JEPRUM_API_KEY=jp_live_xxx uv run python examples/basic_demo.py

Or for local-only (no cloud):
    uv run python examples/basic_demo.py
"""

from __future__ import annotations

import asyncio
import os
import random
import sys
from pathlib import Path
from typing import Any

from jeprum import Jeprum, GuardrailViolation, AgentKilled, AgentPaused

# ---------------------------------------------------------------------------
# ANSI color codes
# ---------------------------------------------------------------------------
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

DASHBOARD_URL = "https://jeprum-dashboard.vercel.app"
CLOUD_ENDPOINT = "https://jeprum-cloud.onrender.com"

# ---------------------------------------------------------------------------
# Mock MCP Session
# ---------------------------------------------------------------------------

TOOL_COSTS: dict[str, float] = {
    "web_search": 0.012,
    "calculator": 0.005,
    "read_file": 0.008,
    "analyze_data": 0.020,
    "send_notification": 0.030,
    "delete_file": 0.010,
    "get_weather": 0.007,
    "summarize": 0.025,
}


class MockMCPSession:
    """Simulates an MCP ClientSession with realistic latency."""

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        await asyncio.sleep(random.uniform(0.05, 0.30))
        return {"status": "ok", "tool": name, "result": f"Result for {name}"}

    async def list_tools(self) -> list[dict[str, str]]:
        return [{"name": n} for n in TOOL_COSTS]


# ---------------------------------------------------------------------------
# Demo calls
# ---------------------------------------------------------------------------

DEMO_CALLS: list[tuple[str, dict[str, Any]]] = [
    # Phase 1: Normal operations (passed)
    ("web_search", {"query": "latest AI agent frameworks 2026"}),
    ("calculator", {"expression": "42 * 17 + 3"}),
    ("get_weather", {"city": "New York"}),
    # Phase 2: Analytics (passed, costs add up)
    ("analyze_data", {"dataset": "agent_metrics_q1"}),
    ("analyze_data", {"dataset": "cost_breakdown"}),
    # Phase 3: Notification — triggers alert_on (warned)
    ("send_notification", {"to": "team@example.com", "message": "Agent report ready"}),
    # Phase 4: Dangerous operation — blocked by tool rule
    ("delete_file", {"path": "/etc/important.conf"}),
    # Phase 5: More work, approaching spending limit
    ("web_search", {"query": "MCP protocol specification"}),
    ("summarize", {"text": "A long document about AI safety..."}),
    ("read_file", {"path": "/tmp/config.yaml"}),
    ("web_search", {"query": "Python async best practices"}),
    ("summarize", {"text": "Another document about governance..."}),
    # Phase 6: Should hit spending limit
    ("analyze_data", {"dataset": "final_report"}),
    ("web_search", {"query": "agent monitoring tools"}),
    ("summarize", {"text": "Yet another analysis document..."}),
]


def print_banner(api_key: str | None) -> None:
    print()
    print(f"{BOLD}{CYAN}╔═══════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║           JEPRUM — Agent Control Plane                ║{RESET}")
    print(f"{BOLD}{CYAN}║              Live Demo v0.1.0                         ║{RESET}")
    print(f"{BOLD}{CYAN}╠═══════════════════════════════════════════════════════╣{RESET}")
    if api_key:
        print(f"{BOLD}{CYAN}║  Dashboard: {RESET}{DASHBOARD_URL:<41}{BOLD}{CYAN}║{RESET}")
        print(f"{BOLD}{CYAN}║  Open the dashboard to watch events live!             ║{RESET}")
    else:
        print(f"{BOLD}{CYAN}║  Mode: Local only (set JEPRUM_API_KEY for cloud)      ║{RESET}")
    print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════════╝{RESET}")
    print()
    print(f"{DIM}  Guardrails:{RESET}")
    print(f"{DIM}    • Max spend: $0.15/day  • Blocked: delete_*  • Alert: send_*, notify_*{RESET}")
    print()
    print(f"{BOLD}  Running {len(DEMO_CALLS)} agent tool calls...{RESET}")
    print(f"{DIM}  {'─' * 62}{RESET}")
    print()


def print_event(
    index: int,
    tool_name: str,
    status: str,
    cost: float,
    duration_ms: float,
    detail: str = "",
) -> None:
    icons = {"PASSED": f"{GREEN}✅", "WARNED": f"{YELLOW}⚠️ ", "BLOCKED": f"{RED}🛑"}
    icon = icons.get(status, "  ")
    cost_str = f"${cost:.3f}" if cost > 0 else "  —  "
    dur_str = f"{duration_ms:.0f}ms" if duration_ms > 0 else "  —"
    idx_str = f"[{index + 1:2d}/{len(DEMO_CALLS)}]"
    color = {"PASSED": GREEN, "WARNED": YELLOW, "BLOCKED": RED}.get(status, RESET)

    print(f"  {idx_str} {icon} {color}{tool_name:20s}{RESET} {cost_str:>7s}  {dur_str:>6s}", end="")
    if detail:
        print(f"  {DIM}{detail}{RESET}", end="")
    print()


def print_summary(passed: int, warned: int, blocked: int, total_cost: float, mode: str) -> None:
    print()
    print(f"{DIM}  {'─' * 62}{RESET}")
    print()
    print(f"{BOLD}  ═══ Demo Summary ═══{RESET}")
    print(f"  Total events:     {passed + warned + blocked}")
    print(f"  {GREEN}Passed:{RESET}           {passed}")
    print(f"  {YELLOW}Warned:{RESET}           {warned}")
    print(f"  {RED}Blocked:{RESET}          {blocked}")
    print(f"  Total cost:       ${total_cost:.4f}")
    print()
    if mode != "local":
        print(f"  {BOLD}Events are now visible on your dashboard.{RESET}")
        print(f"  Try clicking \"Kill\" on the agent to see the kill switch work!")
        print()


async def run_demo() -> None:
    api_key = os.environ.get("JEPRUM_API_KEY")
    log_path = "jeprum_demo_events.jsonl"
    Path(log_path).unlink(missing_ok=True)

    mode = "both" if api_key else "local"

    jp = Jeprum(
        api_key=api_key,
        transport_mode=mode,
        log_path=log_path,
        cloud_endpoint=CLOUD_ENDPOINT,
    )

    session = MockMCPSession()
    agent = jp.monitor(
        session,
        agent_name="Demo Agent",
        rules={
            "max_spend_per_day": 0.15,
            "blocked_tools": ["delete_*"],
            "alert_on": ["send_*", "notify_*"],
        },
    )

    print_banner(api_key)

    passed = warned = blocked = 0
    total_cost = 0.0

    for i, (tool_name, args) in enumerate(DEMO_CALLS):
        cost = TOOL_COSTS.get(tool_name, 0.01)

        # Pre-check spending limit
        from jeprum.models import AgentEvent
        check_evt = AgentEvent(
            agent_id=agent._config.agent_id,
            tool_name=tool_name,
            estimated_cost_usd=cost,
        )
        spend_result = agent._rule_engine.evaluate(check_evt)

        if spend_result.action in ("block", "kill"):
            blocked += 1
            print_event(i, tool_name, "BLOCKED", 0, 0, f"💰 {spend_result.reason}")
            continue

        try:
            result = await agent.call_tool(tool_name, args)

            # Record cost
            cost_evt = AgentEvent(
                agent_id=agent._config.agent_id,
                tool_name=tool_name,
                estimated_cost_usd=cost,
            )
            agent._rule_engine.record_event(cost_evt)
            total_cost += cost

            # Check alert status
            alert_evt = AgentEvent(agent_id=agent._config.agent_id, tool_name=tool_name)
            alert_result = agent._rule_engine.evaluate(alert_evt)

            duration = random.uniform(50, 300)
            if alert_result.action in ("alert", "warn"):
                warned += 1
                print_event(i, tool_name, "WARNED", cost, duration, alert_result.reason or "")
            else:
                passed += 1
                print_event(i, tool_name, "PASSED", cost, duration)

        except GuardrailViolation as exc:
            blocked += 1
            print_event(i, tool_name, "BLOCKED", 0, 0, exc.reason)

        except (AgentKilled, AgentPaused) as exc:
            blocked += 1
            print_event(i, tool_name, "BLOCKED", 0, 0, type(exc).__name__)
            break

    print_summary(passed, warned, blocked, total_cost, mode)

    # If cloud mode, keep agent alive so user can test kill switch from dashboard
    if api_key:
        print(f"  {BOLD}Agent is still running — making a call every 3 seconds.{RESET}")
        print(f"  {DIM}Press Ctrl+C to stop, or kill from the dashboard.{RESET}")
        print()
        try:
            loop_idx = len(DEMO_CALLS)
            tools = ["web_search", "calculator", "get_weather", "read_file"]
            while True:
                await asyncio.sleep(3)
                tool = random.choice(tools)
                try:
                    await agent.call_tool(tool, {"query": "keep-alive"})
                    print(f"  {GREEN}✅ {tool}{RESET}  {DIM}(live — kill from dashboard to stop){RESET}")
                except (AgentKilled, AgentPaused) as exc:
                    print(f"\n  {RED}{BOLD}🛑 Agent stopped: {type(exc).__name__}{RESET}")
                    print(f"  {DIM}The kill switch worked! Agent received the signal from the dashboard.{RESET}")
                    break
                except GuardrailViolation:
                    pass
        except KeyboardInterrupt:
            print(f"\n  {DIM}Stopped by user (Ctrl+C){RESET}")

    await agent.close()
    await jp.close_all()
    print()


def main() -> None:
    try:
        asyncio.run(run_demo())
    except KeyboardInterrupt:
        print(f"\n{DIM}  Exited.{RESET}")


if __name__ == "__main__":
    main()
