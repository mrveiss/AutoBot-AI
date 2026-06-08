# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Test endpoint for Knowledge Base functionality
This bypasses cached instances and creates fresh knowledge base for testing
"""

import asyncio

from fastapi import APIRouter

from api.schemas_common import DataResponse
from api.schemas_knowledge import KnowledgeFreshStatsData, KnowledgeRebuildIndexData
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import TimingConstants

router = APIRouter()
logger = get_logger(__name__)


@router.get("/test/fresh_stats", response_model=DataResponse[KnowledgeFreshStatsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_fresh_kb_stats",
    error_code_prefix="KNOWLEDGE_TEST",
)
async def get_fresh_kb_stats():
    """Get knowledge base stats using a fresh instance (bypasses cache)"""
    try:
        # Import here to get fresh instance
        from knowledge_base import KnowledgeBase

        logger.info("Creating fresh knowledge base instance for testing")

        # Create fresh knowledge base instance
        kb = KnowledgeBase()

        # Wait for initialization
        await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)

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


@router.post("/test/rebuild_index", response_model=DataResponse[KnowledgeRebuildIndexData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="test_rebuild_search_index",
    error_code_prefix="KNOWLEDGE_TEST",
)
async def test_rebuild_search_index():
    """Test rebuilding the search index"""
    try:
        from knowledge_base import KnowledgeBase

        logger.info("Creating fresh knowledge base for index rebuild")

        # Create fresh knowledge base instance
        kb = KnowledgeBase()

        # Wait for initialization
        await asyncio.sleep(TimingConstants.SERVICE_STARTUP_DELAY)

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
