#!/usr/bin/env python3
"""
AI Stack Integration Test Suite

This script tests the comprehensive integration between the main AutoBot backend
and the AI Stack VM (172.16.168.24:8080) with all enhanced AI capabilities.
"""

import asyncio
import json
import logging
import time
from typing import Dict, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def test_ai_stack_client():
    """Test AI Stack client connectivity and basic functionality."""
    logger.info("=" * 60)
    logger.info("AI STACK INTEGRATION TEST SUITE")
    logger.info("=" * 60)

    try:
        # Import the AI Stack client
        from backend.services.ai_stack_client import get_ai_stack_client, AIStackError

        logger.info("✓ AI Stack client imported successfully")

        # Test basic connectivity
        logger.info("\n🔧 Testing AI Stack connectivity...")
        try:
            ai_client = await get_ai_stack_client()
            health_status = await ai_client.health_check()

            if health_status["status"] == "healthy":
                logger.info("✅ AI Stack is healthy and accessible")
                logger.info(f"   Response: {health_status}")
                return True, ai_client
            else:
                logger.warning(f"⚠️ AI Stack status: {health_status['status']}")
                return False, None

        except Exception as e:
            logger.error(f"❌ AI Stack connectivity failed: {e}")
            return False, None

    except ImportError as e:
        logger.error(f"❌ Failed to import AI Stack client: {e}")
        return False, None

async def test_available_agents(ai_client):
    """Test listing and availability of AI agents."""
    logger.info("\n🤖 Testing AI Agent Availability...")

    try:
        agents_info = await ai_client.list_available_agents()
        agents = agents_info.get("agents", [])

        logger.info(f"✅ Found {len(agents)} available agents:")
        for agent in agents:
            logger.info(f"   • {agent}")

        # Test specific agent capabilities
        expected_agents = ["rag", "chat", "research", "knowledge_extraction", "development_speedup"]
        available_expected = [agent for agent in expected_agents if agent in agents]

        logger.info(f"\n📊 Expected agents available: {len(available_expected)}/{len(expected_agents)}")
        for agent in available_expected:
            logger.info(f"   ✓ {agent}")

        missing_agents = [agent for agent in expected_agents if agent not in agents]
        if missing_agents:
            logger.warning(f"   Missing agents: {missing_agents}")

        return agents

    except Exception as e:
        logger.error(f"❌ Failed to list agents: {e}")
        return []

async def test_rag_integration(ai_client):
    """Test RAG (Retrieval-Augmented Generation) integration."""
    logger.info("\n🔍 Testing RAG Integration...")

    try:
        # Test RAG query
        test_query = "What is AutoBot and how does it work?"
        logger.info(f"   Query: {test_query}")

        rag_result = await ai_client.rag_query(
            query=test_query,
            max_results=3
        )

        logger.info("✅ RAG query successful")
        logger.info(f"   Response type: {type(rag_result)}")
        if isinstance(rag_result, dict):
            logger.info(f"   Response keys: {list(rag_result.keys())}")

        return True

    except Exception as e:
        logger.error(f"❌ RAG integration test failed: {e}")
        return False

async def test_chat_integration(ai_client):
    """Test enhanced chat integration."""
    logger.info("\n💬 Testing Chat Integration...")

    try:
        test_message = "Hello, can you help me understand AutoBot's capabilities?"
        logger.info(f"   Message: {test_message}")

        chat_result = await ai_client.chat_message(
            message=test_message,
            context="Testing AI Stack integration"
        )

        logger.info("✅ Chat integration successful")
        logger.info(f"   Response type: {type(chat_result)}")
        if isinstance(chat_result, dict):
            logger.info(f"   Response keys: {list(chat_result.keys())}")

        return True

    except Exception as e:
        logger.error(f"❌ Chat integration test failed: {e}")
        return False

async def test_knowledge_extraction(ai_client):
    """Test knowledge extraction capabilities."""
    logger.info("\n📚 Testing Knowledge Extraction...")

    try:
        test_content = """
        AutoBot is a comprehensive AI-powered automation platform that integrates
        multiple specialized AI agents for enhanced functionality. It features
        RAG capabilities, multi-modal processing, and NPU acceleration.
        """

        logger.info("   Testing knowledge extraction from sample content...")

        extraction_result = await ai_client.extract_knowledge(
            content=test_content,
            content_type="text",
            extraction_mode="comprehensive"
        )

        logger.info("✅ Knowledge extraction successful")
        logger.info(f"   Response type: {type(extraction_result)}")
        if isinstance(extraction_result, dict):
            logger.info(f"   Response keys: {list(extraction_result.keys())}")

        return True

    except Exception as e:
        logger.error(f"❌ Knowledge extraction test failed: {e}")
        return False

async def test_multi_agent_coordination(ai_client):
    """Test multi-agent coordination capabilities."""
    logger.info("\n🎭 Testing Multi-Agent Coordination...")

    try:
        test_query = "Analyze AutoBot's architecture and suggest improvements"
        test_agents = ["rag", "chat"]

        logger.info(f"   Query: {test_query}")
        logger.info(f"   Agents: {test_agents}")

        coordination_result = await ai_client.multi_agent_query(
            query=test_query,
            agents=test_agents,
            coordination_mode="parallel"
        )

        logger.info("✅ Multi-agent coordination successful")
        logger.info(f"   Response type: {type(coordination_result)}")
        if isinstance(coordination_result, dict):
            logger.info(f"   Response keys: {list(coordination_result.keys())}")

        return True

    except Exception as e:
        logger.error(f"❌ Multi-agent coordination test failed: {e}")
        return False

async def test_integration_apis():
    """Test the new integration API endpoints."""
    logger.info("\n🌐 Testing Integration APIs...")

    try:
        # Test that API modules can be imported
        from backend.api.ai_stack_integration import router as ai_stack_router
        from backend.api.chat_enhanced import router as chat_enhanced_router
        from backend.api.knowledge_enhanced import router as knowledge_enhanced_router
        from backend.api.agent_enhanced import router as agent_enhanced_router

        logger.info("✅ All integration API modules imported successfully:")
        logger.info("   • AI Stack Integration API")
        logger.info("   • Enhanced Chat API")
        logger.info("   • Enhanced Knowledge API")
        logger.info("   • Enhanced Agent API")

        return True

    except ImportError as e:
        logger.error(f"❌ API import test failed: {e}")
        return False

async def generate_integration_report(test_results: Dict[str, Any]):
    """Generate comprehensive integration test report."""
    logger.info("\n" + "=" * 60)
    logger.info("AI STACK INTEGRATION TEST REPORT")
    logger.info("=" * 60)

    total_tests = len(test_results)
    passed_tests = sum(1 for result in test_results.values() if result)

    logger.info(f"📊 Test Summary: {passed_tests}/{total_tests} tests passed")
    logger.info(f"📈 Success Rate: {(passed_tests/total_tests)*100:.1f}%")

    logger.info("\n📋 Detailed Results:")
    for test_name, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info(f"   {test_name:.<40} {status}")

    logger.info("\n🎯 Integration Status:")
    if passed_tests == total_tests:
        logger.info("   🟢 FULL INTEGRATION: All systems operational")
    elif passed_tests >= total_tests * 0.7:
        logger.info("   🟡 PARTIAL INTEGRATION: Most systems operational")
    else:
        logger.info("   🔴 LIMITED INTEGRATION: Significant issues detected")

    # Integration capabilities summary
    logger.info("\n🔧 Available Capabilities:")
    capabilities = {
        "RAG Enhanced Search": test_results.get("rag_integration", False),
        "Enhanced Chat": test_results.get("chat_integration", False),
        "Knowledge Extraction": test_results.get("knowledge_extraction", False),
        "Multi-Agent Coordination": test_results.get("multi_agent_coordination", False),
        "API Integration": test_results.get("api_integration", False)
    }

    for capability, available in capabilities.items():
        status = "✅ Available" if available else "❌ Unavailable"
        logger.info(f"   • {capability:.<35} {status}")

async def main():
    """Main test execution function."""
    start_time = time.time()

    logger.info("Starting AI Stack Integration Test Suite...")
    logger.info(f"Target: AI Stack VM (172.16.168.24:8080)")
    logger.info(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S')}")

    test_results = {}

    # Test 1: Basic connectivity
    connectivity_success, ai_client = await test_ai_stack_client()
    test_results["connectivity"] = connectivity_success

    if connectivity_success and ai_client:
        # Test 2: Agent availability
        agents = await test_available_agents(ai_client)
        test_results["agent_availability"] = len(agents) > 0

        # Test 3: RAG integration (if agents available)
        if agents:
            test_results["rag_integration"] = await test_rag_integration(ai_client)
            test_results["chat_integration"] = await test_chat_integration(ai_client)
            test_results["knowledge_extraction"] = await test_knowledge_extraction(ai_client)
            test_results["multi_agent_coordination"] = await test_multi_agent_coordination(ai_client)
        else:
            test_results.update({
                "rag_integration": False,
                "chat_integration": False,
                "knowledge_extraction": False,
                "multi_agent_coordination": False
            })
    else:
        # Mark all tests as failed if no connectivity
        test_results.update({
            "agent_availability": False,
            "rag_integration": False,
            "chat_integration": False,
            "knowledge_extraction": False,
            "multi_agent_coordination": False
        })

    # Test 4: API integration (always testable)
    test_results["api_integration"] = await test_integration_apis()

    # Generate final report
    await generate_integration_report(test_results)

    execution_time = time.time() - start_time
    logger.info(f"\n⏱️ Total execution time: {execution_time:.2f} seconds")
    logger.info("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
