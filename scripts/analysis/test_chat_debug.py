#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

import src.config as config
from src.agents.classification_agent import ClassificationAgent
from src.conversation import conversation_manager

# Setup logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


async def test_classification_agent():
    """Test the classification agent directly"""
    print("🔍 Testing Classification Agent...")

    try:
        agent = ClassificationAgent()
        result = await agent.classify_request("hello")

        print("✅ Classification successful:")
        print(f"   Complexity: {result.complexity.value}")
        print(f"   Confidence: {result.confidence}")
        print(f"   Reasoning: {result.reasoning}")
        print(f"   Suggested agents: {result.suggested_agents}")

        return True
    except Exception as e:
        print(f"❌ Classification failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_conversation_flow():
    """Test the complete conversation flow"""
    print("\n💬 Testing Conversation Flow...")

    try:
        # Create a test conversation
        conversation = conversation_manager.create_conversation("test_debug_chat")

        # Process the message
        result = await conversation.process_user_message("hello")

        print("✅ Conversation processing successful:")
        print(f"   Response: {result['response'][:100]}...")
        print(
            f"   Classification: {result.get('classification', {}).get('complexity', 'None')}"
        )
        print(f"   Processing time: {result.get('processing_time', 0):.2f}s")
        print(f"   KB results: {result.get('kb_results_count', 0)}")

        return True, result
    except Exception as e:
        print(f"❌ Conversation flow failed: {e}")
        import traceback

        traceback.print_exc()
        return False, None


def test_backend_api():
    """Test the backend API endpoint directly"""
    print("\n🌐 Testing Backend API...")

    try:
        # Get the backend URL from config
        backend_url = config.config.get_nested(
            "backend.api_endpoint", "http://127.0.0.3:8001"
        )

        # Test the chat endpoint
        url = f"{backend_url}/api/chat"
        payload = {"chatId": "test_debug_chat", "message": "hello"}

        print(f"   Sending POST to: {url}")
        print(f"   Payload: {payload}")

        response = requests.post(url, json=payload, timeout=30)

        print(f"   Status Code: {response.status_code}")
        print(f"   Headers: {dict(response.headers)}")

        if response.status_code == 200:
            try:
                data = response.json()
                print("✅ API call successful:")
                print(f"   Response type: {data.get('messageType', 'unknown')}")
                print(f"   Content length: {len(data.get('content', ''))}")
                print(f"   Content preview: {data.get('content', '')[:100]}...")
                return True, data
            except json.JSONDecodeError as e:
                print(f"❌ JSON decode error: {e}")
                print(f"   Raw response: {response.text[:200]}...")
                return False, None
        else:
            print(f"❌ API call failed: {response.status_code}")
            print(f"   Response: {response.text[:200]}...")
            return False, None

    except Exception as e:
        print(f"❌ Backend API test failed: {e}")
        import traceback

        traceback.print_exc()
        return False, None


def test_frontend_config():
    """Test frontend configuration and endpoints"""
    print("\n🎨 Testing Frontend Config...")

    try:
        # Check if the frontend is making requests to the right place
        frontend_env_file = Path("autobot-vue/.env")
        if frontend_env_file.exists():
            with open(frontend_env_file, "r") as f:
                content = f.read()
                print("   Frontend .env content:")
                for line in content.split("\n"):
                    if "API" in line or "BACKEND" in line or "HOST" in line:
                        print(f"      {line}")

        # Check the actual API config
        api_config_file = Path("autobot-vue/src/config/api.js")
        if api_config_file.exists():
            print("   ✅ Frontend API config exists")
        else:
            print("   ❌ Frontend API config missing")

        return True
    except Exception as e:
        print(f"❌ Frontend config test failed: {e}")
        return False


async def main():
    """Run all debug tests"""
    print("🚀 AutoBot Chat Debug Tool")
    print("=" * 50)

    # Test each component
    tests = [
        ("Classification Agent", test_classification_agent()),
        ("Conversation Flow", test_conversation_flow()),
    ]

    results = {}

    for test_name, test_coro in tests:
        print(f"\n📋 Running {test_name}...")
        try:
            result = await test_coro
            if isinstance(result, tuple):
                success, data = result
                results[test_name] = {"success": success, "data": data}
            else:
                results[test_name] = {"success": result, "data": None}
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = {"success": False, "data": str(e)}

    # Run synchronous tests
    sync_tests = [
        ("Backend API", test_backend_api),
        ("Frontend Config", test_frontend_config),
    ]

    for test_name, test_func in sync_tests:
        print(f"\n📋 Running {test_name}...")
        try:
            result = test_func()
            if isinstance(result, tuple):
                success, data = result
                results[test_name] = {"success": success, "data": data}
            else:
                results[test_name] = {"success": result, "data": None}
        except Exception as e:
            print(f"❌ {test_name} failed with exception: {e}")
            results[test_name] = {"success": False, "data": str(e)}

    # Summary
    print("\n" + "=" * 50)
    print("📊 DEBUG SUMMARY")
    print("=" * 50)

    for test_name, result in results.items():
        status = "✅ PASS" if result["success"] else "❌ FAIL"
        print(f"{status} {test_name}")
        if not result["success"] and result["data"]:
            print(f"      Error: {result['data']}")

    # Recommendations
    print("\n🔧 RECOMMENDATIONS:")

    if not results.get("Classification Agent", {}).get("success"):
        print("   - Check Ollama service is running and accessible")
        print("   - Verify LLM models are loaded")

    if not results.get("Conversation Flow", {}).get("success"):
        print("   - Check conversation.py for errors")
        print("   - Verify knowledge base connectivity")

    if not results.get("Backend API", {}).get("success"):
        print("   - Check backend service is running on correct port")
        print("   - Verify API endpoints are accessible")

    if not results.get("Frontend Config", {}).get("success"):
        print("   - Check frontend environment configuration")
        print("   - Verify API endpoint URLs")


if __name__ == "__main__":
    asyncio.run(main())
