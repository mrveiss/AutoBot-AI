#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test AutoBot identity in knowledge base
"""

import asyncio
import logging
import sys

sys.path.insert(0, '/home/kali/Desktop/AutoBot')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_autobot_identity():
    """Test that AutoBot identity is properly indexed"""
    try:
        from src.knowledge_base import KnowledgeBase
        from src.config import config as global_config

        # Initialize knowledge base
        kb = KnowledgeBase(config_manager=global_config)
        await kb.ainit()

        # Test searches for AutoBot identity
        queries = [
            "what is autobot",
            "autobot platform",
            "linux system administration",
            "autonomous AI assistant"
        ]

        for query in queries:
            logger.info(f"\n=== Testing query: '{query}' ===")
            results = await kb.search(query, top_k=3)
            logger.info(f"Results: {len(results)}")

            for i, result in enumerate(results):
                content_preview = result['content'][:150] + "..." if len(result['content']) > 150 else result['content']
                logger.info(f"Result {i+1}: {content_preview}")
                logger.info(f"Score: {result.get('score', 'N/A')}")

        # Check overall stats
        stats = await kb.get_stats()
        logger.info(f"\nKnowledge base stats: {stats}")

    except Exception as e:
        logger.error(f"Test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_autobot_identity())
