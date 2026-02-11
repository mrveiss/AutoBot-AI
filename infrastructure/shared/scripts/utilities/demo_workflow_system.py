#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AutoBot Workflow System Demonstration
Shows the complete transformation from generic responses to intelligent orchestration
"""

import asyncio
import logging
import time
from datetime import datetime

import aiohttp
from constants import ServiceURLs

# Setup logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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

        logger.info("🚀 AutoBot Workflow Orchestration Demonstration")
        logger.info("=" * 70)
        logger.info(f"🕐 Demo started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        logger.info()

        logger.info("📊 BEFORE vs AFTER Comparison:")
        logger.info("-" * 50)
        logger.info("❌ OLD: Generic, unhelpful responses")
        logger.info("✅ NEW: Intelligent multi-agent workflows")
        logger.info()

        # Test backend connectivity first
        if not await self.test_connectivity():
            return False

        # Run demonstration scenarios
        for i, scenario in enumerate(self.demo_scenarios, 1):
            await self.demonstrate_scenario(i, scenario)
            logger.info()

        # Show workflow capabilities summary
        await self.show_capabilities_summary()

        return True

    async def test_connectivity(self):
        """Test if the backend is accessible."""

        logger.info("🔍 Testing Backend Connectivity")
        logger.info("-" * 40)

        async with aiohttp.ClientSession() as session:
            try:
                async with session.get(f"{self.base_url}/api/hello") as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✅ Backend connected: {result.get('message', 'OK')}")

                        # Test workflow endpoints
                        async with session.get(
                            f"{self.base_url}/api/workflow/workflows"
                        ) as wf_response:
                            if wf_response.status == 200:
                                logger.info("✅ Workflow API accessible")
                                return True
                            else:
                                logger.info(
                                    f"❌ Workflow API not accessible: {wf_response.status}"
                                )
                                logger.info(
                                    "   Please restart backend to load workflow endpoints"
                                )
                                return False

                    else:
                        logger.info(f"❌ Backend connection failed: {response.status}")
                        return False

            except Exception as e:
                logger.info(f"❌ Cannot connect to backend: {e}")
                logger.info("   Make sure AutoBot is running: python main.py")
                return False

    async def demonstrate_scenario(self, index, scenario):
        """Demonstrate a specific scenario."""

        logger.info(f"{index}. {scenario['name']}")
        logger.info("   Query: \"{scenario['request']}\"")
        logger.info(f"   Expected: {scenario['expected']}")
        logger.info("   " + "-" * 60)

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
                        logger.info(f"   ❌ Request failed: {response.status}")
                        logger.info(f"   Error: {error_text}")

            except Exception as e:
                logger.info(f"   ❌ Execution error: {e}")

    async def analyze_workflow_response(self, result, scenario, execution_time):
        """Analyze and display workflow response details."""

        if result.get("type") == "workflow_orchestration":
            workflow_response = result.get("workflow_response", {})
            classification = workflow_response.get("message_classification", "unknown")

            # Check if classification matches expectation
            classification_match = classification == scenario["classification"]
            status_icon = "✅" if classification_match else "⚠️"

            logger.info(f"   {status_icon} Classification: {classification.upper()}")
            logger.info(f"   🕐 Response Time: {execution_time:.2f}s")

            if classification == "simple":
                logger.info("   💬 Direct response provided - no workflow needed")

            elif classification in ["research", "install", "complex"]:
                agents = workflow_response.get("agents_involved", [])
                steps = workflow_response.get("planned_steps", 0)
                duration = workflow_response.get("estimated_duration", "unknown")
                approvals = workflow_response.get("user_approvals_needed", 0)

                logger.info(f"   🤖 Agents: {', '.join(agents)}")
                logger.info(f"   📋 Steps: {steps}")
                logger.info(f"   ⏱️  Duration: {duration}")
                logger.info(f"   👤 Approvals: {approvals}")

                # Show workflow preview for complex requests
                if classification == "complex":
                    logger.info("   📝 Workflow Steps:")
                    preview = workflow_response.get("workflow_preview", [])
                    for j, step in enumerate(preview[:4], 1):
                        logger.info(f"      {j}. {step}")
                    if len(preview) > 4:
                        logger.info(f"      ... and {len(preview) - 4} more steps")

            # Show workflow ID if available
            if result.get("workflow_id"):
                logger.info(f"   🔗 Workflow ID: {result['workflow_id']}")

        elif result.get("type") == "direct_execution":
            logger.info("   💬 Direct execution - simple response")

        else:
            logger.info(f"   ❓ Unknown response type: {result.get('type', 'none')}")

    async def show_capabilities_summary(self):
        """Show a summary of system capabilities."""

        logger.info("=" * 70)
        logger.info("🎯 AutoBot Workflow Orchestration Capabilities Summary")
        logger.info("=" * 70)

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
            logger.info(f"\n🔧 {cap['feature']}")
            logger.info(f"   📄 {cap['description']}")
            logger.info(f"   💡 Benefit: {cap['benefit']}")

        logger.info("\n" + "=" * 70)
        logger.info("🎉 TRANSFORMATION COMPLETE!")
        logger.info("   From: Generic AI responses")
        logger.info("   To:   Intelligent workflow orchestration")
        logger.info("=" * 70)

    async def test_specific_workflow(self, request_text):
        """Test a specific workflow request in detail."""

        logger.info("\n🔬 Detailed Workflow Analysis")
        logger.info(f'Request: "{request_text}"')
        logger.info("-" * 50)

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
                            logger.info(f"✅ Workflow created: {workflow_id}")

                            # Monitor workflow progress
                            await self.monitor_workflow_execution(session, workflow_id)

                        else:
                            logger.info("✅ Direct execution - no workflow needed")

                    else:
                        error_text = await response.text()
                        logger.info(f"❌ Workflow creation failed: {error_text}")

            except Exception as e:
                logger.info(f"❌ Workflow test error: {e}")

    async def monitor_workflow_execution(self, session, workflow_id):
        """Monitor workflow execution in real-time."""

        logger.info(f"📊 Monitoring Workflow: {workflow_id}")
        logger.info("-" * 40)

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

                        logger.info(
                            f"   Step {current_step}/{total_steps} ({progress:.0f}%) - {workflow_status}"
                        )

                        if workflow_status in ["completed", "failed", "cancelled"]:
                            logger.info(f"   🏁 Workflow {workflow_status}")
                            break

                        # Check for pending approvals
                        if workflow_status == "waiting_approval":
                            logger.info("   👤 User approval required - workflow paused")
                            logger.info("   💡 In production, user would see approval dialog")
                            break

                    else:
                        logger.info(f"   ❌ Status check failed: {response.status}")
                        break

            except Exception as e:
                logger.info(f"   ❌ Monitoring error: {e}")
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

        logger.info("\n🎯 Demo Complete - Key Takeaways:")
        logger.info("   • AutoBot now intelligently classifies requests")
        logger.info("   • Complex requests trigger multi-agent workflows")
        logger.info("   • Users get specific, actionable solutions")
        logger.info("   • No more generic, unhelpful responses")
        logger.info("   • Full transparency with progress tracking")
        logger.info("   • Human oversight maintained through approvals")
        logger.info("\n🚀 AutoBot has evolved from simple chat to intelligent orchestration!")

    else:
        logger.info("\n❌ Demo failed - check backend status")
        logger.info("   Restart backend: source venv/bin/activate && python main.py")


if __name__ == "__main__":
    asyncio.run(main())
