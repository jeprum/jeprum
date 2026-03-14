"""Tests for Jeprum guardrail rule engine."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from jeprum.models import AgentEvent, Rule, RuleEvalResult
from jeprum.rules import RuleEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_event(
    tool_name: str = "search",
    agent_id: str = "agent-1",
    estimated_cost_usd: float | None = None,
    timestamp: datetime | None = None,
) -> AgentEvent:
    """Build a test AgentEvent with sensible defaults."""
    return AgentEvent(
        agent_id=agent_id,
        tool_name=tool_name,
        event_type="tool_call",
        estimated_cost_usd=estimated_cost_usd,
        timestamp=timestamp or datetime.now(timezone.utc),
    )


def make_rule(
    name: str = "test_rule",
    rule_type: str = "blocked_tool",
    config: dict | None = None,
    action: str = "block",
    is_active: bool = True,
) -> Rule:
    """Build a test Rule with sensible defaults."""
    return Rule(
        name=name,
        rule_type=rule_type,
        config=config or {},
        action=action,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# Tests: No rules
# ---------------------------------------------------------------------------

class TestNoRules:
    def test_no_rules_allows_everything(self) -> None:
        engine = RuleEngine(rules=[])
        event = make_event()
        result = engine.evaluate(event)
        assert result.action == "allow"

    def test_empty_init_allows_everything(self) -> None:
        engine = RuleEngine()
        event = make_event()
        result = engine.evaluate(event)
        assert result.action == "allow"


# ---------------------------------------------------------------------------
# Tests: max_spend
# ---------------------------------------------------------------------------

class TestMaxSpend:
    def test_under_budget_allows(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 10.0},
        )
        engine = RuleEngine(rules=[rule])
        event = make_event(estimated_cost_usd=1.0)
        result = engine.evaluate(event)
        assert result.action == "allow"

    def test_over_budget_blocks(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 10.0},
        )
        engine = RuleEngine(rules=[rule])

        # Record $9.50 of spending
        for _ in range(19):
            e = make_event(estimated_cost_usd=0.50)
            engine.record_event(e)

        # Next $1.00 should be blocked (total would be $10.50)
        event = make_event(estimated_cost_usd=1.0)
        result = engine.evaluate(event)
        assert result.action == "block"
        assert "exceed limit" in result.reason

    def test_exact_budget_allows(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 10.0},
        )
        engine = RuleEngine(rules=[rule])

        # Record $9.00
        for _ in range(9):
            e = make_event(estimated_cost_usd=1.0)
            engine.record_event(e)

        # $1.00 more = exactly $10.00, should still allow
        event = make_event(estimated_cost_usd=1.0)
        result = engine.evaluate(event)
        assert result.action == "allow"

    def test_zero_cost_event_always_allowed(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 0.0},
        )
        engine = RuleEngine(rules=[rule])
        event = make_event(estimated_cost_usd=0.0)
        result = engine.evaluate(event)
        assert result.action == "allow"

    def test_none_cost_treated_as_zero(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 10.0},
        )
        engine = RuleEngine(rules=[rule])
        event = make_event(estimated_cost_usd=None)
        result = engine.evaluate(event)
        assert result.action == "allow"

    def test_kill_action(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 1.0},
            action="kill",
        )
        engine = RuleEngine(rules=[rule])

        engine.record_event(make_event(estimated_cost_usd=1.0))

        event = make_event(estimated_cost_usd=0.50)
        result = engine.evaluate(event)
        assert result.action == "kill"


# ---------------------------------------------------------------------------
# Tests: blocked_tool
# ---------------------------------------------------------------------------

class TestBlockedTool:
    def test_exact_match_blocks(self) -> None:
        rule = make_rule(config={"patterns": ["delete_file"]})
        engine = RuleEngine(rules=[rule])
        result = engine.evaluate(make_event(tool_name="delete_file"))
        assert result.action == "block"

    def test_wildcard_match_blocks(self) -> None:
        rule = make_rule(config={"patterns": ["delete_*"]})
        engine = RuleEngine(rules=[rule])
        result = engine.evaluate(make_event(tool_name="delete_user"))
        assert result.action == "block"
        assert "delete_*" in result.reason

    def test_no_match_allows(self) -> None:
        rule = make_rule(config={"patterns": ["delete_*"]})
        engine = RuleEngine(rules=[rule])
        result = engine.evaluate(make_event(tool_name="read_file"))
        assert result.action == "allow"

    def test_multiple_patterns(self) -> None:
        rule = make_rule(config={"patterns": ["delete_*", "drop_*", "rm_*"]})
        engine = RuleEngine(rules=[rule])

        assert engine.evaluate(make_event(tool_name="delete_file")).action == "block"
        assert engine.evaluate(make_event(tool_name="drop_table")).action == "block"
        assert engine.evaluate(make_event(tool_name="rm_dir")).action == "block"
        assert engine.evaluate(make_event(tool_name="read_file")).action == "allow"

    def test_empty_patterns_allows_everything(self) -> None:
        rule = make_rule(config={"patterns": []})
        engine = RuleEngine(rules=[rule])
        result = engine.evaluate(make_event(tool_name="anything"))
        assert result.action == "allow"


# ---------------------------------------------------------------------------
# Tests: rate_limit
# ---------------------------------------------------------------------------

class TestRateLimit:
    def test_under_limit_allows(self) -> None:
        rule = make_rule(
            name="rate_limit",
            rule_type="rate_limit",
            config={"max_events": 5, "period_seconds": 60},
        )
        engine = RuleEngine(rules=[rule])
        now = datetime.now(timezone.utc)

        for i in range(4):
            e = make_event(timestamp=now + timedelta(seconds=i))
            engine.record_event(e)

        event = make_event(timestamp=now + timedelta(seconds=5))
        result = engine.evaluate(event)
        assert result.action == "allow"

    def test_at_limit_blocks(self) -> None:
        rule = make_rule(
            name="rate_limit",
            rule_type="rate_limit",
            config={"max_events": 5, "period_seconds": 60},
        )
        engine = RuleEngine(rules=[rule])
        now = datetime.now(timezone.utc)

        for i in range(5):
            e = make_event(timestamp=now + timedelta(seconds=i))
            engine.record_event(e)

        event = make_event(timestamp=now + timedelta(seconds=6))
        result = engine.evaluate(event)
        assert result.action == "block"
        assert "Rate limit exceeded" in result.reason

    def test_expired_events_dont_count(self) -> None:
        rule = make_rule(
            name="rate_limit",
            rule_type="rate_limit",
            config={"max_events": 5, "period_seconds": 60},
        )
        engine = RuleEngine(rules=[rule])
        now = datetime.now(timezone.utc)

        # Record 5 events 2 minutes ago
        for i in range(5):
            e = make_event(timestamp=now - timedelta(seconds=120) + timedelta(seconds=i))
            engine.record_event(e)

        # New event should be allowed (old ones expired)
        event = make_event(timestamp=now)
        result = engine.evaluate(event)
        assert result.action == "allow"


# ---------------------------------------------------------------------------
# Tests: alert_on
# ---------------------------------------------------------------------------

class TestAlertOn:
    def test_matching_pattern_alerts(self) -> None:
        rule = make_rule(
            name="payment_alert",
            rule_type="alert_on",
            config={"patterns": ["payment_*"]},
            action="alert",
        )
        engine = RuleEngine(rules=[rule])
        result = engine.evaluate(make_event(tool_name="payment_process"))
        assert result.action == "alert"
        assert "payment_*" in result.reason

    def test_no_match_allows(self) -> None:
        rule = make_rule(
            name="payment_alert",
            rule_type="alert_on",
            config={"patterns": ["payment_*"]},
            action="alert",
        )
        engine = RuleEngine(rules=[rule])
        result = engine.evaluate(make_event(tool_name="search"))
        assert result.action == "allow"


# ---------------------------------------------------------------------------
# Tests: Multiple rules, inactive rules, daily reset
# ---------------------------------------------------------------------------

class TestMultipleRules:
    def test_most_restrictive_wins(self) -> None:
        """When multiple rules match, the most restrictive action wins."""
        alert_rule = make_rule(
            name="alert_rule",
            rule_type="alert_on",
            config={"patterns": ["delete_*"]},
            action="alert",
        )
        block_rule = make_rule(
            name="block_rule",
            rule_type="blocked_tool",
            config={"patterns": ["delete_*"]},
            action="block",
        )
        engine = RuleEngine(rules=[alert_rule, block_rule])

        result = engine.evaluate(make_event(tool_name="delete_file"))
        assert result.action == "block"

    def test_inactive_rule_ignored(self) -> None:
        rule = make_rule(
            config={"patterns": ["delete_*"]},
            is_active=False,
        )
        engine = RuleEngine(rules=[rule])
        result = engine.evaluate(make_event(tool_name="delete_file"))
        assert result.action == "allow"

    def test_daily_reset_clears_spending(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 1.0},
        )
        engine = RuleEngine(rules=[rule])

        # Spend $0.90
        engine.record_event(make_event(estimated_cost_usd=0.90))
        assert engine.get_daily_spend("agent-1") == pytest.approx(0.90)

        # Reset
        engine.reset_daily()
        assert engine.get_daily_spend("agent-1") == 0.0

        # Should be allowed again
        event = make_event(estimated_cost_usd=0.50)
        result = engine.evaluate(event)
        assert result.action == "allow"

    def test_different_agents_tracked_separately(self) -> None:
        rule = make_rule(
            name="spend_limit",
            rule_type="max_spend",
            config={"max_usd": 1.0},
        )
        engine = RuleEngine(rules=[rule])

        # Agent 1 spends $0.90
        engine.record_event(make_event(agent_id="agent-1", estimated_cost_usd=0.90))

        # Agent 2 should still have budget
        event = make_event(agent_id="agent-2", estimated_cost_usd=0.50)
        result = engine.evaluate(event)
        assert result.action == "allow"

        # Agent 1 should be blocked
        event = make_event(agent_id="agent-1", estimated_cost_usd=0.50)
        result = engine.evaluate(event)
        assert result.action == "block"
