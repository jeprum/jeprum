#!/usr/bin/env python3
"""
Multi-Agent Simulation for Jeprum
Runs multiple concurrent agents with realistic violations, payments, and scenarios.
"""
import asyncio
import random
import time
from datetime import datetime
from typing import Any

from jeprum import Jeprum
from jeprum.exceptions import GuardrailViolation, AgentKilled, AgentPaused


class MockMCPSession:
    """Simulates an MCP session for testing."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
    
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Simulate tool execution with random delays."""
        await asyncio.sleep(random.uniform(0.1, 0.5))
        
        if tool_name == "payment_processor":
            return {"status": "success", "transaction_id": f"txn_{random.randint(1000, 9999)}"}
        elif tool_name == "database_query":
            return {"rows": random.randint(1, 100), "data": "..."}
        elif tool_name == "api_call":
            return {"response": "OK", "latency_ms": random.randint(50, 300)}
        elif tool_name == "file_write":
            return {"bytes_written": random.randint(100, 10000)}
        elif tool_name == "email_send":
            return {"sent": True, "message_id": f"msg_{random.randint(1000, 9999)}"}
        elif tool_name == "data_export":
            return {"exported": True, "file_size": random.randint(1000, 50000)}
        
        return {"result": "success"}


# Agent scenarios with different behaviors
AGENT_SCENARIOS = [
    {
        "name": "payment-processor-alpha",
        "description": "High-volume payment processor",
        "rules": [
            "max_spend:50.00",  # Will violate this
            "rate_limit:payment_processor:5/minute",
            "alert_on:payment_processor",
        ],
        "actions": [
            ("payment_processor", {"amount": 100, "currency": "USD"}, 8.50),
            ("payment_processor", {"amount": 50, "currency": "USD"}, 4.25),
            ("payment_processor", {"amount": 200, "currency": "USD"}, 12.00),
            ("payment_processor", {"amount": 75, "currency": "USD"}, 6.30),
            ("payment_processor", {"amount": 150, "currency": "USD"}, 9.80),
            ("payment_processor", {"amount": 300, "currency": "USD"}, 15.00),  # Will exceed budget
        ],
        "delay_between": 2,
    },
    {
        "name": "data-exporter-beta",
        "description": "Data export agent with rate limits",
        "rules": [
            "max_spend:100.00",
            "rate_limit:data_export:3/minute",  # Will violate this
            "blocked_tool:file_write",  # Will try to use this
        ],
        "actions": [
            ("data_export", {"format": "csv", "size": "large"}, 5.00),
            ("data_export", {"format": "json", "size": "medium"}, 3.50),
            ("data_export", {"format": "xml", "size": "small"}, 2.00),
            ("data_export", {"format": "parquet", "size": "large"}, 6.00),  # Rate limit violation
            ("file_write", {"path": "/tmp/data.txt"}, 0.50),  # Blocked tool
            ("data_export", {"format": "csv", "size": "huge"}, 8.00),
        ],
        "delay_between": 10,  # Faster to trigger rate limit
    },
    {
        "name": "api-caller-gamma",
        "description": "External API integration agent",
        "rules": [
            "max_spend:30.00",
            "alert_on:api_call",
            "rate_limit:api_call:10/minute",
        ],
        "actions": [
            ("api_call", {"endpoint": "/users", "method": "GET"}, 2.50),
            ("api_call", {"endpoint": "/products", "method": "GET"}, 2.50),
            ("database_query", {"table": "orders"}, 1.00),
            ("api_call", {"endpoint": "/analytics", "method": "POST"}, 5.00),
            ("api_call", {"endpoint": "/reports", "method": "GET"}, 3.50),
            ("api_call", {"endpoint": "/export", "method": "POST"}, 8.00),
            ("api_call", {"endpoint": "/sync", "method": "POST"}, 12.00),  # Will exceed budget
        ],
        "delay_between": 3,
    },
    {
        "name": "email-sender-delta",
        "description": "Email notification agent",
        "rules": [
            "max_spend:20.00",
            "rate_limit:email_send:5/minute",
            "alert_on:email_send",
        ],
        "actions": [
            ("email_send", {"to": "user1@example.com", "subject": "Welcome"}, 0.50),
            ("email_send", {"to": "user2@example.com", "subject": "Alert"}, 0.50),
            ("email_send", {"to": "user3@example.com", "subject": "Report"}, 0.50),
            ("email_send", {"to": "user4@example.com", "subject": "Update"}, 0.50),
            ("email_send", {"to": "user5@example.com", "subject": "Reminder"}, 0.50),
            ("email_send", {"to": "user6@example.com", "subject": "Notification"}, 0.50),  # Rate limit
            ("email_send", {"to": "user7@example.com", "subject": "Alert"}, 0.50),
        ],
        "delay_between": 8,
    },
    {
        "name": "database-worker-epsilon",
        "description": "Database operations agent",
        "rules": [
            "max_spend:40.00",
            "rate_limit:database_query:8/minute",
        ],
        "actions": [
            ("database_query", {"table": "users", "limit": 100}, 1.50),
            ("database_query", {"table": "orders", "limit": 500}, 3.00),
            ("database_query", {"table": "products", "limit": 200}, 2.00),
            ("database_query", {"table": "analytics", "limit": 1000}, 5.00),
            ("database_query", {"table": "logs", "limit": 5000}, 8.00),
            ("database_query", {"table": "reports", "limit": 2000}, 6.50),
            ("database_query", {"table": "metrics", "limit": 3000}, 7.00),
            ("database_query", {"table": "events", "limit": 10000}, 12.00),  # Will exceed budget
        ],
        "delay_between": 4,
    },
]


def print_banner():
    """Print simulation banner."""
    print("\n" + "=" * 80)
    print("🤖  JEPRUM MULTI-AGENT SIMULATION")
    print("=" * 80)
    print(f"⏰  Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"🎯  Agents: {len(AGENT_SCENARIOS)}")
    print(f"📊  Dashboard: https://jeprum-cloud.onrender.com")
    print("=" * 80 + "\n")


def print_agent_start(agent_name: str, description: str):
    """Print agent start message."""
    print(f"\n🚀 [{agent_name}] Starting: {description}")


def print_event(agent_name: str, event_type: str, tool_name: str, cost: float, status: str):
    """Print event details."""
    status_emoji = "✅" if status == "success" else "❌" if status == "blocked" else "⚠️"
    print(f"   {status_emoji} [{agent_name}] {event_type}: {tool_name} (${cost:.2f}) - {status}")


def print_violation(agent_name: str, violation_type: str, message: str):
    """Print violation details."""
    print(f"   🚫 [{agent_name}] VIOLATION: {violation_type} - {message}")


def print_agent_summary(agent_name: str, total_events: int, violations: int, total_cost: float):
    """Print agent summary."""
    print(f"\n📈 [{agent_name}] Summary:")
    print(f"   • Total Events: {total_events}")
    print(f"   • Violations: {violations}")
    print(f"   • Total Cost: ${total_cost:.2f}")


async def run_agent(scenario: dict):
    """Run a single agent with its scenario."""
    agent_name = scenario["name"]
    description = scenario["description"]
    rules = scenario["rules"]
    actions = scenario["actions"]
    delay_between = scenario["delay_between"]
    
    print_agent_start(agent_name, description)
    
    # Initialize Jeprum with cloud transport
    jeprum = Jeprum(
        agent_id=agent_name,
        rules=rules,
        transport="cloud",
        api_key="jep_test_1234567890abcdef",  # Use your actual API key
        cloud_url="https://jeprum-cloud.onrender.com",
    )
    
    # Create mock session
    session = MockMCPSession(agent_name)
    
    # Wrap session with Jeprum
    monitored_session = jeprum.monitor(session, estimated_cost_usd=0.0)
    
    total_events = 0
    violations = 0
    total_cost = 0.0
    
    try:
        for tool_name, arguments, cost in actions:
            try:
                # Update the cost for this call
                monitored_session.estimated_cost_usd = cost
                
                # Call the tool through Jeprum
                result = await monitored_session.call_tool(tool_name, arguments)
                
                total_events += 1
                total_cost += cost
                print_event(agent_name, "CALL", tool_name, cost, "success")
                
                # Wait between calls
                await asyncio.sleep(delay_between)
                
            except GuardrailViolation as e:
                violations += 1
                total_events += 1
                print_violation(agent_name, e.rule_type, str(e))
                
                # Continue after violation (except for blocked tools)
                if "blocked" not in str(e).lower():
                    await asyncio.sleep(delay_between)
                
            except AgentKilled:
                print(f"\n💀 [{agent_name}] KILLED by remote control")
                break
                
            except AgentPaused:
                print(f"\n⏸️  [{agent_name}] PAUSED by remote control")
                # In real scenario, would wait for resume
                await asyncio.sleep(5)
            
            except Exception as e:
                print(f"\n❌ [{agent_name}] ERROR: {type(e).__name__}: {e}")
                await asyncio.sleep(delay_between)
    
    finally:
        # Clean up
        await jeprum.close_all()
        print_agent_summary(agent_name, total_events, violations, total_cost)


async def main():
    """Run all agents concurrently."""
    print_banner()
    
    # Create tasks for all agents
    tasks = [run_agent(scenario) for scenario in AGENT_SCENARIOS]
    
    # Run all agents concurrently
    await asyncio.gather(*tasks, return_exceptions=True)
    
    print("\n" + "=" * 80)
    print("✨  SIMULATION COMPLETE")
    print("=" * 80)
    print(f"⏰  Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊  View results: https://jeprum-cloud.onrender.com")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
