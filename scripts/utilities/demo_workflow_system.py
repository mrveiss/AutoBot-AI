#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Workflow System Demonstration
Shows the complete transformation from generic responses to intelligent orchestration
"""

import asyncio
import aiohttp
import time
from datetime import datetime
from src.constants import ServiceURLs


class WorkflowDemo:
    """Demonstrates AutoBot workflow orchestration capabilities."""

    def __init__(self):
        """Initialize workflow demo with backend URL and demo scenarios."""
        self.base_url = ServiceURLs.BACKEND_LOCAL
        self.demo_scenarios = [
            {
                "name": "Simple Query",
                "request": "What is 2+2?",
                "expected": "Direct response - no workflow needed",
                "classification": "simple",
            },
            {
                "name": "Research Query",
                "request": "Find information about Python web frameworks",
                "expected": "Research workflow - web search and knowledge storage",
                "classification": "research",
            },
            {
                "name": "Installation Query",
                "request": "How do I install Docker on Ubuntu?",
                "expected": "Installation workflow - system commands",
                "classification": "install",
            },
            {
                "name": "Complex Multi-Agent Query",
                "request": "find tools that would require to do network scan",
                "expected": "Full multi-agent workflow - 8 coordinated steps",
                "classification": "complex",
            },
        ]

    async def demonstrate_transformation(self):
        """Show the before/after transformation."""

        print("🚀 AutoBot Workflow Orchestration Demonstration")
        print("=" * 70)
        print(f"🕐 Demo started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print()

        print("📊 BEFORE vs AFTER Comparison:")
        print("-" * 50)
        print("❌ OLD: Generic, unhelpful responses")
        print("✅ NEW: Intelligent multi-agent workflows")
        print()

        # Test backend connectivity first
        if not await self.test_connectivity():
            return False

        # Run demonstration scenarios
        for i, scenario in enumerate(self.demo_scenarios, 1):
            await self.demonstrate_scenario(i, scenario)
            print()

        # Show workflow capabilities summary
        await self.show_capabilities_summary()

        return True

    async def test_connectivity(self):
        """Test if the backend is accessible."""

        print("🔍 Testing Backend Connectivity")
        print("-" * 40)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/api/hello") as response:
                    if response.status == 200:
                        result = await response.json()
                        print(f"✅ Backend connected: {result.get('message', 'OK')}")

                        # Test workflow endpoints
                        async with session.get(
                            f"{self.base_url}/api/workflow/workflows"
                        ) as wf_response:
                            if wf_response.status == 200:
                                print("✅ Workflow API accessible")
                                return True
                            else:
                                print(
                                    f"❌ Workflow API not accessible: {wf_response.status}"
                                )
                                print(
                                    "   Please restart backend to load workflow endpoints"
                                )
                                return False

                    else:
                        print(f"❌ Backend connection failed: {response.status}")
                        return False

            except Exception as e:
                print(f"❌ Cannot connect to backend: {e}")
                print("   Make sure AutoBot is running: python main.py")
                return False

    async def demonstrate_scenario(self, index, scenario):
        """Demonstrate a specific scenario."""

        print(f"{index}. {scenario['name']}")
        print("   Query: \"{scenario['request']}\"")
        print(f"   Expected: {scenario['expected']}")
        print("   " + "-" * 60)

        async with aiohttp.ClientSession() as session:
            try:
                # Execute workflow
                workflow_request = {
                    "user_message": scenario["request"],
                    "auto_approve": True,  # Auto-approve for demo
                }

                start_time = time.time()

                async with session.post(
                    f"{self.base_url}/api/workflow/workflow/execute",
                    json=workflow_request,
                ) as response:
                    execution_time = time.time() - start_time

                    if response.status == 200:
                        result = await response.json()
                        await self.analyze_workflow_response(
                            result, scenario, execution_time
                        )

                    else:
                        error_text = await response.text()
                        print(f"   ❌ Request failed: {response.status}")
                        print(f"   Error: {error_text}")

            except Exception as e:
                print(f"   ❌ Execution error: {e}")

    async def analyze_workflow_response(self, result, scenario, execution_time):
        """Analyze and display workflow response details."""

        if result.get("type") == "workflow_orchestration":
            workflow_response = result.get("workflow_response", {})
            classification = workflow_response.get("message_classification", "unknown")

            # Check if classification matches expectation
            classification_match = classification == scenario["classification"]
            status_icon = "✅" if classification_match else "⚠️"

            print(f"   {status_icon} Classification: {classification.upper()}")
            print(f"   🕐 Response Time: {execution_time:.2f}s")

            if classification == "simple":
                print("   💬 Direct response provided - no workflow needed")

            elif classification in ["research", "install", "complex"]:
                agents = workflow_response.get("agents_involved", [])
                steps = workflow_response.get("planned_steps", 0)
                duration = workflow_response.get("estimated_duration", "unknown")
                approvals = workflow_response.get("user_approvals_needed", 0)

                print(f"   🤖 Agents: {', '.join(agents)}")
                print(f"   📋 Steps: {steps}")
                print(f"   ⏱️  Duration: {duration}")
                print(f"   👤 Approvals: {approvals}")

                # Show workflow preview for complex requests
                if classification == "complex":
                    print("   📝 Workflow Steps:")
                    preview = workflow_response.get("workflow_preview", [])
                    for j, step in enumerate(preview[:4], 1):
                        print(f"      {j}. {step}")
                    if len(preview) > 4:
                        print(f"      ... and {len(preview) - 4} more steps")

            # Show workflow ID if available
            if result.get("workflow_id"):
                print(f"   🔗 Workflow ID: {result['workflow_id']}")

        elif result.get("type") == "direct_execution":
            print("   💬 Direct execution - simple response")

        else:
            print(f"   ❓ Unknown response type: {result.get('type', 'none')}")

    async def show_capabilities_summary(self):
        """Show a summary of system capabilities."""

        print("=" * 70)
        print("🎯 AutoBot Workflow Orchestration Capabilities Summary")
        print("=" * 70)

        capabilities = [
            {
                "feature": "Intelligent Request Classification",
                "description": "Automatically categorizes requests by complexity",
                "benefit": "Routes requests to appropriate handling strategy",
            },
            {
                "feature": "Multi-Agent Coordination",
                "description": "Orchestrates specialized agents for complex tasks",
                "benefit": "Provides comprehensive solutions vs generic responses",
            },
            {
                "feature": "Research Agent Integration",
                "description": "Web research with tool discovery and guides",
                "benefit": "Finds specific tools with installation instructions",
            },
            {
                "feature": "User Approval System",
                "description": "Human oversight for critical workflow steps",
                "benefit": "Maintains control while enabling automation",
            },
            {
                "feature": "Progress Tracking",
                "description": "Real-time workflow status and step monitoring",
                "benefit": "Transparency and ability to intervene if needed",
            },
            {
                "feature": "Knowledge Management",
                "description": "Structured storage of research findings",
                "benefit": "Builds organizational knowledge over time",
            },
        ]

        for cap in capabilities:
            print(f"\n🔧 {cap['feature']}")
            print(f"   📄 {cap['description']}")
            print(f"   💡 Benefit: {cap['benefit']}")

        print("\n" + "=" * 70)
        print("🎉 TRANSFORMATION COMPLETE!")
        print("   From: Generic AI responses")
        print("   To:   Intelligent workflow orchestration")
        print("=" * 70)

    async def test_specific_workflow(self, request_text):
        """Test a specific workflow request in detail."""

        print("\n🔬 Detailed Workflow Analysis")
        print(f'Request: "{request_text}"')
        print("-" * 50)

        async with aiohttp.ClientSession() as session:
            try:
                workflow_request = {
                    "user_message": request_text,
                    "auto_approve": False,  # Require manual approval to show process
                }

                # Execute workflow
                async with session.post(
                    f"{self.base_url}/api/workflow/workflow/execute",
                    json=workflow_request,
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        workflow_id = result.get("workflow_id")

                        if workflow_id:
                            print(f"✅ Workflow created: {workflow_id}")

                            # Monitor workflow progress
                            await self.monitor_workflow_execution(session, workflow_id)

                        else:
                            print("✅ Direct execution - no workflow needed")

                    else:
                        error_text = await response.text()
                        print(f"❌ Workflow creation failed: {error_text}")

            except Exception as e:
                print(f"❌ Workflow test error: {e}")

    async def monitor_workflow_execution(self, session, workflow_id):
        """Monitor workflow execution in real-time."""

        print(f"📊 Monitoring Workflow: {workflow_id}")
        print("-" * 40)

        for i in range(10):  # Check up to 10 times
            try:
                async with session.get(
                    f"{self.base_url}/api/workflow/workflow/{workflow_id}/status"
                ) as response:
                    if response.status == 200:
                        status = await response.json()

                        current_step = status.get("current_step", 0) + 1
                        total_steps = status.get("total_steps", 0)
                        progress = status.get("progress", 0) * 100
                        workflow_status = status.get("status", "unknown")

                        print(
                            f"   Step {current_step}/{total_steps} ({progress:.0f}%) - {workflow_status}"
                        )

                        if workflow_status in ["completed", "failed", "cancelled"]:
                            print(f"   🏁 Workflow {workflow_status}")
                            break

                        # Check for pending approvals
                        if workflow_status == "waiting_approval":
                            print("   👤 User approval required - workflow paused")
                            print("   💡 In production, user would see approval dialog")
                            break

                    else:
                        print(f"   ❌ Status check failed: {response.status}")
                        break

            except Exception as e:
                print(f"   ❌ Monitoring error: {e}")
                break

            await asyncio.sleep(2)  # Wait 2 seconds between checks


async def main():
    """Run the complete workflow demonstration."""

    demo = WorkflowDemo()

    # Run main demonstration
    success = await demo.demonstrate_transformation()

    if success:
        # Test a specific complex workflow in detail
        await demo.test_specific_workflow(
            "find tools that would require to do network scan"
        )

        print("\n🎯 Demo Complete - Key Takeaways:")
        print("   • AutoBot now intelligently classifies requests")
        print("   • Complex requests trigger multi-agent workflows")
        print("   • Users get specific, actionable solutions")
        print("   • No more generic, unhelpful responses")
        print("   • Full transparency with progress tracking")
        print("   • Human oversight maintained through approvals")
        print("\n🚀 AutoBot has evolved from simple chat to intelligent orchestration!")

    else:
        print("\n❌ Demo failed - check backend status")
        print("   Restart backend: source venv/bin/activate && python main.py")


if __name__ == "__main__":
    asyncio.run(main())
