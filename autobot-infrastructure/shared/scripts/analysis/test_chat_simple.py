#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Simple test to verify ChatWorkflowManager without KB blocking
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


async def test_chat():
    """Test the chat workflow with a simple message"""
    from async_chat_workflow import process_chat_message_with_timeout

    try:
        logger.info("Testing chat workflow...")
        result = await asyncio.wait_for(process_chat_message_with_timeout("hello", "test-chat"), timeout=10.0)

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
