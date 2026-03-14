"""Jeprum — Pydantic v2 data models for events, rules, agent config, and status."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class AgentEvent(BaseModel):
    """Represents a single action taken by an agent."""

    id: UUID = Field(default_factory=uuid4)
    agent_id: str
    agent_name: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    event_type: Literal["tool_call", "tool_result", "error", "guardrail_trigger"] = "tool_call"
    tool_name: str
    input_params: dict[str, Any] = Field(default_factory=dict)
    output_result: Any = None
    duration_ms: float | None = None
    estimated_cost_usd: float | None = None
    guardrail_check: Literal["passed", "blocked", "warned", "skipped"] = "skipped"
    guardrail_details: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"ser_json_timedelta": "float"}

    def to_log_line(self) -> str:
        """Serialize the event to a JSON string suitable for JSONL file writing."""
        return self.model_dump_json()

    @classmethod
    def from_log_line(cls, line: str) -> AgentEvent:
        """Deserialize an AgentEvent from a JSON string."""
        return cls.model_validate_json(line.strip())


class Rule(BaseModel):
    """A guardrail rule that governs agent behavior."""

    id: UUID = Field(default_factory=uuid4)
    name: str
    rule_type: Literal["max_spend", "blocked_tool", "rate_limit", "alert_on"]
    config: dict[str, Any] = Field(default_factory=dict)
    action: Literal["block", "warn", "alert", "kill"] = "block"
    is_active: bool = True


class RuleEvalResult(BaseModel):
    """Result of evaluating a guardrail rule against an event."""

    rule_name: str
    action: Literal["allow", "block", "warn", "alert", "kill"]
    reason: str | None = None


class AgentConfig(BaseModel):
    """Configuration for a monitored agent."""

    agent_id: str
    agent_name: str | None = None
    api_key: str | None = None
    cloud_endpoint: str = "https://api.jeprum.com"
    rules: list[Rule] = Field(default_factory=list)
    transport_mode: Literal["local", "cloud", "both"] = "local"
    local_log_path: str = "jeprum_events.jsonl"
    batch_size: int = 10
    batch_interval_seconds: float = 2.0
    poll_interval_seconds: float = 10.0
    enabled: bool = True


class AgentStatus(BaseModel):
    """Current runtime status of a monitored agent."""

    agent_id: str
    status: Literal["active", "paused", "killed"] = "active"
    total_cost_today_usd: float = 0.0
    total_events_today: int = 0
    last_event_at: datetime | None = None
