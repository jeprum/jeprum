# Getting Started with Jeprum

Get up and running in 5 minutes.

## Prerequisites

- Python 3.11+
- An MCP-based agent (or use our mock for testing)

## Installation

```bash
pip install jeprum
```

For MCP integration:

```bash
pip install jeprum[mcp]
```

## Basic Usage — Local Monitoring

No cloud account needed. Events are logged to a local JSONL file.

```python
import asyncio
from jeprum import Jeprum

class MockSession:
    """Stand-in for an MCP ClientSession."""
    async def call_tool(self, name, arguments=None):
        return {"result": f"done: {name}"}

async def main():
    jp = Jeprum(transport_mode="local", log_path="events.jsonl")

    session = MockSession()
    monitored = jp.monitor(session, agent_name="My Agent")

    result = await monitored.call_tool("search", {"query": "hello"})
    print(result)  # {"result": "done: search"}

    await monitored.close()
    await jp.close_all()

asyncio.run(main())
```

After running, inspect the log:

```bash
cat events.jsonl | python -m json.tool --json-lines
```

Each line contains: agent ID, tool name, input/output, duration, guardrail status, and timestamp.

## Adding Guardrails

Guardrails are checked **before** each tool call. If a rule blocks, the tool is never executed.

```python
monitored = jp.monitor(session, rules={
    "max_spend_per_day": 10.0,           # Block when daily spend exceeds $10
    "blocked_tools": ["delete_*"],        # Block any tool matching delete_*
    "alert_on": ["send_*", "payment_*"], # Flag but allow matching tools
    "rate_limit": {"max_events": 100, "period_seconds": 60},
})
```

When a guardrail blocks a call:

```python
from jeprum import GuardrailViolation

try:
    await monitored.call_tool("delete_file", {"path": "/data"})
except GuardrailViolation as e:
    print(f"Blocked by rule '{e.rule_name}': {e.reason}")
```

Alert rules (`alert_on`) don't block — they mark the event as `warned` so it shows up highlighted in the dashboard.

## Cloud Dashboard

Connect to the Jeprum Cloud for real-time monitoring, remote kill switch, and a web dashboard.

### 1. Get an API key

```bash
curl -X POST https://jeprum-cloud.onrender.com/api/v1/api-keys \
  -H "Content-Type: application/json" \
  -d '{"tier": "starter"}'
```

### 2. Use cloud transport

```python
jp = Jeprum(
    api_key="jp_live_your_key_here",
    transport_mode="cloud",
    cloud_endpoint="https://jeprum-cloud.onrender.com",
)
```

Or use `transport_mode="both"` to log locally **and** ship to the cloud.

### 3. Open the dashboard

Visit the dashboard URL and enter your API key. You'll see every tool call in real-time.

## Kill Switch

From the dashboard, click **Kill** on any agent. The SDK polls for status changes every 10 seconds. When it detects a kill signal, the next `call_tool()` raises `AgentKilled`:

```python
from jeprum import AgentKilled

try:
    result = await monitored.call_tool("search", {"query": "test"})
except AgentKilled:
    print("Agent was killed remotely — shutting down")
```

You can also kill/pause/resume programmatically:

```python
await monitored.kill()    # All future calls raise AgentKilled
await monitored.pause()   # All future calls raise AgentPaused
await monitored.resume()  # Back to normal
```

## Next Steps

- [Guardrail Rules](rules.md) — detailed rule configuration
- [API Reference](api-reference.md) — all classes and methods
- [Contributing](../CONTRIBUTING.md) — help improve Jeprum
