#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test when research agent is disabled
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


async def test_research_disabled():
    """Test behavior when research is disabled"""
    from chat_workflow import ChatWorkflowManager

    logger.info("=== Testing Research Agent Disabled Scenario ===\n")

    # Create workflow manager with research disabled
    workflow = ChatWorkflowManager()
    workflow.web_research_enabled = False  # Simulate disabled research

    try:
        logger.info("Testing unknown topic with research disabled...")
        result = await asyncio.wait_for(
            workflow.process_message(
                "tell me about quantum computing in 2024", "test-chat"
            ),
            timeout=15.0,
        )

        logger.info("✅ Response: %s", result.response)
        logger.info("   Knowledge Status: %s", result.knowledge_status.value)
        logger.info("   Processing Time: %.2fs\n", result.processing_time)

    except Exception as e:
        logger.error("❌ Test failed: %s", e)
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_research_disabled())
