#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test bypassing the classification agent to see if that's where the hang occurs
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# #14518: the path insert here pointed at a ``src`` directory that does not
# exist beside this script, and ``llm_interface`` is a pre-restructure module
# name. The canonical entry point is services.llm_service.get_llm_service (#18552). Add
# autobot-backend the way the other operator entry points in this tree do
# (#14129).
# A backend tool (#18289): it also puts the repository root on the path (for `autobot_shared`), so it
# runs from any directory with no PYTHONPATH.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from agents.llm_failsafe_agent import get_robust_llm_response  # noqa: E402


async def test_llm_failsafe_direct():
    """Test the LLM failsafe agent directly"""
    logger.info("Testing LLM Failsafe Agent directly...")

    try:
        prompt = "Say hello back to the user."

        logger.info("   Calling get_robust_llm_response with: %s", prompt)

        # Set a timeout to catch hangs
        response = await asyncio.wait_for(get_robust_llm_response(prompt, context={"test": "direct"}), timeout=15.0)

        logger.error("✅ LLM Failsafe response received:")
        logger.info("   Tier: %s", response.tier_used.value)
        logger.info("   Content: %s...", response.content[:100])
        logger.info("   Success: %s", response.success)

        return True

    except asyncio.TimeoutError:
        logger.error("❌ LLM Failsafe timed out after 15 seconds")
        return False

    except Exception as e:
        logger.error("❌ LLM Failsafe failed: %s", e)
        import traceback

        traceback.print_exc()
        return False


async def test_classification_without_communication():
    """Test classification logic without agent communication"""
    logger.info("\n🔍 Testing Classification without agent communication...")

    try:
        # Import just the LLM interface directly
        from services.llm_service import get_llm_service

        llm = get_llm_service()

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
        response = await asyncio.wait_for(llm.chat(messages, llm_type="task"), timeout=15.0)

        logger.info("✅ Direct LLM interface response:")
        logger.info("   Response: %s...", (response.content or "No response")[:100])

        return True

    except asyncio.TimeoutError:
        logger.error("❌ Direct LLM interface timed out")
        return False

    except Exception as e:
        logger.error("❌ Direct LLM interface failed: %s", e)
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
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
