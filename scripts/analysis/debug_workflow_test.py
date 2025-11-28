#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test script to debug the exact workflow execution path
"""
import asyncio
import sys
import time

# Add the src directory to the path
sys.path.insert(0, '/home/kali/Desktop/AutoBot')


async def test_llm_interface_directly():
    """Test LLM interface directly to see where it hangs"""
    print("=== Testing LLM Interface Directly ===")

    try:
        # Import and initialize LLM interface
        from src.llm_interface import LLMInterface

        print("✅ LLMInterface imported")

        llm = LLMInterface()
        print("✅ LLMInterface initialized")

        # Prepare test messages
        messages = [
            {
                "role": "system",
                "content": "You are AutoBot, an intelligent Linux automation assistant."
            },
            {
                "role": "user",
                "content": "hello"
            }
        ]

        print("📞 Making chat_completion call...")
        start_time = time.time()

        # Add timeout to the entire operation
        try:
            response = await asyncio.wait_for(
                llm.chat_completion(messages=messages, llm_type="orchestrator"),
                timeout=30.0
            )

            end_time = time.time()
            print(f"✅ Response received in {end_time - start_time:.2f}s")
            print(f"Response type: {type(response)}")

            if isinstance(response, dict):
                print(f"Response keys: {list(response.keys())}")
                if 'message' in response and 'content' in response['message']:
                    content = response['message']['content']
                    preview = content[:100] + "..." if len(content) > 100 else content
                    print(f"Content preview: {preview}")

            return response

        except asyncio.TimeoutError:
            end_time = time.time()
            print(f"🚨 TIMEOUT after {end_time - start_time:.2f}s")
            return None

    except Exception as e:
        print(f"❌ Error in LLM interface test: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_simple_workflow():
    """Test the simple chat workflow to see where it hangs"""
    print("\n=== Testing SimpleChatWorkflow ===")

    try:
        from src.simple_chat_workflow import process_chat_message_simple

        print("✅ SimpleChatWorkflow imported")

        print("📞 Processing message via workflow...")
        start_time = time.time()

        try:
            response = await asyncio.wait_for(
                process_chat_message_simple("hello", "debug-test"),
                timeout=35.0  # Longer timeout to see where it hangs
            )

            end_time = time.time()
            print(f"✅ Workflow response received in {end_time - start_time:.2f}s")
            print(f"Response type: {type(response)}")
            print(f"Response content: {response}")

            return response

        except asyncio.TimeoutError:
            end_time = time.time()
            print(f"🚨 WORKFLOW TIMEOUT after {end_time - start_time:.2f}s")
            return None

    except Exception as e:
        print(f"❌ Error in workflow test: {e}")
        import traceback
        traceback.print_exc()
        return None


async def main():
    """Run all tests"""
    print("🔍 AutoBot Chat Timeout Debug Script")
    print("====================================")

    # Test 1: Direct LLM interface
    llm_result = await test_llm_interface_directly()

    # Test 2: Simple workflow
    workflow_result = await test_simple_workflow()

    print("\n=== Summary ===")
    print(f"LLM Interface Test: {'✅ SUCCESS' if llm_result else '❌ FAILED'}")
    print(f"Workflow Test: {'✅ SUCCESS' if workflow_result else '❌ FAILED'}")

if __name__ == "__main__":
    asyncio.run(main())
