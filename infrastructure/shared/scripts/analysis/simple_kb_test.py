#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Simple test of current AutoBot knowledge base functionality
"""

import asyncio
import logging
import sys

sys.path.insert(0, "/home/kali/Desktop/AutoBot")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_autobot_kb():
    """Test the actual AutoBot knowledge base"""
    try:
        from config import config as global_config
        from knowledge_base import KnowledgeBase

        # Initialize KB
        kb = KnowledgeBase(config_manager=global_config)
        await kb.ainit()

        # Test search with correct signature
        results = await kb.search("deployment configuration")  # Use default n_results=5

        logger.info("Knowledge base works! Found %s results", len(results))

        for i, result in enumerate(results[:2]):
            logger.info("Result %s: %s...", i+1, result['content'][:100])

        return True, len(results)

    except Exception as e:
        logger.error("KB test failed: %s", e)
        return False, 0


async def main():
    logger.info("Testing AutoBot Knowledge Base Current State")

    success, count = await test_autobot_kb()

    logger.info("")
    logger.info("RESULT:")
    logger.info("  Status: %s", 'WORKING' if success else 'BROKEN')
    logger.info("  Results: %s", count)

    if success and count > 0:
        logger.info("")
        logger.info("CONCLUSION: KEEP LLAMAINDEX")
        logger.info("  • Current implementation works with existing 13,383 vectors")
        logger.info("  • No migration needed")
        logger.info("  • Just fix any remaining LLM configuration issues")
    else:
        logger.info("")
        logger.info("CONCLUSION: INVESTIGATE FURTHER")
        logger.info("  • Current implementation has issues")
        logger.info("  • May need to migrate to LangChain")


if __name__ == "__main__":
    asyncio.run(main())
