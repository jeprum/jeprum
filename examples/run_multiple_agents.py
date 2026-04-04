#!/usr/bin/env python3
"""
Multi-Agent Simulation - Realistic violations and payments
Demonstrates 3 concurrent agents with different behaviors and guardrails.
"""
import asyncio
import random
from datetime import datetime
from typing import Any

from jeprum import Jeprum
from jeprum.exceptions import GuardrailViolation, AgentKilled, AgentPaused
from jeprum.models import AgentEvent


class MockMCPSession:
    """Mock MCP session for testing."""
    
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        await asyncio.sleep(random.uniform(0.05, 0.15))
        return {"status": "success", "tool": tool_name}


async def payment_processor_agent():
    """Payment processor - will exceed $50 budget."""
    agent_id = "payment-processor-001"
    print(f"\n🚀 Starting {agent_id}")
    
    jeprum = Jeprum(
        transport_mode="cloud",
        api_key="jp_live_d274d7067f14674d8e71699fcc9dab3feba4dc86298325c2f8283705629691fe",
        cloud_endpoint="https://jeprum-cloud.onrender.com",
    )
    
    session = MockMCPSession()
    agent = jeprum.monitor(
        session,
        agent_id=agent_id,
        agent_name="Payment Processor",
        rules={
            "max_spend_per_day": 50.00,
            "rate_limit": {"max_events": 5, "period_seconds": 60},
        },
    )
    
    # Payment transactions with costs
    transactions = [
        ("payment", {"amount": 100}, 8.50),
        ("payment", {"amount": 50}, 4.25),
        ("payment", {"amount": 200}, 12.00),
        ("payment", {"amount": 75}, 6.30),
        ("payment", {"amount": 150}, 9.80),
        ("payment", {"amount": 300}, 15.00),  # Will exceed budget
    ]
    
    total_cost = 0.0
    violations = 0
    
    try:
        for tool_name, args, cost in transactions:
            # Pre-check with cost
            check_event = AgentEvent(
                agent_id=agent_id,
                tool_name=tool_name,
                estimated_cost_usd=cost,
            )
            result = agent._rule_engine.evaluate(check_event)
            
            if result.action in ("block", "kill"):
                violations += 1
                print(f"   🚫 {agent_id}: ${args['amount']} payment BLOCKED (${cost:.2f}) - {result.reason}")
                continue
            
            try:
                await agent.call_tool(tool_name, args)
                
                # Record the cost
                cost_event = AgentEvent(
                    agent_id=agent_id,
                    tool_name=tool_name,
                    estimated_cost_usd=cost,
                )
                agent._rule_engine.record_event(cost_event)
                total_cost += cost
                
                print(f"   ✅ {agent_id}: ${args['amount']} payment processed (${cost:.2f})")
                await asyncio.sleep(2)
                
            except GuardrailViolation as e:
                violations += 1
                print(f"   🚫 {agent_id}: VIOLATION - {e.reason}")
            except AgentKilled:
                print(f"   💀 {agent_id}: KILLED")
                break
    
    finally:
        await jeprum.close_all()
        print(f"✨ {agent_id}: Done - ${total_cost:.2f} spent, {violations} violations")


async def data_export_agent():
    """Data exporter - will hit rate limits and blocked tools."""
    agent_id = "data-exporter-002"
    print(f"\n🚀 Starting {agent_id}")
    
    jeprum = Jeprum(
        transport_mode="cloud",
        api_key="jp_live_d274d7067f14674d8e71699fcc9dab3feba4dc86298325c2f8283705629691fe",
        cloud_endpoint="https://jeprum-cloud.onrender.com",
    )
    
    session = MockMCPSession()
    agent = jeprum.monitor(
        session,
        agent_id=agent_id,
        agent_name="Data Exporter",
        rules={
            "max_spend_per_day": 100.00,
            "rate_limit": {"max_events": 3, "period_seconds": 60},
            "blocked_tools": ["delete_data"],
        },
    )
    
    operations = [
        ("export", {"format": "csv"}, 5.00),
        ("export", {"format": "json"}, 3.50),
        ("export", {"format": "xml"}, 2.00),
        ("export", {"format": "parquet"}, 6.00),  # Will hit rate limit
        ("delete_data", {"table": "old_records"}, 1.00),  # Blocked tool
        ("export", {"format": "avro"}, 4.50),
    ]
    
    total_cost = 0.0
    violations = 0
    
    try:
        for tool_name, args, cost in operations:
            check_event = AgentEvent(
                agent_id=agent_id,
                tool_name=tool_name,
                estimated_cost_usd=cost,
            )
            result = agent._rule_engine.evaluate(check_event)
            
            if result.action in ("block", "kill"):
                violations += 1
                print(f"   🚫 {agent_id}: {tool_name} BLOCKED - {result.reason}")
                await asyncio.sleep(8)  # Wait before retry
                continue
            
            try:
                await agent.call_tool(tool_name, args)
                
                cost_event = AgentEvent(
                    agent_id=agent_id,
                    tool_name=tool_name,
                    estimated_cost_usd=cost,
                )
                agent._rule_engine.record_event(cost_event)
                total_cost += cost
                
                print(f"   ✅ {agent_id}: {tool_name} {args.get('format', '')} (${cost:.2f})")
                await asyncio.sleep(8)
                
            except GuardrailViolation as e:
                violations += 1
                print(f"   🚫 {agent_id}: VIOLATION - {e.reason}")
                await asyncio.sleep(8)
    
    finally:
        await jeprum.close_all()
        print(f"✨ {agent_id}: Done - ${total_cost:.2f} spent, {violations} violations")


async def api_integration_agent():
    """API caller - will exceed budget and trigger alerts."""
    agent_id = "api-caller-003"
    print(f"\n🚀 Starting {agent_id}")
    
    jeprum = Jeprum(
        transport_mode="cloud",
        api_key="jp_live_d274d7067f14674d8e71699fcc9dab3feba4dc86298325c2f8283705629691fe",
        cloud_endpoint="https://jeprum-cloud.onrender.com",
    )
    
    session = MockMCPSession()
    agent = jeprum.monitor(
        session,
        agent_id=agent_id,
        agent_name="API Integration",
        rules={
            "max_spend_per_day": 30.00,
            "alert_on": ["api_call"],
        },
    )
    
    api_calls = [
        ("api_call", {"endpoint": "/users"}, 2.50),
        ("api_call", {"endpoint": "/products"}, 2.50),
        ("api_call", {"endpoint": "/analytics"}, 5.00),
        ("api_call", {"endpoint": "/reports"}, 3.50),
        ("api_call", {"endpoint": "/export"}, 8.00),
        ("api_call", {"endpoint": "/sync"}, 12.00),  # Will exceed budget
    ]
    
    total_cost = 0.0
    violations = 0
    alerts = 0
    
    try:
        for tool_name, args, cost in api_calls:
            check_event = AgentEvent(
                agent_id=agent_id,
                tool_name=tool_name,
                estimated_cost_usd=cost,
            )
            result = agent._rule_engine.evaluate(check_event)
            
            if result.action in ("block", "kill"):
                violations += 1
                print(f"   🚫 {agent_id}: {args['endpoint']} BLOCKED (${cost:.2f}) - {result.reason}")
                continue
            
            if result.action in ("warn", "alert"):
                alerts += 1
                print(f"   ⚠️  {agent_id}: {args['endpoint']} ALERT")
            
            try:
                await agent.call_tool(tool_name, args)
                
                cost_event = AgentEvent(
                    agent_id=agent_id,
                    tool_name=tool_name,
                    estimated_cost_usd=cost,
                )
                agent._rule_engine.record_event(cost_event)
                total_cost += cost
                
                print(f"   ✅ {agent_id}: {args['endpoint']} (${cost:.2f})")
                await asyncio.sleep(3)
                
            except GuardrailViolation as e:
                violations += 1
                print(f"   🚫 {agent_id}: VIOLATION - {e.reason}")
    
    finally:
        await jeprum.close_all()
        print(f"✨ {agent_id}: Done - ${total_cost:.2f} spent, {violations} violations, {alerts} alerts")


async def main():
    print("\n" + "=" * 80)
    print("🤖  JEPRUM MULTI-AGENT SIMULATION")
    print("=" * 80)
    print(f"⏰  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊  Dashboard: https://jeprum-cloud.onrender.com")
    print(f"🎯  Running 3 agents with realistic violations...")
    print("=" * 80)
    
    # Run all agents concurrently
    results = await asyncio.gather(
        payment_processor_agent(),
        data_export_agent(),
        api_integration_agent(),
        return_exceptions=True
    )
    
    # Check for errors
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"\n❌ Agent {i} failed with error: {type(result).__name__}: {result}")
            import traceback
            traceback.print_exception(type(result), result, result.__traceback__)
    
    print("\n" + "=" * 80)
    print("✨  SIMULATION COMPLETE")
    print("=" * 80)
    print(f"⏰  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊  Check dashboard: https://jeprum-cloud.onrender.com")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
