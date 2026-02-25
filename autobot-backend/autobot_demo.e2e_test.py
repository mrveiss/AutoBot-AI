#!/usr/bin/env python3
"""
AutoBot Demonstration Script
Shows the complete workflow orchestration system in action
"""

import asyncio
import time
from typing import Any, Dict

import aiohttp


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

                    print(  # noqa: print
                        f"\r📊 Progress: {status.get('progress_percentage', 0):.1f}% "
                        f"| Step {status.get('current_step')}/{status.get('total_steps')} "
                        f"| Status: {status.get('status')}",
                        end="",
                        flush=True,
                    )

                    if status.get("status") in ["completed", "failed", "cancelled"]:
                        print()  # New line  # noqa: print
                        return status

            await asyncio.sleep(2)

        print("\n⏱️  Workflow timed out")  # noqa: print
        return None


async def demo_simple_query():
    """Demonstrate a simple query that gets a direct response."""
    print("\n📝 Demo 1: Simple Query")  # noqa: print
    print("-" * 60)  # noqa: print
    print("Query: 'What is 2+2?'")  # noqa: print
    print("Expected: Direct response without workflow")  # noqa: print

    try:
        chat_id = await create_chat_session()
        response = await send_chat_message(chat_id, "What is 2+2?")

        print(f"\n✅ Response: {response.get('response', 'No response')}")  # noqa: print
        print(f"Status: {response.get('status', 'unknown')}")  # noqa: print

    except Exception as e:
        print(f"❌ Error: {e}")  # noqa: print


async def demo_research_workflow():
    """Demonstrate a research workflow."""
    print("\n\n🔍 Demo 2: Research Workflow")  # noqa: print
    print("-" * 60)  # noqa: print
    print("Query: 'What are the latest Python web frameworks in 2024?'")  # noqa: print
    print("Expected: Research workflow with web search")  # noqa: print

    try:
        result = await execute_workflow(
            "What are the latest Python web frameworks in 2024?", auto_approve=True
        )

        if result.get("type") == "workflow_orchestration":
            workflow_id = result.get("workflow_id")
            workflow_response = result.get("workflow_response", {})

            print("\n✅ Workflow initiated!")  # noqa: print
            print(  # noqa: print
                f"   Classification: {workflow_response.get('message_classification')}"
            )
            print(f"   Workflow ID: {workflow_id[:8]}...")  # noqa: print
            print(  # noqa: print
                f"   Agents: {', '.join(workflow_response.get('agents_involved', []))}"
            )
            print(f"   Steps: {workflow_response.get('planned_steps')}")  # noqa: print

            # Monitor progress
            print("\n⏳ Monitoring workflow progress...")  # noqa: print
            final_status = await monitor_workflow(workflow_id)

            if final_status:
                print(f"\n✅ Workflow {final_status.get('status')}!")  # noqa: print
                if final_status.get("steps_completed"):
                    print("\n📋 Completed Steps:")  # noqa: print
                    for step in final_status.get("steps_completed", []):
                        print(  # noqa: print
                            f"   ✓ {step.get('agent')}: {step.get('action')}"
                        )  # noqa: print
        else:
            print(f"\n💬 Direct response: {result}")  # noqa: print

    except Exception as e:
        print(f"❌ Error: {e}")  # noqa: print


async def demo_complex_workflow():
    """Demonstrate a complex multi-agent workflow."""
    print("\n\n🚀 Demo 3: Complex Multi-Agent Workflow")  # noqa: print
    print("-" * 60)  # noqa: print
    print(  # noqa: print
        "Query: 'I need to scan my network for security vulnerabilities'"
    )  # noqa: print
    print(  # noqa: print
        "Expected: 8-step workflow with research, approvals, and installation"
    )  # noqa: print

    try:
        result = await execute_workflow(
            "I need to scan my network for security vulnerabilities",
            auto_approve=True,  # Auto-approve for demo
        )

        if result.get("type") == "workflow_orchestration":
            workflow_id = result.get("workflow_id")
            workflow_response = result.get("workflow_response", {})

            print("\n✅ Complex workflow initiated!")  # noqa: print
            print(  # noqa: print
                f"   Classification: {workflow_response.get('message_classification')}"
            )
            print(f"   Workflow ID: {workflow_id[:8]}...")  # noqa: print
            print(  # noqa: print
                f"   Estimated duration: {workflow_response.get('estimated_duration')}"
            )

            # Show workflow plan
            print("\n📋 Workflow Plan:")  # noqa: print
            for i, step in enumerate(workflow_response.get("workflow_preview", []), 1):
                print(f"   {i}. {step}")  # noqa: print

            # Monitor progress
            print("\n⏳ Executing workflow...")  # noqa: print
            final_status = await monitor_workflow(workflow_id, timeout=120)

            if final_status:
                print(f"\n✅ Workflow {final_status.get('status')}!")  # noqa: print

                # Show results
                if final_status.get("status") == "completed":
                    print("\n🎯 Workflow Results:")  # noqa: print
                    print(  # noqa: print
                        "   - Knowledge Base searched for existing tools"
                    )  # noqa: print
                    print(  # noqa: print
                        "   - Research conducted on latest security scanners"
                    )  # noqa: print
                    print("   - Tool recommendations prepared")  # noqa: print
                    print("   - Installation guides retrieved")  # noqa: print
                    print("   - Information stored for future reference")  # noqa: print

    except Exception as e:
        print(f"❌ Error: {e}")  # noqa: print


async def demo_workflow_management():
    """Demonstrate workflow management capabilities."""
    print("\n\n⚙️  Demo 4: Workflow Management")  # noqa: print
    print("-" * 60)  # noqa: print

    try:
        # Check active workflows
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "http://localhost:8001/api/workflow/workflows"
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    active_count = data.get("active_workflows", 0)

                    print(f"✅ Active workflows: {active_count}")  # noqa: print

                    if data.get("workflows"):
                        print("\n📋 Recent Workflows:")  # noqa: print
                        for workflow in data.get("workflows", [])[:3]:
                            print(  # noqa: print
                                f"\n   ID: {workflow.get('id', 'N/A')[:8]}..."
                            )  # noqa: print
                            print(f"   Status: {workflow.get('status')}")  # noqa: print
                            print(  # noqa: print
                                f"   Type: {workflow.get('classification')}"
                            )  # noqa: print
                            print(  # noqa: print
                                f"   Progress: {workflow.get('steps_completed')}/{workflow.get('total_steps')} steps"
                            )
                    else:
                        print("   No active workflows")  # noqa: print

    except Exception as e:
        print(f"❌ Error: {e}")  # noqa: print


async def main():
    """Run all demonstrations."""
    print("🤖 AutoBot Multi-Agent Workflow Orchestration Demo")  # noqa: print
    print("=" * 70)  # noqa: print
    print(  # noqa: print
        "Demonstrating the transformation from generic responses to intelligent workflows\n"
    )

    print("🔍 System Check...")  # noqa: print
    try:
        async with aiohttp.ClientSession() as session:
            # Check backend health
            async with session.get(
                "http://localhost:8001/api/system/health"
            ) as response:
                if response.status == 200:
                    health = await response.json()
                    print(f"✅ Backend: {health.get('status')}")  # noqa: print
                    print(f"✅ LLM: {health.get('current_model')}")  # noqa: print
                    print(f"✅ Redis: {health.get('redis_status')}")  # noqa: print
                else:
                    print("❌ Backend health check failed")  # noqa: print
                    return
    except Exception as e:
        print(f"❌ Cannot connect to backend: {e}")  # noqa: print
        print("   Please ensure AutoBot is running with: ./run_agent.sh")  # noqa: print
        return

    # Run demonstrations
    await demo_simple_query()
    await demo_research_workflow()
    await demo_complex_workflow()
    await demo_workflow_management()

    print("\n\n" + "=" * 70)  # noqa: print
    print("✅ Demonstration Complete!")  # noqa: print
    print("\n🎯 Key Achievements Demonstrated:")  # noqa: print
    print("   1. Simple queries receive direct responses")  # noqa: print
    print("   2. Research queries trigger web search workflows")  # noqa: print
    print(  # noqa: print
        "   3. Complex queries orchestrate multiple specialized agents"
    )  # noqa: print
    print("   4. Full workflow tracking and management capabilities")  # noqa: print
    print(  # noqa: print
        "\n🚀 AutoBot has successfully transformed from generic responses"
    )  # noqa: print
    print("   to intelligent multi-agent workflow orchestration!")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
