# API Reference

## Class: `Jeprum`

The main entry point. Create one instance and call `.monitor()` for each agent session.

```python
from jeprum import Jeprum
```

### Constructor

```python
Jeprum(
    api_key: str | None = None,         # API key for cloud transport
    transport_mode: str = "local",       # "local", "cloud", or "both"
    log_path: str = "jeprum_events.jsonl",  # Path for local JSONL logs
    cloud_endpoint: str = "https://api.jeprum.com",  # Cloud API URL
    enabled: bool = True,                # Set False to disable all monitoring
)
```

### Methods

**`monitor(session, *, rules, agent_name, agent_id, **kwargs) -> JeprumInterceptor`**

Wrap an MCP session with monitoring and guardrails.

| Parameter | Type | Description |
|-----------|------|-------------|
| `session` | Any | MCP ClientSession or any object with `call_tool()` |
| `rules` | dict \| list[Rule] \| None | Guardrail rules (shorthand dict or Rule objects) |
| `agent_name` | str \| None | Human-readable agent name |
| `agent_id` | str \| None | Unique ID (auto-generated if omitted) |

**`async close_all() -> None`**

Close all interceptors and flush pending events.

---

## Class: `JeprumInterceptor`

Returned by `Jeprum.monitor()`. Drop-in replacement for an MCP ClientSession.

### Methods

**`async call_tool(name: str, arguments: dict | None = None) -> Any`**

Intercept a tool call. Checks guardrails, executes the tool, logs the event.

Raises:
- `GuardrailViolation` — if a rule blocks the call
- `AgentKilled` — if the agent has been killed
- `AgentPaused` — if the agent has been paused

**`async list_tools() -> Any`**

Pass-through to the original session. No interception.

**`async kill() -> None`**

Kill the agent. All future `call_tool()` calls raise `AgentKilled`.

**`async pause() -> None`**

Pause the agent. All future `call_tool()` calls raise `AgentPaused`.

**`async resume() -> None`**

Resume a paused or killed agent.

**`async close() -> None`**

Flush pending events and shut down transport.

### Properties

**`status -> AgentStatus`**

Returns current agent status with cumulative stats.

---

## Data Models

### `AgentEvent`

A single action taken by an agent.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique event ID |
| `agent_id` | str | Agent identifier |
| `agent_name` | str \| None | Human-readable name |
| `timestamp` | datetime | When the event occurred (UTC) |
| `event_type` | str | `"tool_call"`, `"error"`, `"guardrail_trigger"` |
| `tool_name` | str | Name of the tool called |
| `input_params` | dict | Arguments passed to the tool |
| `output_result` | Any | Tool response |
| `duration_ms` | float \| None | Execution time in milliseconds |
| `estimated_cost_usd` | float \| None | Estimated cost of the call |
| `guardrail_check` | str | `"passed"`, `"blocked"`, `"warned"`, `"skipped"` |
| `guardrail_details` | str \| None | Explanation of guardrail decision |
| `trace_id` | str \| None | Optional trace correlation ID |
| `metadata` | dict | Arbitrary key-value metadata |

### `Rule`

A guardrail rule.

| Field | Type | Description |
|-------|------|-------------|
| `id` | UUID | Unique rule ID |
| `name` | str | Human-readable rule name |
| `rule_type` | str | `"max_spend"`, `"blocked_tool"`, `"rate_limit"`, `"alert_on"` |
| `config` | dict | Rule-specific configuration |
| `action` | str | `"block"`, `"warn"`, `"alert"`, `"kill"` |
| `is_active` | bool | Whether the rule is enabled |

### `AgentConfig`

Configuration for a monitored agent (created internally by `Jeprum.monitor()`).

| Field | Type | Default |
|-------|------|---------|
| `agent_id` | str | — |
| `agent_name` | str \| None | None |
| `api_key` | str \| None | None |
| `cloud_endpoint` | str | `"https://api.jeprum.com"` |
| `rules` | list[Rule] | [] |
| `transport_mode` | str | `"local"` |
| `local_log_path` | str | `"jeprum_events.jsonl"` |
| `batch_size` | int | 10 |
| `batch_interval_seconds` | float | 2.0 |
| `poll_interval_seconds` | float | 10.0 |
| `enabled` | bool | True |

### `AgentStatus`

Runtime status of a monitored agent.

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | str | Agent identifier |
| `status` | str | `"active"`, `"paused"`, `"killed"` |
| `total_cost_today_usd` | float | Cumulative cost today |
| `total_events_today` | int | Event count today |
| `last_event_at` | datetime \| None | Timestamp of last event |

---

## Exceptions

### `GuardrailViolation`

Raised when a guardrail rule blocks a tool call.

| Attribute | Type | Description |
|-----------|------|-------------|
| `rule_name` | str | Name of the rule that triggered |
| `reason` | str | Human-readable explanation |
| `event` | AgentEvent | The event that was blocked |

### `AgentKilled`

Raised when `call_tool()` is called on a killed agent. Inherits from `JeprumError`.

### `AgentPaused`

Raised when `call_tool()` is called on a paused agent. Inherits from `JeprumError`.
