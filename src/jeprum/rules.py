"""Jeprum — Guardrail rule engine.

Evaluates agent events against a set of rules and returns allow/block/warn/alert/kill
decisions. Fully synchronous, pure in-memory logic. Must complete in <5ms per evaluation.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import date, datetime, timezone
from fnmatch import fnmatch
from typing import Any

from jeprum.models import AgentEvent, Rule, RuleEvalResult

logger = logging.getLogger("jeprum.rules")

# Priority ordering: higher number = more restrictive
_ACTION_PRIORITY: dict[str, int] = {
    "allow": 0,
    "alert": 1,
    "warn": 2,
    "block": 3,
    "kill": 4,
}


class RuleEngine:
    """Evaluates guardrail rules against agent events.

    Maintains internal state for spending tracking, event counts,
    and rate limiting. All operations are synchronous and in-memory.
    """

    def __init__(self, rules: list[Rule] | None = None) -> None:
        self._rules: list[Rule] = rules or []
        self._daily_spend: dict[str, float] = {}
        self._daily_event_count: dict[str, int] = {}
        self._last_reset_date: date = datetime.now(timezone.utc).date()
        # rate_limit tracking: agent_id -> deque of event timestamps
        self._rate_limit_windows: dict[str, deque[float]] = {}

    def evaluate(self, event: AgentEvent) -> RuleEvalResult:
        """Evaluate all active rules against an event.

        Returns the MOST restrictive result across all rules.
        If no rules match, returns allow.
        """
        self._maybe_reset_daily()

        most_restrictive = RuleEvalResult(
            rule_name="",
            action="allow",
            reason=None,
        )

        for rule in self._rules:
            if not rule.is_active:
                continue

            result = self._evaluate_rule(rule, event)
            if _ACTION_PRIORITY.get(result.action, 0) > _ACTION_PRIORITY.get(
                most_restrictive.action, 0
            ):
                most_restrictive = result

        return most_restrictive

    def record_event(self, event: AgentEvent) -> None:
        """Update internal tracking state after an event has been allowed.

        Called by the interceptor after successful tool call execution.
        """
        self._maybe_reset_daily()

        agent_id = event.agent_id

        # Track spending
        cost = event.estimated_cost_usd or 0.0
        self._daily_spend[agent_id] = self._daily_spend.get(agent_id, 0.0) + cost

        # Track event count
        self._daily_event_count[agent_id] = (
            self._daily_event_count.get(agent_id, 0) + 1
        )

        # Track rate limit window
        if agent_id not in self._rate_limit_windows:
            self._rate_limit_windows[agent_id] = deque()
        self._rate_limit_windows[agent_id].append(event.timestamp.timestamp())

    def reset_daily(self) -> None:
        """Reset daily counters. Can be called manually or automatically on date change."""
        self._daily_spend.clear()
        self._daily_event_count.clear()
        self._last_reset_date = datetime.now(timezone.utc).date()

    def get_daily_spend(self, agent_id: str) -> float:
        """Get the current daily spend for an agent."""
        self._maybe_reset_daily()
        return self._daily_spend.get(agent_id, 0.0)

    def get_daily_event_count(self, agent_id: str) -> int:
        """Get the current daily event count for an agent."""
        self._maybe_reset_daily()
        return self._daily_event_count.get(agent_id, 0)

    def _maybe_reset_daily(self) -> None:
        """Reset daily counters if the date has changed."""
        today = datetime.now(timezone.utc).date()
        if today != self._last_reset_date:
            self.reset_daily()

    def _evaluate_rule(self, rule: Rule, event: AgentEvent) -> RuleEvalResult:
        """Evaluate a single rule against an event."""
        evaluators = {
            "max_spend": self._eval_max_spend,
            "blocked_tool": self._eval_blocked_tool,
            "rate_limit": self._eval_rate_limit,
            "alert_on": self._eval_alert_on,
        }

        evaluator = evaluators.get(rule.rule_type)
        if evaluator is None:
            logger.warning("Unknown rule type: %s", rule.rule_type)
            return RuleEvalResult(rule_name=rule.name, action="allow")

        return evaluator(rule, event)

    def _eval_max_spend(self, rule: Rule, event: AgentEvent) -> RuleEvalResult:
        """Evaluate a max_spend rule."""
        max_usd = rule.config.get("max_usd", float("inf"))
        current_spend = self._daily_spend.get(event.agent_id, 0.0)
        event_cost = event.estimated_cost_usd or 0.0
        projected = current_spend + event_cost

        if projected > max_usd:
            return RuleEvalResult(
                rule_name=rule.name,
                action=rule.action,
                reason=(
                    f"Daily spend ${projected:.4f} would exceed limit ${max_usd:.2f} "
                    f"(current: ${current_spend:.4f}, this call: ${event_cost:.4f})"
                ),
            )

        return RuleEvalResult(rule_name=rule.name, action="allow")

    def _eval_blocked_tool(self, rule: Rule, event: AgentEvent) -> RuleEvalResult:
        """Evaluate a blocked_tool rule using fnmatch-style patterns."""
        patterns: list[str] = rule.config.get("patterns", [])

        for pattern in patterns:
            if fnmatch(event.tool_name, pattern):
                return RuleEvalResult(
                    rule_name=rule.name,
                    action=rule.action,
                    reason=f"Tool '{event.tool_name}' matches blocked pattern '{pattern}'",
                )

        return RuleEvalResult(rule_name=rule.name, action="allow")

    def _eval_rate_limit(self, rule: Rule, event: AgentEvent) -> RuleEvalResult:
        """Evaluate a rate_limit rule using a sliding window."""
        max_events = rule.config.get("max_events", 100)
        period_seconds = rule.config.get("period_seconds", 60)

        agent_id = event.agent_id
        now_ts = event.timestamp.timestamp()
        cutoff = now_ts - period_seconds

        window = self._rate_limit_windows.get(agent_id, deque())

        # Prune expired entries
        while window and window[0] < cutoff:
            window.popleft()

        if len(window) >= max_events:
            return RuleEvalResult(
                rule_name=rule.name,
                action=rule.action,
                reason=(
                    f"Rate limit exceeded: {len(window)} events in last "
                    f"{period_seconds}s (max: {max_events})"
                ),
            )

        return RuleEvalResult(rule_name=rule.name, action="allow")

    def _eval_alert_on(self, rule: Rule, event: AgentEvent) -> RuleEvalResult:
        """Evaluate an alert_on rule using fnmatch-style patterns."""
        patterns: list[str] = rule.config.get("patterns", [])

        for pattern in patterns:
            if fnmatch(event.tool_name, pattern):
                return RuleEvalResult(
                    rule_name=rule.name,
                    action="alert",
                    reason=f"Tool '{event.tool_name}' matches alert pattern '{pattern}'",
                )

        return RuleEvalResult(rule_name=rule.name, action="allow")
