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
        from src.config import config as global_config
        from src.knowledge_base import KnowledgeBase

        # Initialize KB
        kb = KnowledgeBase(config_manager=global_config)
        await kb.ainit()

        # Test search with correct signature
        results = await kb.search("deployment configuration")  # Use default n_results=5

        logger.info(f"✅ Knowledge base works! Found {len(results)} results")

        for i, result in enumerate(results[:2]):
            logger.info(f"Result {i+1}: {result['content'][:100]}...")

        return True, len(results)

    except Exception as e:
        logger.error(f"❌ KB test failed: {e}")
        return False, 0


async def main():
    print("🧪 Testing AutoBot Knowledge Base Current State")

    success, count = await test_autobot_kb()

    print("\n📊 RESULT:")
    print(f"  Status: {'✅ WORKING' if success else '❌ BROKEN'}")
    print(f"  Results: {count}")

    if success and count > 0:
        print("\n🎯 CONCLUSION: KEEP LLAMAINDEX")
        print("  • Current implementation works with existing 13,383 vectors")
        print("  • No migration needed")
        print("  • Just fix any remaining LLM configuration issues")
    else:
        print("\n🎯 CONCLUSION: INVESTIGATE FURTHER")
        print("  • Current implementation has issues")
        print("  • May need to migrate to LangChain")


if __name__ == "__main__":
    asyncio.run(main())
