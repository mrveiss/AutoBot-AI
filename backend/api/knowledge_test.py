"""
Test endpoint for Knowledge Base functionality
This bypasses cached instances and creates fresh knowledge base for testing
"""

from fastapi import APIRouter
import asyncio
import logging
from src.constants.network_constants import NetworkConstants

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/test/fresh_stats")
async def get_fresh_kb_stats():
    """Get knowledge base stats using a fresh instance (bypasses cache)"""
    try:
        # Import here to get fresh instance
        from src.knowledge_base import KnowledgeBase

        logger.info("Creating fresh knowledge base instance for testing")

        # Create fresh knowledge base instance
        kb = KnowledgeBase()

        # Wait for initialization
        await asyncio.sleep(2)

        # Get stats
        stats = await kb.get_stats()

        logger.info(f"Fresh KB stats: {stats}")

        return {
            "source": "fresh_instance",
            "stats": stats,
            "success": True
        }

    except Exception as e:
        logger.error(f"Error getting fresh KB stats: {e}")
        return {
            "source": "fresh_instance",
            "error": str(e),
            "success": False
        }


@router.post("/test/rebuild_index")
async def test_rebuild_search_index():
    """Test rebuilding the search index"""
    try:
        from src.knowledge_base import KnowledgeBase

        logger.info("Creating fresh knowledge base for index rebuild")

        # Create fresh knowledge base instance
        kb = KnowledgeBase()

        # Wait for initialization
        await asyncio.sleep(2)

        # Attempt to rebuild search index
        result = await kb.rebuild_search_index()

        logger.info(f"Index rebuild result: {result}")

        return {
            "operation": "rebuild_search_index",
            "result": result,
            "success": result.get("status") == "success"
        }

    except Exception as e:
        logger.error(f"Error rebuilding search index: {e}")
        return {
            "operation": "rebuild_search_index",
            "error": str(e),
            "success": False
        }