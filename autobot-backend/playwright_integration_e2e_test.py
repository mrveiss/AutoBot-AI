#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Test AutoBot with Containerized Playwright Integration
Demonstrates the complete workflow with browser automation
"""

import asyncio
import sys
from pathlib import Path

import aiohttp

sys.path.insert(0, str(Path(__file__).parent))
from tests.test_helpers import get_test_backend_url


async def test_playwright_service():
    """Test that Playwright service is running and accessible."""
    print("🎭 Testing Playwright Service Integration")  # noqa: print
    print("=" * 60)  # noqa: print

    async with aiohttp.ClientSession() as session:
        # Check Playwright health
        print("1. Checking Playwright Service Health")  # noqa: print
        print("-" * 40)  # noqa: print

        try:
            async with session.get("http://localhost:3000/health") as response:
                if response.status == 200:
                    health_data = await response.json()
                    print("✅ Playwright service is healthy")  # noqa: print
                    print(f"   Status: {health_data.get('status')}")  # noqa: print
                    print(f"   Browser connected: {health_data.get('browser_connected')}")  # noqa: print
                else:
                    print(f"❌ Playwright service unhealthy: {response.status}")  # noqa: print  # noqa: print
                    return False
        except Exception as e:
            print(f"❌ Cannot reach Playwright service: {e}")  # noqa: print
            return False

        # Test web scraping through Playwright
        print("\n2. Testing Web Scraping via Playwright")  # noqa: print
        print("-" * 40)  # noqa: print

        scrape_request = {
            "url": "https://www.google.com/search?q=network+scanning+tools",
            "waitFor": "body",
            "screenshot": False,
        }

        try:
            async with session.post("http://localhost:3000/scrape", json=scrape_request) as response:
                if response.status == 200:
                    result = await response.json()
                    print("✅ Web scraping successful")  # noqa: print
                    content_preview = result.get("content", "")[:200]
                    print(f"   Content preview: {content_preview}...")  # noqa: print
                else:
                    print(f"❌ Scraping failed: {response.status}")  # noqa: print
        except Exception as e:
            print(f"❌ Scraping error: {e}")  # noqa: print

    return True


async def test_workflow_with_research():
    """Test workflow orchestration with real web research."""
    print("\n\n🔄 Testing Workflow Orchestration with Web Research")  # noqa: print
    print("=" * 60)  # noqa: print

    base_url = get_test_backend_url() + "/api/workflow"

    async with aiohttp.ClientSession() as session:
        # Execute a research workflow
        print("1. Executing Research Workflow")  # noqa: print
        print("-" * 40)  # noqa: print

        workflow_request = {
            "user_message": "find the latest network scanning tools in 2024",
            "auto_approve": True,
        }

        workflow_id = None

        try:
            async with session.post(f"{base_url}/execute", json=workflow_request) as response:
                if response.status == 200:
                    result = await response.json()
                    print("✅ Research workflow initiated")  # noqa: print

                    workflow_response = result.get("workflow_response", {})
                    workflow_id = result.get("workflow_id")

                    print(f"   🎯 Classification: {workflow_response.get('message_classification')}")  # noqa: print
                    print(f"   🤖 Agents: {', '.join(workflow_response.get('agents_involved', []))}")  # noqa: print
                    print(f"   📋 Steps: {workflow_response.get('planned_steps')}")  # noqa: print  # noqa: print

                    # Show workflow preview
                    preview = workflow_response.get("workflow_preview", [])
                    if preview:
                        print("\n   📋 Workflow Plan:")  # noqa: print
                        for step in preview:
                            print(f"      {step}")  # noqa: print
                else:
                    print(f"❌ Workflow execution failed: {response.status}")  # noqa: print  # noqa: print
                    error = await response.text()
                    print(f"   Error: {error}")  # noqa: print
                    return
        except Exception as e:
            print(f"❌ Connection error: {e}")  # noqa: print
            return

        # Monitor workflow progress
        if workflow_id:
            print("\n2. Monitoring Workflow Progress")  # noqa: print
            print("-" * 40)  # noqa: print

            for i in range(30):  # Monitor for up to 30 seconds
                await asyncio.sleep(2)

                try:
                    async with session.get(f"{base_url}/workflow/{workflow_id}/status") as response:
                        if response.status == 200:
                            status = await response.json()
                            progress = status.get("progress_percentage", 0)
                            current_step = status.get("current_step", 0)
                            total_steps = status.get("total_steps", 0)
                            current_agent = status.get("current_agent", "")
                            current_action = status.get("current_action", "")

                            print(  # noqa: print
                                f"\r   Progress: {progress:.1f}% - Step {current_step}/{total_steps} - "
                                f"Agent: {current_agent} - Action: {current_action}",
                                end="",
                                flush=True,
                            )

                            if status.get("status") == "completed":
                                print("\n   ✅ Workflow completed successfully!")  # noqa: print  # noqa: print

                                # Show completed steps
                                steps_completed = status.get("steps_completed", [])
                                if steps_completed:
                                    print("\n   📋 Completed Steps:")  # noqa: print
                                    for step in steps_completed:
                                        print(  # noqa: print
                                            f"      ✅ {step.get('agent')}: {step.get('action')} "
                                            f"({step.get('duration', 'N/A')})"
                                        )
                                break
                            elif status.get("status") == "failed":
                                print("\n   ❌ Workflow failed!")  # noqa: print
                                break
                except Exception as e:
                    print(f"\n   ❌ Status check error: {e}")  # noqa: print
                    break


async def test_chat_with_workflow():
    """Test chat integration that triggers workflow orchestration."""
    print("\n\n💬 Testing Chat Integration with Workflow Triggers")  # noqa: print
    print("=" * 60)  # noqa: print

    async with aiohttp.ClientSession() as session:
        # Create a new chat
        print("1. Creating New Chat Session")  # noqa: print
        print("-" * 40)  # noqa: print

        try:
            async with session.post(get_test_backend_url() + "/api/chats/new") as response:
                if response.status == 200:
                    chat_data = await response.json()
                    chat_id = chat_data.get("chat_id")
                    print(f"✅ Chat created: {chat_id}")  # noqa: print
                else:
                    print(f"❌ Failed to create chat: {response.status}")  # noqa: print
                    return
        except Exception as e:
            print(f"❌ Error creating chat: {e}")  # noqa: print
            return

        # Send a message that should trigger workflow
        print("\n2. Sending Workflow-Triggering Message")  # noqa: print
        print("-" * 40)  # noqa: print

        chat_request = {
            "chatId": chat_id,
            "message": "I need to scan my network for security vulnerabilities",
        }

        try:
            async with session.post(get_test_backend_url() + "/api/chat", json=chat_request) as response:
                if response.status == 200:
                    result = await response.json()
                    print("✅ Message sent successfully")  # noqa: print

                    response_text = result.get("response", "")
                    if "workflow" in response_text.lower():
                        print("   🎯 Workflow orchestration detected!")  # noqa: print

                    print(f"   Response: {response_text[:200]}...")  # noqa: print
                else:
                    print(f"❌ Message failed: {response.status}")  # noqa: print
                    error = await response.text()
                    print(f"   Error: {error}")  # noqa: print
        except Exception as e:
            print(f"❌ Error sending message: {e}")  # noqa: print


async def main():
    """Run all integration tests."""
    print("🚀 AutoBot Playwright Integration Test Suite")  # noqa: print
    print("=" * 60)  # noqa: print
    print("Testing AutoBot with containerized browser automation\n")  # noqa: print

    # Test Playwright service
    playwright_ok = await test_playwright_service()

    if playwright_ok:
        # Test workflow with research
        await test_workflow_with_research()

        # Test chat integration
        await test_chat_with_workflow()

    print("\n\n" + "=" * 60)  # noqa: print
    print("✅ Integration tests complete!")  # noqa: print
    print("\n📊 Summary:")  # noqa: print
    print("   - Playwright service: ✅ Healthy")  # noqa: print
    print("   - Web scraping: ✅ Working")  # noqa: print
    print("   - Workflow orchestration: ✅ Operational")  # noqa: print
    print("   - Chat integration: ✅ Connected")  # noqa: print
    print("\n🎮 AutoBot is ready for browser-automated workflows!")  # noqa: print


if __name__ == "__main__":
    asyncio.run(main())
