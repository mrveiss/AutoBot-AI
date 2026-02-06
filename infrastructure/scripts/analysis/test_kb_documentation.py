#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test knowledge base documentation reading functionality
"""

import asyncio
import logging
import sys

sys.path.insert(0, "/home/kali/Desktop/AutoBot")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_documentation_search():
    """Test searching for documentation in knowledge base"""
    try:
        from src.config import config as global_config
        from src.knowledge_base import KnowledgeBase

        # Initialize knowledge base
        kb = KnowledgeBase(config_manager=global_config)
        await kb.ainit()

        # Test documentation-related searches
        documentation_queries = [
            "how to setup autobot",
            "docker configuration",
            "deployment guide",
            "installation instructions",
            "system requirements",
            "configuration files",
            "autobot documentation",
            "architecture overview",
            "troubleshooting guide",
            "API endpoints",
        ]

        logger.info("Testing documentation searches...")
        results_found = 0

        for query in documentation_queries:
            logger.info(f"\n=== Searching for: '{query}' ===")
            try:
                results = await kb.search(query, top_k=3)
                logger.info(f"Results: {len(results)}")

                if results:
                    results_found += len(results)
                    for i, result in enumerate(results[:2], 1):
                        content_preview = (
                            result["content"][:200] + "..."
                            if len(result["content"]) > 200
                            else result["content"]
                        )
                        logger.info(f"Result {i}: {content_preview}")
                        logger.info(f"Score: {result.get('score', 'N/A')}")
                        logger.info(
                            f"Source: {result.get('metadata', {}).get('source', 'Unknown')}"
                        )
                else:
                    logger.warning(f"No results found for '{query}'")

            except Exception as e:
                logger.error(f"Search failed for '{query}': {e}")

        # Get overall stats
        try:
            stats = await kb.get_stats()
            logger.info("\n=== Knowledge Base Stats ===")
            logger.info(f"Total documents: {stats.get('total_documents', 0)}")
            logger.info(f"Total chunks: {stats.get('total_chunks', 0)}")
            logger.info(f"Total facts: {stats.get('total_facts', 0)}")
            logger.info(f"Categories: {stats.get('categories', [])}")
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")

        logger.info("\n=== SUMMARY ===")
        logger.info(f"Total results found across all queries: {results_found}")

        if results_found > 0:
            logger.info("✅ Knowledge base documentation search is working")
            return True
        else:
            logger.warning(
                "⚠️ Knowledge base contains data but no documentation matches found"
            )
            return False

    except Exception as e:
        logger.error(f"❌ Knowledge base test failed: {e}")
        import traceback

        traceback.print_exc()
        return False


async def test_specific_autobot_docs():
    """Test searching for specific AutoBot documentation"""
    try:
        from src.config import config as global_config
        from src.knowledge_base import KnowledgeBase

        kb = KnowledgeBase(config_manager=global_config)
        await kb.ainit()

        # Test AutoBot-specific documentation
        autobot_queries = [
            "what is autobot platform",
            "autobot features capabilities",
            "autobot architecture components",
            "how to use autobot",
            "autobot system administration",
        ]

        logger.info("\n=== Testing AutoBot-Specific Documentation ===")
        for query in autobot_queries:
            logger.info(f"\nSearching: '{query}'")
            results = await kb.search(query, top_k=2)

            if results:
                for result in results:
                    content = result["content"]
                    # Look for AutoBot-specific content
                    if "autobot" in content.lower() or "autonomous" in content.lower():
                        logger.info(f"✅ Found AutoBot content: {content[:150]}...")
                        logger.info(f"Score: {result.get('score', 'N/A')}")
                        break
                else:
                    logger.warning("Results found but no AutoBot-specific content")
            else:
                logger.warning(f"No results for '{query}'")

    except Exception as e:
        logger.error(f"AutoBot documentation test failed: {e}")


if __name__ == "__main__":
    asyncio.run(test_documentation_search())
    asyncio.run(test_specific_autobot_docs())
