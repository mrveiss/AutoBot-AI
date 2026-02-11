#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test LLM interface directly to see if it's hanging
"""

import asyncio
import sys
import time
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from agents.llm_failsafe_agent import get_robust_llm_response


async def test_llm_direct():
    """Test LLM directly with a simple prompt"""
    logger.info("Testing LLM Failsafe Agent directly...")

    start_time = time.time()

    try:
        # Simple test prompt
        prompt = "Say hello back to the user."

        logger.info("   Sending prompt: %s", prompt)
        logger.info("   Waiting for response...")

        # Get response with 15 second timeout to see if it's faster than 30s
        response = await asyncio.wait_for(
            get_robust_llm_response(prompt, context={"test": True}), timeout=15.0
        )

        elapsed = time.time() - start_time

        logger.info("✅ LLM response received in %.2fs:", elapsed)
        logger.info("   Tier used: %s", response.tier_used.value)
        logger.info("   Model: %s", response.model_used)
        logger.info("   Success: %s", response.success)
        logger.info("   Content: %s...", response.content[:100])
        logger.warning("   Warnings: %s", response.warnings)

        return True

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger.error("❌ LLM request timed out after %.2fs", elapsed)
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("❌ LLM request failed after {elapsed:.2f}s: %s", e)
        import traceback

        traceback.print_exc()
        return False


async def test_classification_direct():
    """Test classification agent directly"""
    logger.info("\n🔍 Testing Classification Agent directly...")

    start_time = time.time()

    try:
        from agents.classification_agent import ClassificationAgent

        agent = ClassificationAgent()

        logger.info("   Classifying 'hello'...")

        # Test with shorter timeout to isolate the issue
        result = await asyncio.wait_for(agent.classify_request("hello"), timeout=10.0)

        elapsed = time.time() - start_time

        logger.info("✅ Classification completed in %.2fs:", elapsed)
        logger.info("   Complexity: %s", result.complexity.value)
        logger.info("   Confidence: %s", result.confidence)
        logger.info("   Reasoning: %s...", result.reasoning[:50])

        return True

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger.error("❌ Classification timed out after %.2fs", elapsed)
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("❌ Classification failed after {elapsed:.2f}s: %s", e)
        import traceback

        traceback.print_exc()
        return False


async def test_kb_search():
    """Test knowledge base search directly"""
    logger.info("\n📚 Testing Knowledge Base search...")

    start_time = time.time()

    try:
        from agents import get_kb_librarian

        kb_librarian = get_kb_librarian()

        logger.info("   Searching KB for 'hello'...")

        # Test KB search with timeout
        result = await asyncio.wait_for(
            kb_librarian.search_knowledge_base(
                query="hello", max_results=5, threshold=0.1
            ),
            timeout=8.0,
        )

        elapsed = time.time() - start_time

        logger.info("✅ KB search completed in %.2fs:", elapsed)
        if result and result.get("documents"):
            logger.info("   Found %s documents", len(result['documents']))
        else:
            logger.info("   No documents found")

        return True

    except asyncio.TimeoutError:
        elapsed = time.time() - start_time
        logger.error("❌ KB search timed out after %.2fs", elapsed)
        return False

    except Exception as e:
        elapsed = time.time() - start_time
        logger.error("❌ KB search failed after {elapsed:.2f}s: %s", e)
        import traceback

        traceback.print_exc()
        return False


async def main():
    """Run all direct tests to isolate the hanging component"""
    logger.info("🚀 AutoBot Direct Component Test")
    logger.info("=" * 50)

    # Test each component individually with timeouts
    tests = [
        ("Classification Agent", test_classification_direct()),
        ("Knowledge Base Search", test_kb_search()),
        ("LLM Failsafe Agent", test_llm_direct()),
    ]

    for test_name, test_coro in tests:
        logger.info("\n📋 Running %s...", test_name)
        try:
            success = await test_coro
            if not success:
                logger.info("🚨 %s is the likely culprit!", test_name)
        except Exception as e:
            logger.error("❌ {test_name} crashed: %s", e)

    logger.info("\n" + "=" * 50)
    logger.error("🔍 Test completed. Check above for timeouts or failures.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
