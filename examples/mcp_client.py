#!/usr/bin/env python3
"""Minimal MCP Client — connects to mcp_server.py via stdio and calls every tool.

Run:
    python examples/mcp_client.py
"""
from __future__ import annotations

import asyncio
import sys

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    # Launch the MCP server as a subprocess
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["examples/mcp_server.py"],
    )

    print("🔌 Connecting to MCP server…")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            print("✅ Connected!\n")

            # 1. List available tools
            tools_result = await session.list_tools()
            tool_names = [t.name for t in tools_result.tools]
            print(f"📋 Available tools: {tool_names}\n")

            # 2. Call each tool
            print("─" * 50)

            # Search
            result = await session.call_tool("search", {"query": "AI agents"})
            print(f"🔍 search('AI agents'):")
            for content in result.content:
                print(f"   {content.text}")
            print()

            # Calculator
            result = await session.call_tool("calculator", {"expression": "42 * 17 + 3"})
            print(f"🧮 calculator('42 * 17 + 3'):")
            for content in result.content:
                print(f"   {content.text}")
            print()

            # Get time
            result = await session.call_tool("get_time", {})
            print(f"🕐 get_time():")
            for content in result.content:
                print(f"   {content.text}")
            print()

            print("─" * 50)
            print("✨ Done — all tools called successfully.")


if __name__ == "__main__":
    asyncio.run(main())
