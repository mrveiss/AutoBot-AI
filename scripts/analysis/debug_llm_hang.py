#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Debug script to isolate the LLM hanging issue
"""

import asyncio
import sys
import os
import logging

# Add the project root to Python path
sys.path.append('/home/kali/Desktop/AutoBot')

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)


async def test_llm_interface():
    """Test the LLMInterface directly to see where it hangs"""
    try:
        print("=== Testing LLMInterface directly ===")

        # Import LLMInterface
        print("Step 1: Importing LLMInterface...")
        from src.llm_interface import LLMInterface
        print("✅ LLMInterface imported successfully")

        # Create instance
        print("Step 2: Creating LLMInterface instance...")
        llm = LLMInterface()
        print("✅ LLMInterface instance created successfully")

        # Test simple message
        print("Step 3: Testing simple chat completion...")
        messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Hello, can you hear me?"}
        ]

        print("Step 4: Calling chat_completion...")
        start_time = asyncio.get_event_loop().time()

        # Add timeout to see where it hangs
        try:
            response = await asyncio.wait_for(
                llm.chat_completion(messages=messages, llm_type="orchestrator"),
                timeout=10.0  # 10 second timeout for debugging
            )
            end_time = asyncio.get_event_loop().time()
            print(f"✅ LLM response received in {end_time - start_time:.2f} seconds")
            print(f"Response type: {type(response)}")
            print(f"Response keys: {response.keys() if isinstance(response, dict) else 'N/A'}")

        except asyncio.TimeoutError:
            print("❌ LLM call timed out after 10 seconds")
            return False
        except Exception as e:
            print(f"❌ LLM call failed with exception: {e}")
            return False

        return True

    except Exception as e:
        print(f"❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_simple_workflow():
    """Test the SimpleChatWorkflow to see where it hangs"""
    try:
        print("=== Testing SimpleChatWorkflow ===")

        print("Step 1: Importing SimpleChatWorkflow...")
        from src.simple_chat_workflow import SimpleChatWorkflow
        print("✅ SimpleChatWorkflow imported successfully")

        print("Step 2: Creating SimpleChatWorkflow instance...")
        workflow = SimpleChatWorkflow()
        print("✅ SimpleChatWorkflow instance created successfully")

        print("Step 3: Testing simple message processing...")
        start_time = asyncio.get_event_loop().time()

        try:
            result = await asyncio.wait_for(
                workflow.process_message("Hello, can you help me?", chat_id="test123"),
                timeout=15.0  # 15 second timeout
            )
            end_time = asyncio.get_event_loop().time()
            print(f"✅ Workflow completed in {end_time - start_time:.2f} seconds")
            print(f"Response length: {len(result.response)}")
            print(f"Response preview: {result.response[:100]}...")

        except asyncio.TimeoutError:
            print("❌ Workflow timed out after 15 seconds")
            return False
        except Exception as e:
            print(f"❌ Workflow failed with exception: {e}")
            import traceback
            traceback.print_exc()
            return False

        return True

    except Exception as e:
        print(f"❌ Workflow test failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return False


async def test_ollama_direct():
    """Test direct Ollama connection to verify it's working"""
    try:
        print("=== Testing Direct Ollama Connection ===")

        import aiohttp
        import json

        print("Step 1: Testing Ollama health endpoint...")
        async with aiohttp.ClientSession() as session:
            async with session.get("ServiceURLs.OLLAMA_LOCAL/api/tags") as response:
                if response.status == 200:
                    data = await response.json()
                    models = [model["name"] for model in data.get("models", [])]
                    print(f"✅ Ollama is healthy, available models: {models}")
                else:
                    print(f"❌ Ollama health check failed: HTTP {response.status}")
                    return False

        print("Step 2: Testing simple Ollama chat...")
        chat_data = {
            "model": "llama3.2:1b",
            "messages": [{"role": "user", "content": "Say 'Hello World'"}],
            "stream": False  # Non-streaming for simplicity
        }

        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                "ServiceURLs.OLLAMA_LOCAL/api/chat",
                json=chat_data,
                headers={"Content-Type": "application/json"}
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    content = data.get("message", {}).get("content", "")
                    print(f"✅ Ollama direct test successful: {content}")
                    return True
                else:
                    print(f"❌ Ollama direct test failed: HTTP {response.status}")
                    text = await response.text()
                    print(f"Error response: {text}")
                    return False

    except Exception as e:
        print(f"❌ Direct Ollama test failed: {e}")
        import traceback
        from src.constants import NetworkConstants, ServiceURLs
        traceback.print_exc()
        return False


async def main():
    """Run all tests to isolate the hanging issue"""
    print("Starting LLM hang debugging tests...")
    print("="*50)

    # Test 1: Direct Ollama connection
    if not await test_ollama_direct():
        print("❌ Direct Ollama test failed - Ollama service issue")
        return

    print("="*50)

    # Test 2: LLMInterface
    if not await test_llm_interface():
        print("❌ LLMInterface test failed - Issue in LLM interface layer")
        return

    print("="*50)

    # Test 3: SimpleChatWorkflow
    if not await test_simple_workflow():
        print("❌ SimpleChatWorkflow test failed - Issue in workflow layer")
        return

    print("="*50)
    print("🎉 All tests passed - LLM system appears to be working!")

if __name__ == "__main__":
    asyncio.run(main())
