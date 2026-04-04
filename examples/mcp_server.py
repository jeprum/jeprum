#!/usr/bin/env python3
"""Minimal MCP Server — exposes 3 tools for testing Jeprum integration.

Run directly:
    python examples/mcp_server.py

Or let the MCP client launch it via stdio transport.
"""
from __future__ import annotations

import ast
import operator
from datetime import datetime, timezone

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

server = Server("jeprum-demo-server")

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

TOOLS = [
    Tool(
        name="search",
        description="Search the web for a query and return mock results.",
        inputSchema={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
    ),
    Tool(
        name="calculator",
        description="Evaluate a simple math expression.",
        inputSchema={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "Math expression like '2 + 3 * 4'"},
            },
            "required": ["expression"],
        },
    ),
    Tool(
        name="get_time",
        description="Return the current UTC time.",
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
]

# Safe math operators for calculator
SAFE_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
}


def _safe_eval(expr: str) -> float:
    """Evaluate a math expression safely using AST parsing."""
    tree = ast.parse(expr, mode="eval")

    def _eval(node: ast.expr) -> float:
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.BinOp):
            op_type = type(node.op)
            if op_type not in SAFE_OPS:
                raise ValueError(f"Unsupported operator: {op_type.__name__}")
            return SAFE_OPS[op_type](_eval(node.left), _eval(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -_eval(node.operand)
        raise ValueError(f"Unsupported expression node: {type(node).__name__}")

    return _eval(tree)


# ---------------------------------------------------------------------------
# MCP handlers
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "search":
        query = arguments.get("query", "")
        return [
            TextContent(
                type="text",
                text=f"Search results for '{query}':\n"
                f"1. Introduction to {query} — Wikipedia\n"
                f"2. {query} explained — Medium article\n"
                f"3. Latest developments in {query} — arXiv paper",
            )
        ]

    if name == "calculator":
        expression = arguments.get("expression", "0")
        try:
            result = _safe_eval(expression)
            return [TextContent(type="text", text=f"{expression} = {result}")]
        except Exception as exc:
            return [TextContent(type="text", text=f"Error: {exc}")]

    if name == "get_time":
        now = datetime.now(timezone.utc).isoformat()
        return [TextContent(type="text", text=f"Current UTC time: {now}")]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
