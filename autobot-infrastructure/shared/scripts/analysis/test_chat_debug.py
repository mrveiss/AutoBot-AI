#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Debug script to test the chat flow and identify where responses are getting lost
"""

import asyncio
import json
import logging
import sys
from pathlib import Path

import requests

# A backend tool (#18289): it deliberately drives backend internals. It puts the backend and the
# repository root (for `autobot_shared`) on its own path, so it runs from any directory with no
# PYTHONPATH; the backend's Python dependencies must be installed.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

import config as config  # noqa: E402
from agents.classification_agent import ClassificationAgent  # noqa: E402
from async_chat_workflow import process_chat_message_with_timeout  # noqa: E402

# Setup logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_classification_agent():
    """Test the classification agent directly"""
    logger.info("🔍 Testing Classification Agent...")

    try:
        agent = ClassificationAgent()
        result = await agent.classify_request("hello")

        logger.info("✅ Classification successful:")
        logger.info(f"   Complexity: {result.complexity.value}")
        logger.info(f"   Confidence: {result.confidence}")
        logger.info(f"   Reasoning: {result.reasoning}")
        logger.info(f"   Suggested agents: {result.suggested_agents}")

        return True
    except Exception as e:
        logger.error(f"❌ Classification failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_conversation_flow():
    """Test the complete conversation flow"""
    logger.info("\n💬 Testing Conversation Flow...")

    try:
        # The conversation_manager this used was removed; the async chat workflow is its successor.
        outcome = await process_chat_message_with_timeout("hello", "test_debug_chat")
        result = {
            "response": outcome.response,
            "message_type": outcome.message_type.value,
            "processing_time": outcome.processing_time,
            "kb_results_count": len(outcome.kb_results),
        }

        logger.info("✅ Conversation processing successful:")
        logger.info(f"   Response: {result['response'][:100]}...")
        logger.info(f"   Message type: {result['message_type']}")
        logger.info(f"   Processing time: {result['processing_time']:.2f}s")
        logger.info(f"   KB results: {result['kb_results_count']}")

        return True, result
    except Exception as e:
        logger.error(f"❌ Conversation flow failed: {e}")
        import traceback

        traceback.print_exc()
        return False, None


def test_backend_api():
    """Test the backend API endpoint directly"""
    logger.info("\n🌐 Testing Backend API...")

    try:
        # Get the backend URL from config
        backend_url = config.config.get_nested("backend.api_endpoint", "http://127.0.0.3:8001")

        # Test the chat endpoint
        url = f"{backend_url}/api/chat"
        payload = {"chatId": "test_debug_chat", "message": "hello"}

        logger.info(f"   Sending POST to: {url}")
        logger.info(f"   Payload: {payload}")

        response = requests.post(url, json=payload, timeout=30)

        logger.info(f"   Status Code: {response.status_code}")
        logger.info(f"   Headers: {dict(response.headers)}")

        if response.status_code == 200:
            try:
                data = response.json()
                logger.info("✅ API call successful:")
                logger.info(f"   Response type: {data.get('messageType', 'unknown')}")
                logger.info(f"   Content length: {len(data.get('content', ''))}")
                logger.info(f"   Content preview: {data.get('content', '')[:100]}...")
                return True, data
            except json.JSONDecodeError as e:
                logger.error(f"❌ JSON decode error: {e}")
                logger.info(f"   Raw response: {response.text[:200]}...")
                return False, None
        else:
            logger.error(f"❌ API call failed: {response.status_code}")
            logger.info(f"   Response: {response.text[:200]}...")
            return False, None

    except Exception as e:
        logger.error(f"❌ Backend API test failed: {e}")
        import traceback

        traceback.print_exc()
        return False, None


def test_frontend_config():
    """Test frontend configuration and endpoints"""
    logger.info("\n🎨 Testing Frontend Config...")

    try:
        # Check if the frontend is making requests to the right place
        frontend_env_file = Path("autobot-vue/.env")
        if frontend_env_file.exists():
            with open(frontend_env_file, "r", encoding="utf-8") as f:
                content = f.read()
                logger.info("   Frontend .env content:")
                for line in content.split("\n"):
                    if "API" in line or "BACKEND" in line or "HOST" in line:
                        logger.info(f"      {line}")

        # Check the actual API config
        api_config_file = Path("autobot-vue/src/config/api.js")
        if api_config_file.exists():
            logger.info("   ✅ Frontend API config exists")
        else:
            logger.error("   ❌ Frontend API config missing")

        return True
    except Exception as e:
        logger.error(f"❌ Frontend config test failed: {e}")
        return False


async def main():
    """Run all debug tests"""
    logger.info("🚀 AutoBot Chat Debug Tool")
    logger.info("=" * 50)

    # Test each component
    tests = [
        ("Classification Agent", test_classification_agent()),
        ("Conversation Flow", test_conversation_flow()),
    ]

    results = {}

    for test_name, test_coro in tests:
        logger.info(f"\n📋 Running {test_name}...")
        try:
            result = await test_coro
            if isinstance(result, tuple):
                success, data = result
                results[test_name] = {"success": success, "data": data}
            else:
                results[test_name] = {"success": result, "data": None}
        except Exception as e:
            logger.error(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = {"success": False, "data": str(e)}

    # Run synchronous tests
    sync_tests = [
        ("Backend API", test_backend_api),
        ("Frontend Config", test_frontend_config),
    ]

    for test_name, test_func in sync_tests:
        logger.info(f"\n📋 Running {test_name}...")
        try:
            result = test_func()
            if isinstance(result, tuple):
                success, data = result
                results[test_name] = {"success": success, "data": data}
            else:
                results[test_name] = {"success": result, "data": None}
        except Exception as e:
            logger.error(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = {"success": False, "data": str(e)}

    # Summary
    logger.info("\n" + "=" * 50)
    logger.info("📊 DEBUG SUMMARY")
    logger.info("=" * 50)

    for test_name, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        logger.info(f"{status} {test_name}")
        if not result["success"] and result["data"]:
            logger.error(f"      Error: {result['data']}")

    # Recommendations
    logger.info("\n🔧 RECOMMENDATIONS:")

    if not results.get("Classification Agent", {}).get("success"):
        logger.info("   - Check Ollama service is running and accessible")
        logger.info("   - Verify LLM models are loaded")

    if not results.get("Conversation Flow", {}).get("success"):
        logger.error("   - Check conversation.py for errors")
        logger.info("   - Verify knowledge base connectivity")

    if not results.get("Backend API", {}).get("success"):
        logger.info("   - Check backend service is running on correct port")
        logger.info("   - Verify API endpoints are accessible")

    if not results.get("Frontend Config", {}).get("success"):
        logger.info("   - Check frontend environment configuration")
        logger.info("   - Verify API endpoint URLs")


if __name__ == "__main__":
    asyncio.run(main())
