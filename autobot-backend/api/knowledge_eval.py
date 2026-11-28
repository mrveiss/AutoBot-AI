# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Test endpoint for Knowledge Base functionality
This bypasses cached instances and creates fresh knowledge base for testing
"""

from fastapi import APIRouter, Depends

from api.schemas_knowledge import KnowledgeFreshStatsData, KnowledgeRebuildIndexData
from auth_middleware import check_admin_permission, get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge_factory import get_knowledge_base_async

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = get_logger(__name__)


@router.get("/test/fresh_stats", response_model=KnowledgeFreshStatsData)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fresh_kb_stats",
    error_code_prefix="KNOWLEDGE_TEST",
)
async def get_fresh_kb_stats():
    """Get knowledge base stats using a fresh instance (bypasses cache)"""
    try:
        # D5 (#18122): the canonical instance, already initialised -- no private KB
        kb = await get_knowledge_base_async()
        if kb is None:
            raise RuntimeError("Knowledge base unavailable (init failed or cooling down)")

        # Get stats
        stats = await kb.get_stats()

        logger.info(f"Fresh KB stats: {stats}")

        return {"source": "fresh_instance", "stats": stats, "success": True}

    except Exception:
        logger.error("Error getting fresh KB stats")
        return {
            "source": "fresh_instance",
            "error": "Internal server error",
            "success": False,
        }


@router.post("/test/rebuild_index", response_model=KnowledgeRebuildIndexData)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_rebuild_search_index",
    error_code_prefix="KNOWLEDGE_TEST",
)
async def test_rebuild_search_index(_: bool = Depends(check_admin_permission)):
    """Test rebuilding the search index"""
    try:
        kb = await get_knowledge_base_async()
        if kb is None:
            raise RuntimeError("Knowledge base unavailable (init failed or cooling down)")

        # Attempt to rebuild search index
        result = await kb.rebuild_search_index()

        logger.info(f"Index rebuild result: {result}")

        return {
            "operation": "rebuild_search_index",
            "result": result,
            "success": result.get("status") == "success",
        }

    except Exception:
        logger.error("Error rebuilding search index")
        return {
            "operation": "rebuild_search_index",
            "error": "Internal server error",
            "success": False,
        }
