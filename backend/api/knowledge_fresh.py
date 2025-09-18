"""
Fresh Knowledge Base Stats Endpoint - Bypasses All Caching
This creates a completely new knowledge base instance for testing the fixes
"""

from fastapi import APIRouter, Request
import asyncio
import logging

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/fresh_stats")
async def get_fresh_knowledge_stats(request: Request = None):
    """Get knowledge base stats using a completely fresh instance (bypasses all cache)"""
    try:
        logger.info("=== Creating completely fresh knowledge base instance ===")

        # Import here to ensure fresh module loading
        import importlib
        import sys

        # Force reload the knowledge base module
        if 'src.knowledge_base' in sys.modules:
            importlib.reload(sys.modules['src.knowledge_base'])

        from src.knowledge_base import KnowledgeBase

        # Create completely fresh instance
        kb = KnowledgeBase()

        # Wait for async initialization
        logger.info("Waiting for knowledge base initialization...")
        await asyncio.sleep(3)

        # Get fresh stats
        logger.info("Getting fresh stats...")
        stats = await kb.get_stats()

        logger.info(f"Fresh stats retrieved: {stats}")

        # Return in the same format as the regular endpoint
        return {
            "source": "completely_fresh_instance",
            "total_documents": stats.get("total_documents", 0),
            "total_chunks": stats.get("total_chunks", 0),
            "total_facts": stats.get("total_facts", 0),
            "categories": stats.get("categories", []),
            "status": stats.get("status", "unknown"),
            "indexed_documents": stats.get("indexed_documents", 0),
            "vector_index_sync": stats.get("vector_index_sync", False),
            "message": f"Fresh instance stats - {stats.get('status', 'unknown')}",
            "debug_info": {
                "vector_count": stats.get("total_documents", 0),
                "indexed_count": stats.get("indexed_documents", 0),
                "mismatch": stats.get("total_documents", 0) != stats.get("indexed_documents", 0)
            }
        }

    except Exception as e:
        logger.error(f"Error getting fresh KB stats: {e}")
        import traceback
        traceback.print_exc()
        return {
            "source": "completely_fresh_instance",
            "error": str(e),
            "total_documents": 0,
            "total_chunks": 0,
            "total_facts": 0,
            "categories": [],
            "status": "error",
            "message": f"Fresh instance failed: {str(e)}"
        }


@router.get("/debug_redis")
async def debug_redis_connection():
    """Debug Redis connection and vector counts"""
    try:
        import redis
        import aioredis

        # Test direct Redis connection to the knowledge base
        redis_client = redis.Redis(
            host="172.16.168.23",
            port=6379,
            db=1,  # Knowledge base database
            decode_responses=False,
            socket_timeout=5
        )

        # Test connection
        redis_client.ping()

        # Count vectors directly
        vector_keys = []
        for key in redis_client.scan_iter(match="llama_index/vector_*"):
            vector_keys.append(key.decode('utf-8') if isinstance(key, bytes) else str(key))

        # Get FT.INFO
        try:
            ft_info = redis_client.execute_command('FT.INFO', 'llama_index')
            indexed_docs = 0
            for i, item in enumerate(ft_info):
                if isinstance(item, bytes):
                    item = item.decode()
                if item == 'num_docs' and i + 1 < len(ft_info):
                    indexed_docs = int(ft_info[i + 1])
                    break
        except Exception as e:
            indexed_docs = f"Error: {e}"

        return {
            "redis_connection": "successful",
            "database": 1,
            "vector_keys_found": len(vector_keys),
            "sample_keys": vector_keys[:5],
            "indexed_documents": indexed_docs,
            "mismatch_detected": len(vector_keys) != indexed_docs if isinstance(indexed_docs, int) else True
        }

    except Exception as e:
        return {
            "redis_connection": "failed",
            "error": str(e)
        }


@router.post("/rebuild_index")
async def rebuild_search_index():
    """Rebuild the search index to sync vectors with search index"""
    try:
        logger.info("=== Rebuilding search index ===")

        from src.knowledge_base import KnowledgeBase

        # Create fresh instance
        kb = KnowledgeBase()
        await asyncio.sleep(2)

        # Rebuild index
        result = await kb.rebuild_search_index()

        logger.info(f"Index rebuild result: {result}")

        return {
            "operation": "rebuild_search_index",
            "result": result,
            "success": result.get("status") == "success"
        }

    except Exception as e:
        logger.error(f"Error rebuilding index: {e}")
        return {
            "operation": "rebuild_search_index",
            "error": str(e),
            "success": False
        }