#!/usr/bin/env python3
"""Debug script to test Knowledge Base search directly and identify the parameter issue."""

import asyncio
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_knowledge_base():
    """Test knowledge base search directly."""
    try:
        # Import knowledge base directly to avoid circular import
        try:
            from src.knowledge_base_v2 import KnowledgeBaseV2
            logger.info("Using KnowledgeBaseV2")
            kb = KnowledgeBaseV2()
            await kb.initialize()
        except ImportError:
            logger.info("KnowledgeBaseV2 not available, using standard KnowledgeBase")
            from src.knowledge_base import KnowledgeBase
            kb = KnowledgeBase()
            await kb._ensure_redis_initialized()

        logger.info(f"Knowledge base class: {kb.__class__.__name__}")

        # Test the search method directly
        query = "test"
        top_k = 5

        logger.info(f"Testing search with query='{query}', top_k={top_k}")

        # Check which parameters the search method expects
        import inspect
        search_method = getattr(kb, 'search')
        sig = inspect.signature(search_method)
        logger.info(f"Search method signature: {sig}")

        # Try the search
        if 'top_k' in sig.parameters:
            logger.info("Using 'top_k' parameter")
            results = await kb.search(query=query, top_k=top_k)
        elif 'similarity_top_k' in sig.parameters:
            logger.info("Using 'similarity_top_k' parameter")
            results = await kb.search(query=query, similarity_top_k=top_k)
        else:
            logger.error(f"Unknown parameter names in search method: {list(sig.parameters.keys())}")
            return

        logger.info(f"Search results: {len(results)} found")
        for i, result in enumerate(results[:3]):
            logger.info(f"Result {i+1}: {result}")

    except Exception as e:
        logger.error(f"Error testing knowledge base: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_knowledge_base())
