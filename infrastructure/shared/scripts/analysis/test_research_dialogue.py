#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test the yes/no research dialogue workflow
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

# Setup logging
logging.basicConfig(level=logging.INFO)


async def test_research_dialogue():
    """Test the research dialogue workflow"""
    from chat_workflow import process_chat_message

    logger.info("=== Testing Research Dialogue Workflow ===\n")

    # Test 1: Unknown topic that should trigger research question
    try:
        logger.info("1. Testing unknown topic (should ask for research)...")
        result = await asyncio.wait_for(
            process_chat_message(
                "tell me about quantum computing in 2024", "test-chat"
            ),
            timeout=15.0,
        )

        logger.info(f"✅ Response: {result.response}")
        logger.info(f"   Knowledge Status: {result.knowledge_status.value}")
        logger.info(f"   Processing Time: {result.processing_time:.2f}s\n")

    except Exception as e:
        logger.error(f"❌ Test 1 failed: {e}\n")

    # Test 2: "Yes" response
    try:
        logger.info("2. Testing 'yes' response...")
        result = await asyncio.wait_for(
            process_chat_message("yes", "test-chat"), timeout=10.0
        )

        logger.info(f"✅ Response: {result.response}")
        logger.info(f"   Knowledge Status: {result.knowledge_status.value}\n")

    except Exception as e:
        logger.error(f"❌ Test 2 failed: {e}\n")

    # Test 3: "No" response
    try:
        logger.info("3. Testing 'no' response...")
        result = await asyncio.wait_for(
            process_chat_message("no", "test-chat"), timeout=10.0
        )

        logger.info(f"✅ Response: {result.response}")
        logger.info(f"   Knowledge Status: {result.knowledge_status.value}\n")

    except Exception as e:
        logger.error(f"❌ Test 3 failed: {e}\n")


if __name__ == "__main__":
    asyncio.run(test_research_dialogue())
