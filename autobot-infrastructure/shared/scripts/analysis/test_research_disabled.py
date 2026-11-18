#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test when research agent is disabled
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
            workflow.process_message("tell me about quantum computing in 2024", "test-chat"),
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
