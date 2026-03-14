"""Jeprum — Custom exceptions for the AI agent monitoring SDK."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from jeprum.models import AgentEvent


class JeprumError(Exception):
    """Base exception for all Jeprum errors."""


class GuardrailViolation(JeprumError):
    """Raised when an agent action is blocked by a guardrail rule.

    Attributes:
        rule_name: Name of the rule that triggered the violation.
        reason: Human-readable explanation of why the action was blocked.
        event: The AgentEvent that triggered the violation, if available.
    """

    def __init__(
        self,
        reason: str,
        rule_name: str = "",
        event: AgentEvent | None = None,
    ) -> None:
        self.rule_name = rule_name
        self.reason = reason
        self.event = event
        super().__init__(f"Guardrail violation [{rule_name}]: {reason}")


class AgentKilled(JeprumError):
    """Raised when an agent has been killed via the dashboard or API."""

    def __init__(self, agent_id: str = "") -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' has been killed")


class AgentPaused(JeprumError):
    """Raised when an agent has been paused via the dashboard or API."""

    def __init__(self, agent_id: str = "") -> None:
        self.agent_id = agent_id
        super().__init__(f"Agent '{agent_id}' has been paused")


class TransportError(JeprumError):
    """Raised when telemetry shipping fails.

    This is informational only — it should NEVER crash the agent.
    Callers should catch this and log a warning, not propagate it.
    """

    def __init__(self, message: str = "", cause: Exception | None = None) -> None:
        self.cause = cause
        super().__init__(f"Transport error: {message}")
