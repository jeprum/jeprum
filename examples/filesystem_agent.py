#!/usr/bin/env python3
"""Filesystem Agent — MCP server + client with Jeprum guardrails.

Demonstrates Jeprum governing a filesystem agent:
  - read_file / list_directory → pass
  - write_file → triggers alert (warned)
  - delete_file → BLOCKED by guardrail
  - Rate limited to 20 calls/minute

Run:
    python examples/filesystem_agent.py

With cloud transport:
    JEPRUM_API_KEY=jp_live_xxx python examples/filesystem_agent.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from jeprum import Jeprum
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
# MCP Filesystem Server (inline — launched as subprocess with --server flag)
# ---------------------------------------------------------------------------

SANDBOX_DIR: str | None = None  # Set at runtime

FS_TOOLS = [
    Tool(
        name="read_file",
        description="Read the contents of a file.",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    Tool(
        name="write_file",
        description="Write content to a file.",
        inputSchema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    ),
    Tool(
        name="list_directory",
        description="List files in a directory.",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
    Tool(
        name="delete_file",
        description="Delete a file.",
        inputSchema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
    ),
]


def _resolve(path: str) -> Path:
    """Resolve a path within the sandbox."""
    sandbox = Path(os.environ.get("FS_SANDBOX", "/tmp/jeprum_fs_demo"))
    resolved = (sandbox / path).resolve()
    if not str(resolved).startswith(str(sandbox.resolve())):
        raise ValueError("Path escape detected")
    return resolved


fs_server = Server("jeprum-fs-server")


@fs_server.list_tools()
async def fs_list_tools() -> list[Tool]:
    return FS_TOOLS


@fs_server.call_tool()
async def fs_call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "read_file":
            p = _resolve(arguments["path"])
            text = p.read_text() if p.exists() else f"File not found: {arguments['path']}"
            return [TextContent(type="text", text=text)]

        if name == "write_file":
            p = _resolve(arguments["path"])
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(arguments["content"])
            return [TextContent(type="text", text=f"Written {len(arguments['content'])} bytes to {arguments['path']}")]

        if name == "list_directory":
            p = _resolve(arguments["path"])
            if not p.is_dir():
                return [TextContent(type="text", text=f"Not a directory: {arguments['path']}")]
            entries = sorted(e.name for e in p.iterdir())
            return [TextContent(type="text", text="\n".join(entries) if entries else "(empty)")]

        if name == "delete_file":
            p = _resolve(arguments["path"])
            if p.exists():
                p.unlink()
                return [TextContent(type="text", text=f"Deleted: {arguments['path']}")]
            return [TextContent(type="text", text=f"Not found: {arguments['path']}")]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def run_server():
    async with stdio_server() as (read_stream, write_stream):
        await fs_server.run(read_stream, write_stream, fs_server.create_initialization_options())


# ---------------------------------------------------------------------------
# Client with Jeprum
# ---------------------------------------------------------------------------


async def run_client():
    api_key = os.environ.get("JEPRUM_API_KEY")
    mode = "both" if api_key else "local"

    # Create a sandbox directory with sample files
    sandbox = Path(tempfile.mkdtemp(prefix="jeprum_fs_"))
    (sandbox / "readme.txt").write_text("Welcome to the Jeprum filesystem demo.")
    (sandbox / "data.csv").write_text("name,value\nalpha,1\nbeta,2\ngamma,3")
    (sandbox / "config.json").write_text('{"version": "1.0", "debug": false}')

    print(f"\n{BOLD}{CYAN}╔═══════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║  JEPRUM — Filesystem Agent Demo                   ║{RESET}")
    print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════╝{RESET}")
    print(f"{DIM}  Sandbox: {sandbox}{RESET}")
    print(f"{DIM}  Mode: {mode}{RESET}\n")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=["examples/filesystem_agent.py", "--server"],
        env={**os.environ, "FS_SANDBOX": str(sandbox)},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            jp = Jeprum(
                api_key=api_key,
                transport_mode=mode,
                log_path="jeprum_filesystem_demo.jsonl",
                cloud_endpoint=CLOUD_ENDPOINT,
            )

            agent = jp.monitor(
                session,
                agent_name="Filesystem Agent",
                rules={
                    "blocked_tools": ["delete_*"],
                    "alert_on": ["write_*"],
                    "rate_limit": {"max_events": 20, "period_seconds": 60},
                },
            )

            tools_result = await agent.list_tools()
            print(f"📋 Tools: {[t.name for t in tools_result.tools]}")
            print(f"  {DIM}Guardrails: block delete_*, alert write_*, 20 calls/min{RESET}\n")
            print(f"{'─' * 55}")

            calls = [
                ("list_directory", {"path": "."}, "List sandbox directory"),
                ("read_file", {"path": "readme.txt"}, "Read readme.txt"),
                ("read_file", {"path": "data.csv"}, "Read data.csv"),
                ("write_file", {"path": "output.txt", "content": "Agent wrote this!"}, "Write output.txt"),
                ("delete_file", {"path": "config.json"}, "Delete config.json"),
            ]

            passed = blocked = warned = 0

            for i, (tool, args, desc) in enumerate(calls, 1):
                print(f"\n{BOLD}[{i}/{len(calls)}] {desc}{RESET}")
                print(f"  {DIM}→ {tool}({args}){RESET}")

                try:
                    result = await agent.call_tool(tool, args)
                    text = result.content[0].text if result.content else "(no output)"

                    # Check if it was alerted
                    if tool.startswith("write"):
                        warned += 1
                        print(f"  {YELLOW}⚠️  PASSED (alerted){RESET}")
                    else:
                        passed += 1
                        print(f"  {GREEN}✅ PASSED{RESET}")

                    # Show first line of output
                    first_line = text.split("\n")[0][:70]
                    print(f"  {DIM}{first_line}{RESET}")

                except GuardrailViolation as e:
                    blocked += 1
                    print(f"  {RED}🛑 BLOCKED: {e.reason}{RESET}")

            print(f"\n{'─' * 55}")
            print(f"\n{BOLD}Summary:{RESET}")
            print(f"  {GREEN}Passed:{RESET}  {passed}")
            print(f"  {YELLOW}Warned:{RESET}  {warned}")
            print(f"  {RED}Blocked:{RESET} {blocked}")

            if api_key:
                print(f"\n  {CYAN}📊 Events visible on dashboard{RESET}")

            await jp.close_all()

    # Clean up sandbox
    import shutil
    shutil.rmtree(sandbox, ignore_errors=True)
    print(f"\n{BOLD}✨ Demo complete.{RESET}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if "--server" in sys.argv:
        asyncio.run(run_server())
    else:
        asyncio.run(run_client())
