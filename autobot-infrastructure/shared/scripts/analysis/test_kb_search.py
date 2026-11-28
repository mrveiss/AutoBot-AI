#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test Knowledge Base Documentation Search
"""

import asyncio
import logging
import sys
from pathlib import Path

# A backend tool (#18289): it deliberately drives backend internals. It puts the backend and the
# repository root (for `autobot_shared`) on its own path, so it runs from any directory with no
# PYTHONPATH; the backend's Python dependencies must be installed.
_REPO_ROOT = Path(__file__).resolve().parents[4]
for _root in (_REPO_ROOT / "autobot-backend", _REPO_ROOT):
    if str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from chat_workflow import ChatWorkflowManager  # noqa: E402
from knowledge_base import KnowledgeBase  # noqa: E402

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_kb_search():
    """Test knowledge base search functionality"""

    logger.info("=== Testing Knowledge Base Search ===")

    # Test 1: Initialize Knowledge Base directly
    try:
        logger.info("\n1. Testing Knowledge Base initialization...")
        kb = KnowledgeBase()
        await kb.ainit()

        # Get stats
        stats = await kb.get_stats()
        logger.info(f"KB Stats: {stats}")

        # Test search for documentation
        logger.info("\n2. Testing documentation search...")
        search_queries = [
            "docker deployment guide",
            "API documentation",
            "configuration setup",
            "installation guide",
            "troubleshooting",
        ]

        for query in search_queries:
            logger.info(f"\nSearching for: '{query}'")
            try:
                results = await kb.search_legacy(query, n_results=3)
                logger.info(f"  Found {len(results)} results")

                for i, result in enumerate(results):
                    content_preview = (
                        result["content"][:100] + "..." if len(result["content"]) > 100 else result["content"]
                    )
                    logger.info(f"  Result {i+1}: {content_preview}")
                    logger.info(f"    Metadata: {result.get('metadata', {})}")
                    logger.info(f"    Score: {result.get('score', 0.0)}")

            except Exception as e:
                logger.error(f"  Error searching: {e}")

    except Exception as e:
        logger.error(f"KB initialization failed: {e}")
        import traceback

        traceback.print_exc()

    # Test 2: Test Chat Workflow Manager
    try:
        logger.info("\n\n=== Testing Chat Workflow Manager ===")
        workflow = ChatWorkflowManager()

        # Test documentation-related queries
        test_messages = [
            "How do I install AutoBot?",
            "Show me the API documentation",
            "What's in the configuration guide?",
            "Help with Docker deployment",
        ]

        for message in test_messages:
            logger.info(f"\nTesting message: '{message}'")
            try:
                result = await workflow.process_message(message)
                logger.info(f"  Message Type: {result.message_type}")
                logger.info(f"  Knowledge Status: {result.knowledge_status}")
                logger.info(f"  KB Results: {len(result.kb_results)}")
                logger.info(f"  Response preview: {result.response[:200]}...")

                if result.kb_results:
                    logger.info("  Knowledge Base results:")
                    for i, kb_result in enumerate(result.kb_results[:2]):
                        content_preview = kb_result.get("content", "")[:100]
                        logger.info(f"    {i+1}: {content_preview}...")

            except Exception as e:
                logger.error(f"  Error in workflow: {e}")
                import traceback

                traceback.print_exc()

    except Exception as e:
        logger.error(f"Workflow initialization failed: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_kb_search())
