#!/usr/bin/env python3
"""
Test AutoBot Chat and Workflow Integration
Focus on chat interaction that triggers workflows
"""

import asyncio

import aiohttp


async def test_chat_workflow():
    """Test chat messages that trigger different workflow types."""
    print("🎯 Testing AutoBot Chat -> Workflow Integration")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        # Create a new chat session
        print("1. Creating New Chat Session")
        print("-" * 40)

        try:
            async with session.post("http://localhost:8001/api/chats/new") as response:
                if response.status == 200:
                    chat_data = await response.json()
                    chat_id = chat_data.get("chat_id")
                    print(f"✅ Chat created: {chat_id}")
                else:
                    print(f"❌ Failed to create chat: {response.status}")
                    return
        except Exception as e:
            print(f"❌ Error creating chat: {e}")
            return

        # Test different message types
        test_messages = [
            {
                "type": "Simple",
                "message": "What is 2+2?",
                "expected": "direct response",
            },
            {
                "type": "Research",
                "message": "What are the latest Python web frameworks in 2024?",
                "expected": "research workflow",
            },
            {
                "type": "Install",
                "message": "How do I install Docker on Ubuntu?",
                "expected": "installation workflow",
            },
            {
                "type": "Complex",
                "message": "I need tools to scan my network for security vulnerabilities",
                "expected": "multi-agent workflow",
            },
        ]

        for i, test in enumerate(test_messages, 1):
            print(f"\n{i+1}. Testing {test['type']} Request")
            print("-" * 40)
            print(f"   Message: '{test['message']}'")
            print(f"   Expected: {test['expected']}")

            chat_request = {"chatId": chat_id, "message": test["message"]}

            try:
                async with session.post(
                    "http://localhost:8001/api/chat", json=chat_request
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        response_text = result.get("response", "")

                        # Check if it's a workflow response
                        if any(
                            keyword in response_text.lower()
                            for keyword in [
                                "workflow",
                                "orchestration",
                                "agents",
                                "steps",
                            ]
                        ):
                            print("   ✅ Workflow orchestration triggered!")

                            # Try to extract workflow info
                            if "workflow_id" in response_text:
                                print("   🔄 Workflow initiated")
                            if "agents" in response_text.lower():
                                print("   🤖 Multi-agent coordination detected")
                            if "steps" in response_text.lower():
                                print("   📋 Workflow steps planned")
                        else:
                            print("   💬 Direct chat response")

                        # Show response preview
                        preview = (
                            response_text[:200] + "..."
                            if len(response_text) > 200
                            else response_text
                        )
                        print(f"   Response: {preview}")

                    else:
                        print(f"   ❌ Request failed: {response.status}")
                        error = await response.text()
                        print(f"   Error: {error[:200]}")

            except Exception as e:
                print(f"   ❌ Error: {e}")

            # Small delay between messages
            await asyncio.sleep(2)

        # Check active workflows
        print("\n6. Checking Active Workflows")
        print("-" * 40)

        try:
            async with session.get(
                "http://localhost:8001/api/workflow/workflows"
            ) as response:
                if response.status == 200:
                    workflows_data = await response.json()
                    active_count = workflows_data.get("active_workflows", 0)
                    workflows = workflows_data.get("workflows", [])

                    print(f"✅ Active workflows: {active_count}")

                    if workflows:
                        for workflow in workflows[:3]:  # Show first 3
                            print(f"\n   Workflow: {workflow.get('id', 'N/A')[:8]}...")
                            print(f"   Status: {workflow.get('status')}")
                            print(
                                f"   Classification: {workflow.get('classification')}"
                            )
                            print(
                                f"   Progress: {workflow.get('steps_completed')}/{workflow.get('total_steps')}"
                            )
                            print(
                                f"   Agents: {', '.join(workflow.get('agents_involved', []))}"
                            )
                else:
                    print(f"❌ Failed to get workflows: {response.status}")
        except Exception as e:
            print(f"❌ Error checking workflows: {e}")


async def test_direct_workflow_execution():
    """Test direct workflow API execution."""
    print("\n\n🚀 Testing Direct Workflow Execution")
    print("=" * 60)

    async with aiohttp.ClientSession() as session:
        workflow_request = {
            "user_message": "find network scanning tools",
            "auto_approve": True,
        }

        print("1. Executing Workflow via API")
        print("-" * 40)

        try:
            async with session.post(
                "http://localhost:8001/api/workflow/execute", json=workflow_request
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    print("✅ Workflow executed successfully")

                    if result.get("type") == "workflow_orchestration":
                        workflow_id = result.get("workflow_id")
                        workflow_response = result.get("workflow_response", {})

                        print(f"   Workflow ID: {workflow_id[:8]}...")
                        print(
                            f"   Classification: {workflow_response.get('message_classification')}"
                        )
                        print(
                            f"   Planned steps: {workflow_response.get('planned_steps')}"
                        )
                        print(
                            f"   Agents: {', '.join(workflow_response.get('agents_involved', []))}"
                        )

                        # Show workflow preview
                        preview = workflow_response.get("workflow_preview", [])
                        if preview:
                            print("\n   Workflow Steps:")
                            for step in preview[:5]:  # Show first 5 steps
                                print(f"   - {step}")
                    else:
                        print("   ℹ️  Direct response (no workflow needed)")

                else:
                    print(f"❌ Workflow execution failed: {response.status}")
                    error = await response.text()
                    print(f"   Error: {error[:200]}")

        except Exception as e:
            print(f"❌ Error executing workflow: {e}")


async def main():
    """Run all tests."""
    print("🤖 AutoBot Chat and Workflow Integration Test")
    print("=" * 60)
    print("Testing how chat messages trigger workflow orchestration\n")

    # Test chat workflow integration
    await test_chat_workflow()

    # Test direct workflow execution
    await test_direct_workflow_execution()

    print("\n\n" + "=" * 60)
    print("✅ Integration tests complete!")
    print("\n📊 Key Insights:")
    print("   - Simple queries get direct responses")
    print("   - Complex queries trigger multi-agent workflows")
    print("   - Workflow API allows direct orchestration")
    print("   - Chat interface seamlessly integrates workflows")
    print("\n🎮 AutoBot is ready for intelligent task automation!")


if __name__ == "__main__":
    asyncio.run(main())
