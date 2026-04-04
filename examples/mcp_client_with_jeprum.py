#!/usr/bin/env python3
"""MCP Client wrapped with Jeprum — first REAL MCP integration.

Demonstrates Jeprum governing an actual MCP agent:
  - search calls trigger alerts
  - calculator is BLOCKED by guardrail
  - get_time passes cleanly

Run:
    python examples/mcp_client_with_jeprum.py

With cloud transport (events visible on dashboard):
    JEPRUM_API_KEY=jp_live_xxx python examples/mcp_client_with_jeprum.py
"""
from __future__ import annotations

import asyncio
import os
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jeprum import Jeprum
from jeprum.exceptions import GuardrailViolation, AgentKilled, AgentPaused

CLOUD_ENDPOINT = "https://jeprum-cloud.onrender.com"

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"


async def main():
    api_key = os.environ.get("JEPRUM_API_KEY")
    mode = "both" if api_key else "local"

    print(f"\n{BOLD}{CYAN}╔═══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║  JEPRUM + MCP — Real Integration Demo             ║{RESET}")
    print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════╝{RESET}")
    print(f"{DIM}  Mode: {mode} | Cloud: {'✓' if api_key else '✗'}{RESET}\n")

    # Launch the real MCP server
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["examples/mcp_server.py"],
    )

    print(f"{DIM}🔌 Connecting to MCP server…{RESET}")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print(f"{GREEN}✅ MCP session ready{RESET}\n")

            # Wrap with Jeprum — THE KEY LINE
            jp = Jeprum(
                api_key=api_key,
                transport_mode=mode,
                log_path="jeprum_mcp_demo.jsonl",
                cloud_endpoint=CLOUD_ENDPOINT,
            )

            monitored = jp.monitor(
                session,
                agent_name="MCP Demo Agent",
                rules={
                    "blocked_tools": ["calculator"],  # Block calculator
                    "alert_on": ["search"],           # Alert on search
                    "max_spend_per_day": 1.00,        # $1 budget
                },
            )

            # List tools (pass-through, no interception)
            tools_result = await monitored.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"📋 Tools: {tool_names}\n")
            print(f"  {DIM}Guardrails:{RESET}")
            print(f"  {DIM}  • Blocked: calculator{RESET}")
            print(f"  {DIM}  • Alert: search{RESET}")
            print(f"  {DIM}  • Budget: $1.00/day{RESET}\n")
            print(f"{'─' * 55}")

            # Call 1: search — should PASS + trigger ALERT
            print(f"\n{BOLD}[1/3] Calling search('AI agents')…{RESET}")
            try:
                result = await monitored.call_tool("search", {"query": "AI agents"})
                for content in result.content:
                    print(f"  {GREEN}✅ PASSED (alerted){RESET}")
                    print(f"  {DIM}{content.text[:80]}…{RESET}")
            except GuardrailViolation as e:
                print(f"  {RED}🛑 BLOCKED: {e.reason}{RESET}")

            # Call 2: calculator — should be BLOCKED
            print(f"\n{BOLD}[2/3] Calling calculator('42 * 17')…{RESET}")
            try:
                result = await monitored.call_tool("calculator", {"expression": "42 * 17"})
                print(f"  {GREEN}✅ PASSED{RESET}")
            except GuardrailViolation as e:
                print(f"  {RED}🛑 BLOCKED: {e.reason}{RESET}")

            # Call 3: get_time — should PASS cleanly
            print(f"\n{BOLD}[3/3] Calling get_time()…{RESET}")
            try:
                result = await monitored.call_tool("get_time", {})
                for content in result.content:
                    print(f"  {GREEN}✅ PASSED{RESET}")
                    print(f"  {DIM}{content.text}{RESET}")
            except GuardrailViolation as e:
                print(f"  {RED}🛑 BLOCKED: {e.reason}{RESET}")

            print(f"\n{'─' * 55}")
            print(f"\n{BOLD}Summary:{RESET}")
            print(f"  {GREEN}Passed:{RESET}  2 (search + get_time)")
            print(f"  {YELLOW}Alerted:{RESET} 1 (search)")
            print(f"  {RED}Blocked:{RESET} 1 (calculator)")

            if api_key:
                print(f"\n  {CYAN}📊 Events visible on your dashboard{RESET}")

            # Clean up
            await jp.close_all()

    print(f"\n{BOLD}✨ Demo complete.{RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
