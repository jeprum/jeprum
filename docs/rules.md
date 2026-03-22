# Guardrail Rules

Jeprum's rule engine evaluates every tool call before execution. Rules are checked synchronously — if a rule blocks, the tool is never called.

## Rule Types

### max_spend

Tracks cumulative cost per agent per day. Blocks when the next call would exceed the limit.

```python
rules = {"max_spend_per_day": 10.0}
```

Equivalent Rule object:

```python
Rule(name="spending", rule_type="max_spend", config={"max_usd": 10.0}, action="block")
```

- Requires `estimated_cost_usd` to be set on events
- Resets daily (midnight UTC)
- Each agent is tracked independently

### blocked_tool

Blocks specific tools by name pattern using `fnmatch`-style matching.

```python
rules = {"blocked_tools": ["delete_*", "drop_*", "rm_*"]}
```

Equivalent Rule object:

```python
Rule(name="no_deletes", rule_type="blocked_tool", config={"patterns": ["delete_*"]}, action="block")
```

- `*` matches any characters: `delete_*` blocks `delete_file`, `delete_user`, etc.
- `?` matches a single character
- `[abc]` matches one of the listed characters

### rate_limit

Limits how many tool calls an agent can make in a sliding time window.

```python
rules = {"rate_limit": {"max_events": 100, "period_seconds": 60}}
```

Equivalent Rule object:

```python
Rule(name="rate_limit", rule_type="rate_limit", config={"max_events": 100, "period_seconds": 60}, action="block")
```

- Uses a sliding window — old events outside the window don't count
- Applied per agent

### alert_on

Flags matching tool calls as "warned" but does **not** block them. Events appear highlighted in the dashboard.

```python
rules = {"alert_on": ["payment_*", "send_*", "transfer_*"]}
```

Equivalent Rule object:

```python
Rule(name="payment_alert", rule_type="alert_on", config={"patterns": ["payment_*"]}, action="alert")
```

- The tool call proceeds normally
- Event is marked `guardrail_check="warned"` 
- Shows as yellow in the dashboard timeline

## Rule Actions

| Action | Behavior |
|--------|----------|
| `block` | Stop this specific tool call, raise `GuardrailViolation` |
| `warn` | Allow the call, mark event as warned |
| `alert` | Same as warn (forward-compatible with alerting integrations) |
| `kill` | Stop the agent entirely — equivalent to remote kill switch |

## Using Rule Objects Directly

For more control, create `Rule` objects instead of using the shorthand dict:

```python
from jeprum.models import Rule

rules = [
    Rule(
        name="spending_cap",
        rule_type="max_spend",
        config={"max_usd": 5.0},
        action="kill",  # Kill the agent (not just block the call) when exceeded
    ),
    Rule(
        name="no_destructive",
        rule_type="blocked_tool",
        config={"patterns": ["delete_*", "drop_*", "truncate_*"]},
        action="block",
    ),
    Rule(
        name="sensitive_ops",
        rule_type="alert_on",
        config={"patterns": ["payment_*", "transfer_*"]},
        action="alert",
    ),
]

monitored = jp.monitor(session, rules=rules)
```

## Multiple Rules

When multiple rules match the same event, the most restrictive action wins:

`kill` > `block` > `warn`/`alert` > `allow`

## Inactive Rules

Rules have an `is_active` flag. Set `is_active=False` to disable a rule without removing it:

```python
Rule(name="temp_disabled", rule_type="blocked_tool", config={"patterns": ["*"]}, is_active=False)
```
