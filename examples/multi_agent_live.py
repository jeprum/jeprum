#!/usr/bin/env python3
"""
Live Multi-Agent Simulation for Jeprum
Runs multiple concurrent agents with realistic violations and payments.
"""
import asyncio
import random
from datetime import datetime
from typing import Any

from jeprum import Jeprum
from jeprum.exceptions import GuardrailViolation, AgentKilled, AgentPaused


class MockMCPSession:
    """Simulates an MCP session with cost tracking."""
    
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.current_cost = 0.0
    
    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> Any:
        """Simulate tool execution."""
        await asyncio.sleep(random.uniform(0.1, 0.3))
        
        if tool_name == "payment_processor":
            return {"status": "success", "transaction_id": f"txn_{random.randint(1000, 9999)}"}
        elif tool_name == "database_query":
            return {"rows": random.randint(1, 100)}
        elif tool_name == "api_call":
            return {"response": "OK"}
        elif tool_name == "email_send":
            return {"sent": True}
        elif tool_name == "data_export":
            return {"exported": True}
        
        return {"result": "success"}


async def payment_agent():
    """High-volume payment processor - will exceed budget."""
    agent_id = "payment-processor-alpha"
    print(f"\n🚀 [{agent_id}] Starting...")
    
    jeprum = Jeprum(
        agent_id=agent_id,
        rules=["max_spend:50.00", "rate_limit:payment_processor:5/minute"],
        transport="cloud",
        api_key="jep_test_1234567890abcdef",
        cloud_url="https://jeprum-cloud.onrender.com",
    )
    
    session = MockMCPSession(agent_id)
    monitored = jeprum.monitor(session)
    
    payments = [
        (100, 8.50), (50, 4.25), (200, 12.00),
        (75, 6.30), (150, 9.80), (300, 15.00)
    ]
    
    try:
        for amount, cost in payments:
            try:
                # Monkey-patch the cost into the event
                original_call = monitored._session.call_tool
                
                async def call_with_cost(name, args):
                    result = await original_call(name, args)
                    # The event is created in call_tool, we need to set cost before evaluation
                    return result
                
                # Create event manually to set cost
                from jeprum.models import AgentEvent
                event = AgentEvent(
                    agent_id=agent_id,
                    event_type="tool_call",
                    tool_name="payment_processor",
                    input_params={"amount": amount},
                    estimated_cost_usd=cost,
                )
                
                # Evaluate guardrails first
                eval_result = monitored._rule_engine.evaluate(event)
                
                if eval_result.action in ("block", "kill"):
                    print(f"   🚫 [{agent_id}] BLOCKED: ${amount} payment (${cost}) - {eval_result.reason}")
                    monitored._rule_engine.record_event(event)
                    continue
                
                # Execute the call
                await monitored.call_tool("payment_processor", {"amount": amount})
                monitored._rule_engine.record_event(event)
                
                print(f"   ✅ [{agent_id}] Payment ${amount} processed (cost: ${cost:.2f})")
                await asyncio.sleep(2)
                
            except GuardrailViolation as e:
                print(f"   🚫 [{agent_id}] VIOLATION: {e}")
                
            except AgentKilled:
                print(f"   💀 [{agent_id}] KILLED")
                break
    
    finally:
        await jeprum.close_all()
        print(f"✨ [{agent_id}] Completed")


async def data_export_agent():
    """Data export agent - will hit rate limits."""
    agent_id = "data-exporter-beta"
    print(f"\n🚀 [{agent_id}] Starting...")
    
    jeprum = Jeprum(
        agent_id=agent_id,
        rules=["max_spend:100.00", "rate_limit:data_export:3/minute", "blocked_tool:file_write"],
        transport="cloud",
        api_key="jep_test_1234567890abcdef",
        cloud_url="https://jeprum-cloud.onrender.com",
    )
    
    session = MockMCPSession(agent_id)
    monitored = jeprum.monitor(session)
    
    exports = [
        ("csv", 5.00), ("json", 3.50), ("xml", 2.00),
        ("parquet", 6.00), ("avro", 4.50)
    ]
    
    try:
        for format_type, cost in exports:
            try:
                from jeprum.models import AgentEvent
                event = AgentEvent(
                    agent_id=agent_id,
                    event_type="tool_call",
                    tool_name="data_export",
                    input_params={"format": format_type},
                    estimated_cost_usd=cost,
                )
                
                eval_result = monitored._rule_engine.evaluate(event)
                
                if eval_result.action in ("block", "kill"):
                    print(f"   🚫 [{agent_id}] BLOCKED: {format_type} export (${cost}) - {eval_result.reason}")
                    monitored._rule_engine.record_event(event)
                    await asyncio.sleep(10)
                    continue
                
                await monitored.call_tool("data_export", {"format": format_type})
                monitored._rule_engine.record_event(event)
                
                print(f"   ✅ [{agent_id}] Exported {format_type} (cost: ${cost:.2f})")
                await asyncio.sleep(10)
                
            except GuardrailViolation as e:
                print(f"   🚫 [{agent_id}] VIOLATION: {e}")
                await asyncio.sleep(10)
        
        # Try blocked tool
        try:
            await monitored.call_tool("file_write", {"path": "/tmp/data.txt"})
        except GuardrailViolation as e:
            print(f"   🚫 [{agent_id}] BLOCKED TOOL: file_write - {e}")
    
    finally:
        await jeprum.close_all()
        print(f"✨ [{agent_id}] Completed")


async def api_caller_agent():
    """API integration agent - will exceed budget."""
    agent_id = "api-caller-gamma"
    print(f"\n🚀 [{agent_id}] Starting...")
    
    jeprum = Jeprum(
        agent_id=agent_id,
        rules=["max_spend:30.00", "alert_on:api_call"],
        transport="cloud",
        api_key="jep_test_1234567890abcdef",
        cloud_url="https://jeprum-cloud.onrender.com",
    )
    
    session = MockMCPSession(agent_id)
    monitored = jeprum.monitor(session)
    
    calls = [
        ("/users", 2.50), ("/products", 2.50), ("/analytics", 5.00),
        ("/reports", 3.50), ("/export", 8.00), ("/sync", 12.00)
    ]
    
    try:
        for endpoint, cost in calls:
            try:
                from jeprum.models import AgentEvent
                event = AgentEvent(
                    agent_id=agent_id,
                    event_type="tool_call",
                    tool_name="api_call",
                    input_params={"endpoint": endpoint},
                    estimated_cost_usd=cost,
                )
                
                eval_result = monitored._rule_engine.evaluate(event)
                
                if eval_result.action in ("block", "kill"):
                    print(f"   🚫 [{agent_id}] BLOCKED: {endpoint} (${cost}) - {eval_result.reason}")
                    monitored._rule_engine.record_event(event)
                    continue
                
                if eval_result.action in ("warn", "alert"):
                    print(f"   ⚠️  [{agent_id}] ALERT: {endpoint} (${cost})")
                
                await monitored.call_tool("api_call", {"endpoint": endpoint})
                monitored._rule_engine.record_event(event)
                
                print(f"   ✅ [{agent_id}] API call {endpoint} (cost: ${cost:.2f})")
                await asyncio.sleep(3)
                
            except GuardrailViolation as e:
                print(f"   🚫 [{agent_id}] VIOLATION: {e}")
    
    finally:
        await jeprum.close_all()
        print(f"✨ [{agent_id}] Completed")


async def main():
    """Run all agents concurrently."""
    print("\n" + "=" * 80)
    print("🤖  JEPRUM LIVE MULTI-AGENT SIMULATION")
    print("=" * 80)
    print(f"⏰  Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊  Dashboard: https://jeprum-cloud.onrender.com")
    print("=" * 80)
    
    # Run agents concurrently
    await asyncio.gather(
        payment_agent(),
        data_export_agent(),
        api_caller_agent(),
        return_exceptions=True
    )
    
    print("\n" + "=" * 80)
    print("✨  SIMULATION COMPLETE")
    print("=" * 80)
    print(f"⏰  Finished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"📊  View results: https://jeprum-cloud.onrender.com")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
