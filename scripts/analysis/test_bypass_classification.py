#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test bypassing the classification agent to see if that's where the hang occurs
"""

import asyncio
import sys
from pathlib import Path

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.agents.llm_failsafe_agent import get_robust_llm_response


async def test_llm_failsafe_direct():
    """Test the LLM failsafe agent directly"""
    print("🤖 Testing LLM Failsafe Agent directly...")

    try:
        prompt = "Say hello back to the user."

        print(f"   Calling get_robust_llm_response with: {prompt}")

        # Set a timeout to catch hangs
        response = await asyncio.wait_for(
            get_robust_llm_response(prompt, context={"test": "direct"}), timeout=15.0
        )

        print("✅ LLM Failsafe response received:")
        print(f"   Tier: {response.tier_used.value}")
        print(f"   Content: {response.content[:100]}...")
        print(f"   Success: {response.success}")

        return True

    except asyncio.TimeoutError:
        print("❌ LLM Failsafe timed out after 15 seconds")
        return False

    except Exception as e:
        print(f"❌ LLM Failsafe failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_classification_without_communication():
    """Test classification logic without agent communication"""
    print("\n🔍 Testing Classification without agent communication...")

    try:
        # Import just the LLM interface directly
        from src.llm_interface import LLMInterface

        llm = LLMInterface()

        # Create a simple classification request
        messages = [
            {
                "role": "system",
                "content": "You are a classification agent. Respond only with valid JSON.",
            },
            {
                "role": "user",
                "content": 'Classify this: \'hello\'. Return {"complexity": "simple", "confidence": 0.9}',
            },
        ]

        print("   Making direct LLM interface call...")

        # Call LLM interface directly
        response = await asyncio.wait_for(
            llm.chat_completion(messages, llm_type="task"), timeout=15.0
        )

        print("✅ Direct LLM interface response:")
        print(f"   Response: {response.get('response', 'No response')[:100]}...")

        return True

    except asyncio.TimeoutError:
        print("❌ Direct LLM interface timed out")
        return False

    except Exception as e:
        print(f"❌ Direct LLM interface failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Test different components to isolate the hang"""
    print("🚀 Bypass Classification Test")
    print("=" * 40)

    # Test LLM failsafe
    llm_result = await test_llm_failsafe_direct()

    # Test direct LLM interface
    direct_result = await test_classification_without_communication()

    if llm_result and direct_result:
        print("\n✅ Both LLM failsafe and direct interface work!")
        print("   The issue is in the classification agent or communication protocol")
    elif direct_result and not llm_result:
        print("\n🚨 LLM failsafe agent is the problem!")
    elif llm_result and not direct_result:
        print("\n🚨 Direct LLM interface is the problem!")
    else:
        print("\n🚨 Both failed - deeper issue!")


if __name__ == "__main__":
    asyncio.run(main())
