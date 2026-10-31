#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test the yes/no research dialogue workflow
"""

import asyncio
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# A backend tool (#18289): it deliberately drives backend internals. It puts the backend and the
# repository root (for `autobot_shared`) on its own path, so it runs from any directory with no
# PYTHONPATH; the backend's Python dependencies must be installed.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

# Setup logging
logging.basicConfig(level=logging.INFO)


async def test_research_dialogue():
    """Test the research dialogue workflow"""
    from async_chat_workflow import process_chat_message_with_timeout

    logger.info("=== Testing Research Dialogue Workflow ===\n")

    # Test 1: Unknown topic that should trigger research question
    try:
        logger.info("1. Testing unknown topic (should ask for research)...")
        result = await asyncio.wait_for(
            process_chat_message_with_timeout("tell me about quantum computing in 2024", "test-chat"),
            timeout=15.0,
        )

        logger.info("✅ Response: %s", result.response)
        logger.info("   Knowledge Status: %s", result.knowledge_status.value)
        logger.info("   Processing Time: %.2fs\n", result.processing_time)

    except Exception as e:
        logger.error("❌ Test 1 failed: %s\n", e)

    # Test 2: "Yes" response
    try:
        logger.info("2. Testing 'yes' response...")
        result = await asyncio.wait_for(process_chat_message_with_timeout("yes", "test-chat"), timeout=10.0)

        logger.info("✅ Response: %s", result.response)
        logger.info("   Knowledge Status: %s\n", result.knowledge_status.value)

    except Exception as e:
        logger.error("❌ Test 2 failed: %s\n", e)

    # Test 3: "No" response
    try:
        logger.info("3. Testing 'no' response...")
        result = await asyncio.wait_for(process_chat_message_with_timeout("no", "test-chat"), timeout=10.0)

        logger.info("✅ Response: %s", result.response)
        logger.info("   Knowledge Status: %s\n", result.knowledge_status.value)

    except Exception as e:
        logger.error("❌ Test 3 failed: %s\n", e)


if __name__ == "__main__":
    asyncio.run(test_research_dialogue())
