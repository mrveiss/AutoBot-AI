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
import logging

logger = logging.getLogger(__name__)

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agents.llm_failsafe_agent import get_robust_llm_response


async def test_llm_failsafe_direct():
    """Test the LLM failsafe agent directly"""
    logger.error("🤖 Testing LLM Failsafe Agent directly...")

    try:
        prompt = "Say hello back to the user."

        logger.info(f"   Calling get_robust_llm_response with: {prompt}")

        # Set a timeout to catch hangs
        response = await asyncio.wait_for(
            get_robust_llm_response(prompt, context={"test": "direct"}), timeout=15.0
        )

        logger.error("✅ LLM Failsafe response received:")
        logger.info(f"   Tier: {response.tier_used.value}")
        logger.info(f"   Content: {response.content[:100]}...")
        logger.info(f"   Success: {response.success}")

        return True

    except asyncio.TimeoutError:
        logger.error("❌ LLM Failsafe timed out after 15 seconds")
        return False

    except Exception as e:
        logger.error(f"❌ LLM Failsafe failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_classification_without_communication():
    """Test classification logic without agent communication"""
    logger.info("\n🔍 Testing Classification without agent communication...")

    try:
        # Import just the LLM interface directly
        from llm_interface import LLMInterface

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

        logger.info("   Making direct LLM interface call...")

        # Call LLM interface directly
        response = await asyncio.wait_for(
            llm.chat_completion(messages, llm_type="task"), timeout=15.0
        )

        logger.info("✅ Direct LLM interface response:")
        logger.info(f"   Response: {response.get('response', 'No response')[:100]}...")

        return True

    except asyncio.TimeoutError:
        logger.error("❌ Direct LLM interface timed out")
        return False

    except Exception as e:
        logger.error(f"❌ Direct LLM interface failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Test different components to isolate the hang"""
    logger.info("🚀 Bypass Classification Test")
    logger.info("=" * 40)

    # Test LLM failsafe
    llm_result = await test_llm_failsafe_direct()

    # Test direct LLM interface
    direct_result = await test_classification_without_communication()

    if llm_result and direct_result:
        logger.error("\n✅ Both LLM failsafe and direct interface work!")
        logger.info("   The issue is in the classification agent or communication protocol")
    elif direct_result and not llm_result:
        logger.error("\n🚨 LLM failsafe agent is the problem!")
    elif llm_result and not direct_result:
        logger.info("\n🚨 Direct LLM interface is the problem!")
    else:
        logger.error("\n🚨 Both failed - deeper issue!")


if __name__ == "__main__":
    asyncio.run(main())
