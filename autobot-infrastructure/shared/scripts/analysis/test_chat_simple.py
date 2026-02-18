#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple test to verify ChatWorkflowManager without KB blocking
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


async def test_chat():
    """Test the chat workflow with a simple message"""
    from chat_workflow import process_chat_message

    try:
        logger.info("Testing chat workflow...")
        result = await asyncio.wait_for(
            process_chat_message("hello", "test-chat"), timeout=10.0
        )

        logger.info("✅ Success! Response: %s...", result.response[:100])
        logger.info("   Knowledge Status: %s", result.knowledge_status.value)
        logger.info("   Message Type: %s", result.message_type.value)
        logger.info("   Processing Time: %.2fs", result.processing_time)

    except asyncio.TimeoutError:
        logger.error("❌ Test timed out after 10 seconds")
    except Exception as e:
        logger.error("❌ Test failed: %s", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_chat())
