"""Jeprum — Main SDK entry point.

The Jeprum class is the public API that developers import and use.
It's a thin factory/convenience layer over JeprumInterceptor.

Usage:
    from jeprum import Jeprum

    jp = Jeprum()
    monitored = jp.monitor(my_mcp_session, rules={"max_spend_per_day": 10.0})
    result = await monitored.call_tool("search", {"query": "test"})
"""

from __future__ import annotations

import uuid
from typing import Any

from jeprum.interceptor import JeprumInterceptor
from jeprum.models import AgentConfig, AgentStatus, Rule


class Jeprum:
    """The live control room for AI agents.

    Create a Jeprum instance and call .monitor() to wrap any MCP session
    (or any object with a call_tool method) with monitoring and guardrails.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        transport_mode: str = "local",
        log_path: str = "jeprum_events.jsonl",
        cloud_endpoint: str = "https://api.jeprum.com",
        enabled: bool = True,
    ) -> None:
        self._api_key = api_key
        self._transport_mode = transport_mode
        self._log_path = log_path
        self._cloud_endpoint = cloud_endpoint
        self._enabled = enabled
        self._interceptors: list[JeprumInterceptor] = []

    def monitor(
        self,
        session: Any,
        *,
        rules: dict[str, Any] | list[Rule] | None = None,
        agent_name: str | None = None,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> JeprumInterceptor:
        """Wrap an MCP session with Jeprum monitoring and guardrails.

        Args:
            session: An MCP ClientSession or any object with a call_tool method.
            rules: Guardrail rules — either a dict (shorthand) or list of Rule objects.
            agent_name: Human-readable agent name.
            agent_id: Unique agent identifier (auto-generated if not provided).
            **kwargs: Additional AgentConfig overrides.

        Returns:
            A JeprumInterceptor with the same call_tool interface as the original session.
        """
        resolved_id = agent_id or str(uuid.uuid4())

        # Parse rules
        if isinstance(rules, dict):
            parsed_rules = self._parse_rules_shorthand(rules)
        elif isinstance(rules, list):
            parsed_rules = rules
        else:
            parsed_rules = []

        config = AgentConfig(
            agent_id=resolved_id,
            agent_name=agent_name,
            api_key=self._api_key,
            cloud_endpoint=self._cloud_endpoint,
            rules=parsed_rules,
            transport_mode=self._transport_mode,
            local_log_path=kwargs.get("log_path", self._log_path),
            batch_size=kwargs.get("batch_size", 10),
            batch_interval_seconds=kwargs.get("batch_interval_seconds", 2.0),
            poll_interval_seconds=kwargs.get("poll_interval_seconds", 10.0),
            enabled=self._enabled,
        )

        interceptor = JeprumInterceptor(session=session, config=config)
        self._interceptors.append(interceptor)
        return interceptor

    async def close_all(self) -> None:
        """Close all active interceptors and flush their transports."""
        for interceptor in self._interceptors:
            await interceptor.close()
        self._interceptors.clear()

    @staticmethod
    def _parse_rules_shorthand(rules_dict: dict[str, Any]) -> list[Rule]:
        """Convert a simple dict format into Rule objects.

        Supported keys:
            "max_spend_per_day": float
            "blocked_tools": list[str]
            "alert_on": list[str]
            "rate_limit": {"max_events": int, "period_seconds": int}
        """
        parsed: list[Rule] = []

        if "max_spend_per_day" in rules_dict:
            parsed.append(
                Rule(
                    name="max_spend_per_day",
                    rule_type="max_spend",
                    config={"max_usd": float(rules_dict["max_spend_per_day"]), "period": "day"},
                    action="block",
                )
            )

        if "blocked_tools" in rules_dict:
            patterns = rules_dict["blocked_tools"]
            if isinstance(patterns, str):
                patterns = [patterns]
            parsed.append(
                Rule(
                    name="blocked_tools",
                    rule_type="blocked_tool",
                    config={"patterns": patterns},
                    action="block",
                )
            )

        if "alert_on" in rules_dict:
            patterns = rules_dict["alert_on"]
            if isinstance(patterns, str):
                patterns = [patterns]
            parsed.append(
                Rule(
                    name="alert_on",
                    rule_type="alert_on",
                    config={"patterns": patterns},
                    action="alert",
                )
            )

        if "rate_limit" in rules_dict:
            rl_config = rules_dict["rate_limit"]
            if isinstance(rl_config, dict):
                parsed.append(
                    Rule(
                        name="rate_limit",
                        rule_type="rate_limit",
                        config={
                            "max_events": rl_config.get("max_events", 100),
                            "period_seconds": rl_config.get("period_seconds", 60),
                        },
                        action="block",
                    )
                )

        return parsed
