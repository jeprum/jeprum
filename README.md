# Jeprum

The live control room for AI agents — see everything, set rules, stop anything.

[![PyPI](https://img.shields.io/pypi/v/jeprum)](https://pypi.org/project/jeprum/)
[![Python](https://img.shields.io/pypi/pyversions/jeprum)](https://pypi.org/project/jeprum/)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Tests](https://github.com/jeprum/jeprum/actions/workflows/ci.yml/badge.svg)](https://github.com/jeprum/jeprum/actions)

## What is Jeprum?

Jeprum is an open-source SDK that monitors and governs AI agents in real-time. It intercepts MCP tool calls, enforces guardrails (spending limits, tool blocking, rate limits), provides a kill switch, and ships telemetry to a cloud dashboard. Install in one command, integrate in 5 lines of code.

## Quick Start

```bash
pip install jeprum
```

```python
from jeprum import Jeprum

jp = Jeprum(api_key="jp_live_xxx", transport_mode="cloud")
monitored = jp.monitor(my_mcp_session, rules={
    "max_spend_per_day": 10.0,
    "blocked_tools": ["delete_*"]
})
result = await monitored.call_tool("search", {"query": "test"})
```

## Features

- **Real-time monitoring** — every tool call captured with duration, cost, and I/O
- **Guardrails** — spending limits, tool blocking, rate limiting, alert patterns
- **Kill switch** — stop any agent remotely from the dashboard
- **Cloud dashboard** — live event timeline, cost tracking, agent management
- **MCP-native** — wraps ClientSession with zero agent code changes
- **Non-blocking** — telemetry shipping never slows your agent
- **Open source** — Apache 2.0

## How It Works

```
Agent → Jeprum SDK (intercept + guardrails) → MCP Server → Tool
               ↓
        Jeprum Cloud (dashboard, kill switch, audit trail)
```

The SDK wraps your MCP session. Every `call_tool()` is intercepted: guardrails are checked synchronously (before execution), events are shipped asynchronously (after execution). Your agent code doesn't change.

## Configuration

```python
rules = {
    "max_spend_per_day": 10.0,
    "blocked_tools": ["delete_*", "drop_*"],
    "alert_on": ["payment.*", "transfer.*"],
    "rate_limit": {"max_events": 100, "period_seconds": 60}
}
```

## Cloud Dashboard

Sign up at [jeprum.com](https://jeprum.com) to get an API key. The dashboard provides:

- Live event timeline with guardrail status
- Agent list with cost and status tracking
- Kill / pause / resume controls
- Cost-over-time charts

## Documentation

- [Getting Started](docs/getting-started.md)
- [Guardrail Rules](docs/rules.md)
- [API Reference](docs/api-reference.md)
- [Contributing](CONTRIBUTING.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.

Built by [Jithendra Siddartha](https://linkedin.com/in/jithendra-siddartha), MS CS @ NYU Tandon.
