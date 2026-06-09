# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fresh Knowledge Base Stats Endpoint - Bypasses All Caching
This creates a completely new knowledge base instance for testing the fixes
"""

import asyncio

from fastapi import APIRouter, Depends, Request

from api.schemas_knowledge import (
    KnowledgeDebugRedisResponse,
    KnowledgeFreshStatsResponse,
    KnowledgeRebuildIndexResponse,
)
from auth_middleware import check_admin_permission
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_management.types import DATABASE_MAPPING
from constants.threshold_constants import TimingConstants

router = APIRouter(
    dependencies=[Depends(check_admin_permission)],
)
logger = get_logger(__name__)


@router.get("/fresh_stats", response_model=KnowledgeFreshStatsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fresh_knowledge_stats",
    error_code_prefix="KNOWLEDGE_DEBUG",
)
async def get_fresh_knowledge_stats(request: Request = None):
    """Get knowledge base stats using a completely fresh instance (bypasses all cache)"""
    try:
        logger.info("=== Creating completely fresh knowledge base instance ===")

        # Import here to ensure fresh module loading
        import importlib
        import sys

        # Force reload the knowledge base module
        if "src.knowledge_base" in sys.modules:
            importlib.reload(sys.modules["src.knowledge_base"])

        from knowledge_base import KnowledgeBase

        # Create completely fresh instance
        kb = KnowledgeBase()

        # Wait for async initialization
        logger.info("Waiting for knowledge base initialization...")
        await asyncio.sleep(TimingConstants.KB_INIT_DELAY)

        # Get fresh stats
        logger.info("Getting fresh stats...")
        stats = await kb.get_stats()

        logger.info("Fresh stats retrieved: %s", stats)

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
                "mismatch": (stats.get("total_documents", 0) != stats.get("indexed_documents", 0)),
            },
        }

    except Exception as e:
        logger.error("Error getting fresh KB stats: %s", e)
        import traceback

        traceback.print_exc()
        return {
            "source": "completely_fresh_instance",
            "error": "Internal server error",
            "total_documents": 0,
            "total_chunks": 0,
            "total_facts": 0,
            "categories": [],
            "status": "error",
            "message": "Fresh instance failed",
        }


@router.get("/debug_redis", response_model=KnowledgeDebugRedisResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="debug_redis_connection",
    error_code_prefix="KNOWLEDGE_DEBUG",
)
async def debug_redis_connection():
    """Debug Redis connection and vector counts using canonical utility.

    This follows CLAUDE.md "🔴 REDIS CLIENT USAGE" policy.
    Uses DB 1 (knowledge) for knowledge base debugging.
    """
    try:
        # Use canonical Redis utility instead of direct instantiation
        from autobot_shared.redis_client import get_redis_client

        redis_client = get_redis_client(database="knowledge")
        if redis_client is None:
            raise ValueError("Redis client initialization returned None - check Redis configuration")

        # Issue #361 - avoid blocking - wrap Redis ops in thread pool
        def _debug_redis_connection():
            # Test connection
            redis_client.ping()

            # Count vectors directly
            vector_keys = []
            for key in redis_client.scan_iter(match="llama_index/vector_*"):
                vector_keys.append(key.decode("utf-8") if isinstance(key, bytes) else str(key))

            # Get FT.INFO
            try:
                ft_info = redis_client.execute_command("FT.INFO", "llama_index")
                indexed_docs = 0
                for i, item in enumerate(ft_info):
                    if isinstance(item, bytes):
                        item = item.decode()
                    if item == "num_docs" and i + 1 < len(ft_info):
                        indexed_docs = int(ft_info[i + 1])
                        break
            except Exception:
                logger.exception("Error querying FT.INFO")
                indexed_docs = "Error: unable to query index"

            return vector_keys, indexed_docs

        vector_keys, indexed_docs = await asyncio.to_thread(_debug_redis_connection)

        return {
            "redis_connection": "successful",
            "database": DATABASE_MAPPING["knowledge"],
            "vector_keys_found": len(vector_keys),
            "sample_keys": vector_keys[:5],
            "indexed_documents": indexed_docs,
            "mismatch_detected": (len(vector_keys) != indexed_docs if isinstance(indexed_docs, int) else True),
        }

    except Exception:
        logger.exception("Unexpected error")

        return {"redis_connection": "failed", "error": "Internal server error"}


@router.post("/rebuild_index", response_model=KnowledgeRebuildIndexResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rebuild_search_index",
    error_code_prefix="KNOWLEDGE_DEBUG",
)
async def rebuild_search_index():
    """Rebuild the search index to sync vectors with search index"""
    try:
        logger.info("=== Rebuilding search index ===")

        from knowledge_base import KnowledgeBase

        # Create fresh instance
        kb = KnowledgeBase()
        await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)

        # Rebuild index
        result = await kb.rebuild_search_index()

        logger.info("Index rebuild result: %s", result)

        return {
            "operation": "rebuild_search_index",
            "result": result,
            "success": result.get("status") == "success",
        }

    except Exception as e:
        logger.error("Error rebuilding index: %s", e)
        return {
            "operation": "rebuild_search_index",
            "error": "Internal server error",
            "success": False,
        }
