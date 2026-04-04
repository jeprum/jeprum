#!/usr/bin/env python3
"""API-Calling Agent with Spending Limits — MCP server + Jeprum budget enforcement.

Demonstrates Jeprum enforcing a $0.10/day spending limit on an agent that
calls paid APIs. Shows cost accumulating until the budget is hit.

Run:
    python examples/api_agent_budget.py

With cloud transport:
    JEPRUM_API_KEY=jp_live_xxx python examples/api_agent_budget.py
"""
from __future__ import annotations

import asyncio
import os
import random
import sys

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jeprum import Jeprum
from jeprum.models import AgentEvent
from jeprum.exceptions import GuardrailViolation

CLOUD_ENDPOINT = "https://jeprum-cloud.onrender.com"

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

# ---------------------------------------------------------------------------
# Cost map — simulated cost per tool call
# ---------------------------------------------------------------------------

TOOL_COSTS = {
    "web_search": 0.01,
    "generate_image": 0.05,
    "translate": 0.02,
    "send_email": 0.03,
}

# ---------------------------------------------------------------------------
# MCP Server — simulated paid APIs
# ---------------------------------------------------------------------------

api_server = Server("jeprum-api-server")

API_TOOLS = [
    Tool(
        name="web_search",
        description="Search the web ($0.01/call).",
        inputSchema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    ),
    Tool(
        name="generate_image",
        description="Generate an image from a prompt ($0.05/call).",
        inputSchema={
            "type": "object",
            "properties": {"prompt": {"type": "string"}},
            "required": ["prompt"],
        },
    ),
    Tool(
        name="translate",
        description="Translate text to another language ($0.02/call).",
        inputSchema={
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "target_lang": {"type": "string"},
            },
            "required": ["text", "target_lang"],
        },
    ),
    Tool(
        name="send_email",
        description="Send an email notification ($0.03/call).",
        inputSchema={
            "type": "object",
            "properties": {
                "to": {"type": "string"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["to", "subject", "body"],
        },
    ),
]


@api_server.list_tools()
async def api_list_tools() -> list[Tool]:
    return API_TOOLS


@api_server.call_tool()
async def api_call_tool(name: str, arguments: dict) -> list[TextContent]:
    # Simulate API latency
    await asyncio.sleep(random.uniform(0.05, 0.15))

    if name == "web_search":
        return [TextContent(type="text", text=f"Results for '{arguments.get('query', '')}': 3 articles found")]
    if name == "generate_image":
        return [TextContent(type="text", text=f"Image generated: {arguments.get('prompt', '')} (512x512, PNG)")]
    if name == "translate":
        return [TextContent(type="text", text=f"Translated to {arguments.get('target_lang', '?')}: «{arguments.get('text', '')[:30]}»")]
    if name == "send_email":
        return [TextContent(type="text", text=f"Email sent to {arguments.get('to', '?')}: {arguments.get('subject', '')}")]
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def run_server():
    async with stdio_server() as (read_stream, write_stream):
        await api_server.run(read_stream, write_stream, api_server.create_initialization_options())


# ---------------------------------------------------------------------------
# Client with Jeprum budget enforcement
# ---------------------------------------------------------------------------

# Sequence of API calls the agent will attempt
AGENT_CALLS = [
    ("web_search", {"query": "latest AI frameworks 2026"}),
    ("translate", {"text": "Hello world", "target_lang": "es"}),
    ("web_search", {"query": "MCP protocol specification"}),
    ("generate_image", {"prompt": "a robot reading a book"}),
    ("send_email", {"to": "team@example.com", "subject": "Agent report", "body": "Summary of findings…"}),
    ("translate", {"text": "Budget is running low", "target_lang": "fr"}),
    ("web_search", {"query": "cost optimization strategies"}),
    ("generate_image", {"prompt": "a futuristic dashboard"}),  # Budget should be hit by now
    ("web_search", {"query": "this should be blocked"}),
    ("send_email", {"to": "boss@example.com", "subject": "Final report", "body": "…"}),
]


async def run_client():
    api_key = os.environ.get("JEPRUM_API_KEY")
    mode = "both" if api_key else "local"

    print(f"\n{BOLD}{CYAN}╔═══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║  JEPRUM — API Agent Budget Demo                   ║{RESET}")
    print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════╝{RESET}")
    print(f"{DIM}  Budget: $0.10/day | Mode: {mode}{RESET}\n")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["examples/api_agent_budget.py", "--server"],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            jp = Jeprum(
                api_key=api_key,
                transport_mode=mode,
                log_path="jeprum_budget_demo.jsonl",
                cloud_endpoint=CLOUD_ENDPOINT,
            )

            agent = jp.monitor(
                session,
                agent_name="API Budget Agent",
                rules={
                    "max_spend_per_day": 0.10,  # $0.10 budget
                    "alert_on": ["send_email"],
                },
            )

            print(f"{'─' * 60}")
            print(f"  {'#':>3}  {'Tool':<18} {'Cost':>7} {'Total':>8}  {'Status'}")
            print(f"{'─' * 60}")

            passed = blocked = alerted = 0
            running_cost = 0.0

            for i, (tool_name, args) in enumerate(AGENT_CALLS, 1):
                cost = TOOL_COSTS.get(tool_name, 0.01)

                # Pre-check spending limit (same pattern as basic_demo)
                check_evt = AgentEvent(
                    agent_id=agent._config.agent_id,
                    tool_name=tool_name,
                    estimated_cost_usd=cost,
                )
                spend_result = agent._rule_engine.evaluate(check_evt)

                if spend_result.action in ("block", "kill"):
                    blocked += 1
                    bar = _cost_bar(running_cost, 0.10)
                    print(f"  {i:3d}  {tool_name:<18} ${cost:.2f}   ${running_cost:.4f}  {RED}🛑 BLOCKED{RESET}  {bar}")
                    print(f"       {DIM}{spend_result.reason}{RESET}")
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
                    running_cost += cost

                    # Check alert
                    alert_evt = AgentEvent(agent_id=agent._config.agent_id, tool_name=tool_name)
                    alert_result = agent._rule_engine.evaluate(alert_evt)

                    bar = _cost_bar(running_cost, 0.10)

                    if alert_result.action in ("alert", "warn"):
                        alerted += 1
                        print(f"  {i:3d}  {tool_name:<18} ${cost:.2f}   ${running_cost:.4f}  {YELLOW}⚠️  ALERTED{RESET} {bar}")
                    else:
                        passed += 1
                        print(f"  {i:3d}  {tool_name:<18} ${cost:.2f}   ${running_cost:.4f}  {GREEN}✅ PASSED{RESET}  {bar}")

                except GuardrailViolation as e:
                    blocked += 1
                    bar = _cost_bar(running_cost, 0.10)
                    print(f"  {i:3d}  {tool_name:<18} ${cost:.2f}   ${running_cost:.4f}  {RED}🛑 BLOCKED{RESET}  {bar}")

            print(f"{'─' * 60}")
            print(f"\n{BOLD}Summary:{RESET}")
            print(f"  Budget:   $0.10/day")
            print(f"  Spent:    ${running_cost:.4f}")
            print(f"  {GREEN}Passed:{RESET}  {passed}")
            print(f"  {YELLOW}Alerted:{RESET} {alerted}")
            print(f"  {RED}Blocked:{RESET} {blocked}")

            if blocked > 0:
                print(f"\n  {RED}💰 Budget enforced — agent stopped spending at ${running_cost:.4f}{RESET}")

            if api_key:
                print(f"\n  {CYAN}📊 Cost chart updating on dashboard{RESET}")

            await jp.close_all()

    print(f"\n{BOLD}✨ Demo complete.{RESET}\n")


def _cost_bar(current: float, limit: float) -> str:
    """Render a tiny cost progress bar."""
    pct = min(current / limit, 1.0) if limit > 0 else 0
    filled = int(pct * 10)
    empty = 10 - filled
    color = GREEN if pct < 0.6 else YELLOW if pct < 0.9 else RED
    return f"{color}{'█' * filled}{'░' * empty}{RESET} {pct:.0%}"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--server" in sys.argv:
        asyncio.run(run_server())
    else:
        asyncio.run(run_client())
