# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Search Analytics API (Issue #78).

Extracted from knowledge_search.py (#16665) to keep that file's own growth
within its grandfathered line-count ceiling (#14236) -- these three endpoints
track search quality/usage and never return knowledge-base facts to the
caller, so they carry no fact-visibility concern.

Endpoints:
- GET  /search_analytics - Search performance metrics
- POST /record_click     - Click-through rate tracking
- POST /expand_query     - Query expansion preview
"""

from fastapi import APIRouter, Depends, HTTPException

from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from knowledge.schemas import ExpandQueryResponse, RecordClickResponse, SearchAnalyticsResponse

router = APIRouter(tags=["knowledge-search"], dependencies=[Depends(get_current_user)])


@router.get("/search_analytics", response_model=SearchAnalyticsResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_search_analytics",
    error_code_prefix="KNOWLEDGE_SEARCH",
)
async def get_search_analytics():
    """
    Get search analytics and performance metrics.

    Issue #78: Search analytics dashboard data.

    Returns:
    - total_searches: Total number of searches
    - unique_queries: Number of unique queries
    - avg_results: Average results per search
    - failed_search_rate: Rate of searches with 0 results
    - click_through_rate: Rate of result clicks
    - avg_duration_ms: Average search duration
    - popular_queries: Most searched queries
    - recent_failed_queries: Recent searches with no results
    """
    try:
        from knowledge.search_quality import get_search_analytics

        analytics = get_search_analytics()
        return {
            "success": True,
            "analytics": analytics.get_search_performance_stats(),
        }
    except ImportError:
        return {
            "success": False,
            "message": "Search analytics not available",
            "analytics": {},
        }


@router.post("/record_click", response_model=RecordClickResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_search_click",
    error_code_prefix="KNOWLEDGE_SEARCH",
)
async def record_search_click(request: dict):
    """
    Record a search result click for analytics.

    Issue #78: Click-through rate tracking.

    Request body:
    - query: The search query
    - result_id: ID of the clicked result
    - session_id: Optional session identifier
    """
    try:
        from knowledge.search_quality import get_search_analytics

        query = request.get("query", "")
        result_id = request.get("result_id", "")
        session_id = request.get("session_id")

        if not query or not result_id:
            raise HTTPException(
                status_code=400,
                detail="query and result_id are required",
            )

        analytics = get_search_analytics()
        analytics.record_click(query, result_id, session_id)

        return {"success": True, "message": "Click recorded"}

    except ImportError:
        return {"success": False, "message": "Search analytics not available"}


@router.post("/expand_query", response_model=ExpandQueryResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="expand_query",
    error_code_prefix="KNOWLEDGE_SEARCH",
)
async def expand_query(request: dict):
    """
    Expand a query with synonyms and related terms.

    Issue #78: Query expansion preview.

    Request body:
    - query: The search query to expand

    Returns:
    - original_query: The input query
    - expanded_queries: List of expanded query variations
    """
    try:
        from knowledge.search_quality import get_query_expander

        query = request.get("query", "")
        if not query:
            raise HTTPException(status_code=400, detail="Query is required")

        expander = get_query_expander()
        expanded = expander.expand_query(query)

        return {
            "success": True,
            "original_query": query,
            "expanded_queries": expanded,
            "expansion_count": len(expanded),
        }

    except ImportError:
        return {
            "success": False,
            "message": "Query expansion not available",
            "expanded_queries": [query],
        }
