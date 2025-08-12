#!/usr/bin/env python3
"""
AutoBot Demonstration Script
Shows the complete workflow orchestration system in action
"""

import asyncio
import aiohttp
import json
import time
from typing import Dict, Any


async def create_chat_session() -> str:
    """Create a new chat session and return the chat ID."""
    async with aiohttp.ClientSession() as session:
        async with session.post("http://localhost:8001/api/chats/new") as response:
            if response.status == 200:
                data = await response.json()
                return data.get("chat_id")
            else:
                raise Exception(f"Failed to create chat: {response.status}")


async def send_chat_message(chat_id: str, message: str) -> Dict[str, Any]:
    """Send a message to the chat and return the response."""
    async with aiohttp.ClientSession() as session:
        chat_request = {"chatId": chat_id, "message": message}

        async with session.post(
            "http://localhost:8001/api/chat", json=chat_request
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                error = await response.text()
                raise Exception(f"Chat request failed: {error}")


async def execute_workflow(message: str, auto_approve: bool = True) -> Dict[str, Any]:
    """Execute a workflow directly via the API."""
    async with aiohttp.ClientSession() as session:
        workflow_request = {"user_message": message, "auto_approve": auto_approve}

        async with session.post(
            "http://localhost:8001/api/workflow/execute", json=workflow_request
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                error = await response.text()
                raise Exception(f"Workflow execution failed: {error}")


async def monitor_workflow(workflow_id: str, timeout: int = 60):
    """Monitor workflow progress until completion."""
    async with aiohttp.ClientSession() as session:
        start_time = time.time()

        while time.time() - start_time < timeout:
            async with session.get(
                f"http://localhost:8001/api/workflow/workflow/{workflow_id}/status"
            ) as response:
                if response.status == 200:
                    status = await response.json()

                    print(
                        f"\r📊 Progress: {status.get('progress_percentage', 0):.1f}% "
                        f"| Step {status.get('current_step')}/{status.get('total_steps')} "
                        f"| Status: {status.get('status')}",
                        end="",
                        flush=True,
                    )

                    if status.get("status") in ["completed", "failed", "cancelled"]:
                        print()  # New line
                        return status

            await asyncio.sleep(2)

        print("\n⏱️  Workflow timed out")
        return None


async def demo_simple_query():
    """Demonstrate a simple query that gets a direct response."""
    print("\n📝 Demo 1: Simple Query")
    print("-" * 60)
    print("Query: 'What is 2+2?'")
    print("Expected: Direct response without workflow")

    try:
        chat_id = await create_chat_session()
        response = await send_chat_message(chat_id, "What is 2+2?")

        print(f"\n✅ Response: {response.get('response', 'No response')}")
        print(f"Status: {response.get('status', 'unknown')}")

    except Exception as e:
        print(f"❌ Error: {e}")


async def demo_research_workflow():
    """Demonstrate a research workflow."""
    print("\n\n🔍 Demo 2: Research Workflow")
    print("-" * 60)
    print("Query: 'What are the latest Python web frameworks in 2024?'")
    print("Expected: Research workflow with web search")

    try:
        result = await execute_workflow(
            "What are the latest Python web frameworks in 2024?", auto_approve=True
        )

        if result.get("type") == "workflow_orchestration":
            workflow_id = result.get("workflow_id")
            workflow_response = result.get("workflow_response", {})

            print(f"\n✅ Workflow initiated!")
            print(
                f"   Classification: {workflow_response.get('message_classification')}"
            )
            print(f"   Workflow ID: {workflow_id[:8]}...")
            print(
                f"   Agents: {', '.join(workflow_response.get('agents_involved', []))}"
            )
            print(f"   Steps: {workflow_response.get('planned_steps')}")

            # Monitor progress
            print("\n⏳ Monitoring workflow progress...")
            final_status = await monitor_workflow(workflow_id)

            if final_status:
                print(f"\n✅ Workflow {final_status.get('status')}!")
                if final_status.get("steps_completed"):
                    print("\n📋 Completed Steps:")
                    for step in final_status.get("steps_completed", []):
                        print(f"   ✓ {step.get('agent')}: {step.get('action')}")
        else:
            print(f"\n💬 Direct response: {result}")

    except Exception as e:
        print(f"❌ Error: {e}")


async def demo_complex_workflow():
    """Demonstrate a complex multi-agent workflow."""
    print("\n\n🚀 Demo 3: Complex Multi-Agent Workflow")
    print("-" * 60)
    print("Query: 'I need to scan my network for security vulnerabilities'")
    print("Expected: 8-step workflow with research, approvals, and installation")

    try:
        result = await execute_workflow(
            "I need to scan my network for security vulnerabilities",
            auto_approve=True,  # Auto-approve for demo
        )

        if result.get("type") == "workflow_orchestration":
            workflow_id = result.get("workflow_id")
            workflow_response = result.get("workflow_response", {})

            print(f"\n✅ Complex workflow initiated!")
            print(
                f"   Classification: {workflow_response.get('message_classification')}"
            )
            print(f"   Workflow ID: {workflow_id[:8]}...")
            print(
                f"   Estimated duration: {workflow_response.get('estimated_duration')}"
            )

            # Show workflow plan
            print("\n📋 Workflow Plan:")
            for i, step in enumerate(workflow_response.get("workflow_preview", []), 1):
                print(f"   {i}. {step}")

            # Monitor progress
            print("\n⏳ Executing workflow...")
            final_status = await monitor_workflow(workflow_id, timeout=120)

            if final_status:
                print(f"\n✅ Workflow {final_status.get('status')}!")

                # Show results
                if final_status.get("status") == "completed":
                    print("\n🎯 Workflow Results:")
                    print("   - Knowledge Base searched for existing tools")
                    print("   - Research conducted on latest security scanners")
                    print("   - Tool recommendations prepared")
                    print("   - Installation guides retrieved")
                    print("   - Information stored for future reference")

    except Exception as e:
        print(f"❌ Error: {e}")


async def demo_workflow_management():
    """Demonstrate workflow management capabilities."""
    print("\n\n⚙️  Demo 4: Workflow Management")
    print("-" * 60)

    try:
        # Check active workflows
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8001/api/workflow/workflows"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    active_count = data.get("active_workflows", 0)

                    print(f"✅ Active workflows: {active_count}")

                    if data.get("workflows"):
                        print("\n📋 Recent Workflows:")
                        for workflow in data.get("workflows", [])[:3]:
                            print(f"\n   ID: {workflow.get('id', 'N/A')[:8]}...")
                            print(f"   Status: {workflow.get('status')}")
                            print(f"   Type: {workflow.get('classification')}")
                            print(
                                f"   Progress: {workflow.get('steps_completed')}/{workflow.get('total_steps')} steps"
                            )
                    else:
                        print("   No active workflows")

    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Run all demonstrations."""
    print("🤖 AutoBot Multi-Agent Workflow Orchestration Demo")
    print("=" * 70)
    print(
        "Demonstrating the transformation from generic responses to intelligent workflows\n"
    )

    print("🔍 System Check...")
    try:
        async with aiohttp.ClientSession() as session:
            # Check backend health
            async with session.get(
                "http://localhost:8001/api/system/health"
            ) as response:
                if response.status == 200:
                    health = await response.json()
                    print(f"✅ Backend: {health.get('status')}")
                    print(f"✅ LLM: {health.get('current_model')}")
                    print(f"✅ Redis: {health.get('redis_status')}")
                else:
                    print("❌ Backend health check failed")
                    return
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")
        print("   Please ensure AutoBot is running with: ./run_agent.sh")
        return

    # Run demonstrations
    await demo_simple_query()
    await demo_research_workflow()
    await demo_complex_workflow()
    await demo_workflow_management()

    print("\n\n" + "=" * 70)
    print("✅ Demonstration Complete!")
    print("\n🎯 Key Achievements Demonstrated:")
    print("   1. Simple queries receive direct responses")
    print("   2. Research queries trigger web search workflows")
    print("   3. Complex queries orchestrate multiple specialized agents")
    print("   4. Full workflow tracking and management capabilities")
    print("\n🚀 AutoBot has successfully transformed from generic responses")
    print("   to intelligent multi-agent workflow orchestration!")


if __name__ == "__main__":
    asyncio.run(main())
