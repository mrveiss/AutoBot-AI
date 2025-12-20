# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Knowledge Base Search API - Search and RAG-enhanced query endpoints.

This module contains all search-related API endpoints for the knowledge base.
Extracted from knowledge.py for better maintainability (Issue #185, #209).

Endpoints:
- POST /search - Basic knowledge search with optional RAG
- POST /enhanced_search - Enhanced search with tags, hybrid mode, reranking
- POST /rag_search - Full RAG-enhanced search with query reformulation
- POST /similarity_search - Similarity search with threshold filtering

Related Issues: #78 (Search Quality), #185 (Split), #209 (Knowledge split)
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException, Request

from backend.api.knowledge_models import EnhancedSearchRequest
from backend.knowledge_factory import get_or_create_knowledge_base
from backend.type_defs.common import Metadata
from src.utils.error_boundaries import ErrorCategory, with_error_handling

# Import RAG Agent for enhanced search capabilities
try:
    from src.agents.rag_agent import get_rag_agent

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logging.warning("RAG Agent not available - enhanced search features disabled")

# Import Advanced RAG Service for reranking
try:
    from backend.services.rag_service import RAGService

    ADVANCED_RAG_AVAILABLE = True
except ImportError:
    ADVANCED_RAG_AVAILABLE = False
    logging.warning("Advanced RAG Service not available - reranking features disabled")

logger = logging.getLogger(__name__)

# Create router for search endpoints
router = APIRouter(tags=["knowledge-search"])

# Performance optimization: O(1) lookup for valid search modes (Issue #326)
VALID_SEARCH_MODES = {"vector", "text", "auto"}


# =============================================================================
# Helper Functions for search endpoints (Issue #281)
# =============================================================================


def _build_search_response(
    results: list,
    query: str,
    mode: str,
    kb_implementation: str,
    *,
    message: str | None = None,
    rag_enhanced: bool = False,
    rag_analysis: dict | None = None,
    reranking_applied: bool = False,
    reranking_method: str | None = None,
) -> dict:
    """
    Build a standardized search response dictionary.

    Issue #281: Extracted helper to reduce repetition in search_knowledge.
    Consolidates 4 similar return blocks into one reusable helper.

    Args:
        results: Search results list
        query: Original search query
        mode: Search mode used
        kb_implementation: Knowledge base class name
        message: Optional status message
        rag_enhanced: Whether RAG enhancement was applied
        rag_analysis: RAG analysis data if enhanced
        reranking_applied: Whether reranking was applied
        reranking_method: Method used for reranking

    Returns:
        Standardized response dictionary
    """
    response = {
        "results": results,
        "total_results": len(results),
        "query": query,
        "mode": mode,
        "kb_implementation": kb_implementation,
    }

    if message:
        response["message"] = message

    if rag_enhanced:
        response["rag_enhanced"] = True
        if rag_analysis:
            response["rag_analysis"] = rag_analysis
    else:
        response["rag_enhanced"] = False

    if reranking_applied:
        response["reranking_applied"] = True
        if reranking_method:
            response["reranking_method"] = reranking_method
    else:
        response["reranking_applied"] = False

    return response


# =============================================================================
# Helper Functions for search_knowledge (Issue #398)
# =============================================================================


async def _execute_kb_search(kb_to_use, query: str, search_limit: int, mode: str) -> list:
    """Execute search on knowledge base (Issue #398: extracted).

    Handles different KB implementations with correct parameters.
    """
    kb_class_name = kb_to_use.__class__.__name__

    if kb_class_name == "KnowledgeBaseV2":
        return await kb_to_use.search(query=query, top_k=search_limit)
    else:
        return await kb_to_use.search(
            query=query, similarity_top_k=search_limit, mode=mode
        )


async def _apply_reranking(query: str, results: list, kb_to_use) -> dict | None:
    """Apply advanced reranking if available (Issue #398: extracted).

    Returns response dict if successful, None if reranking failed.
    """
    if not ADVANCED_RAG_AVAILABLE or not results:
        return None

    try:
        logger.info("Applying advanced reranking to search results")
        rag_service = RAGService(kb_to_use)
        await rag_service.initialize()
        reranked_results = await rag_service.rerank_results(query, results)

        return _build_search_response(
            results=reranked_results,
            query=query,
            mode="reranked",
            kb_implementation=kb_to_use.__class__.__name__,
            reranking_applied=True,
            reranking_method="cross-encoder",
        )
    except Exception as e:
        logger.error(f"Advanced reranking failed: {e}, returning original results")
        return None


async def _apply_rag_enhancement(query: str, results: list, kb_class_name: str) -> dict | None:
    """Apply RAG enhancement if available (Issue #398: extracted).

    Returns response dict if successful, None if RAG failed.
    """
    if not RAG_AVAILABLE or not results:
        return None

    try:
        rag_enhancement = await _enhance_search_with_rag(query, results)
        return _build_search_response(
            results=results,
            query=query,
            mode="rag_enhanced",
            kb_implementation=kb_class_name,
            rag_enhanced=True,
            rag_analysis=rag_enhancement,
        )
    except Exception as e:
        logger.error(f"RAG enhancement failed: {e}")
        return None


# =============================================================================
# Helper Functions for rag_enhanced_search (Issue #281)
# =============================================================================


async def _check_empty_kb_for_rag(kb_to_use, query: str) -> Metadata | None:
    """Check if KB is empty and return early response if so (Issue #281: extracted)."""
    try:
        stats = await kb_to_use.get_stats()
        fact_count = stats.get("total_facts", 0)

        if fact_count == 0:
            logger.info(
                "Knowledge base is empty - "
                "returning empty RAG results immediately"
            )
            return {
                "status": "success",
                "synthesized_response": (
                    "The knowledge base is currently empty. "
                    "Please add documents in the Manage tab to enable search functionality."
                ),
                "results": [],
                "query": query,
                "reformulated_query": query,
                "rag_analysis": {
                    "relevance_score": 0.0,
                    "confidence": 0.0,
                    "sources_used": 0,
                    "synthesis_quality": "empty_kb",
                },
                "message": "Knowledge base is empty",
            }
    except Exception as stats_err:
        logger.warning(f"Could not check KB stats: {stats_err}")

    return None


async def _reformulate_query_if_requested(
    query: str, reformulate_query: bool
) -> List[str]:
    """Reformulate query using RAG agent if requested (Issue #281: extracted)."""
    reformulated_queries = [query]

    if reformulate_query:
        try:
            rag_agent = get_rag_agent()
            reformulation_result = await rag_agent.reformulate_query(query)

            if reformulation_result.get("status") == "success":
                additional_queries = reformulation_result.get(
                    "reformulated_queries", []
                )
                reformulated_queries.extend(
                    additional_queries[:3]
                )  # Limit to avoid too many queries

        except Exception as e:
            logger.warning(f"Query reformulation failed: {e}")

    return reformulated_queries


async def _search_with_all_queries(
    kb_to_use, reformulated_queries: List[str], search_limit: int
) -> List[Metadata]:
    """Search with all reformulated queries and deduplicate (Issue #281: extracted)."""
    all_results = []
    seen_content = set()

    for search_query in reformulated_queries:
        try:
            kb_class_name = kb_to_use.__class__.__name__

            if kb_class_name == "KnowledgeBaseV2":
                query_results = await kb_to_use.search(
                    query=search_query, top_k=search_limit
                )
            else:
                query_results = await kb_to_use.search(
                    query=search_query, similarity_top_k=search_limit
                )

            # Deduplicate results
            for result in query_results:
                content = result.get("content", "")
                if content and content not in seen_content:
                    seen_content.add(content)
                    result["source_query"] = search_query
                    all_results.append(result)

        except Exception as e:
            logger.error(f"Search failed for query '{search_query}': {e}")

    return all_results[:search_limit]


def _convert_results_to_documents(
    results: List[Metadata], original_query: str
) -> List[Metadata]:
    """Convert search results to RAG-compatible document format (Issue #281: extracted)."""
    documents = []
    for result in results:
        documents.append(
            {
                "content": result.get("content", ""),
                "metadata": {
                    "filename": (
                        result.get("metadata", {}).get("title", "Unknown")
                    ),
                    "source": (
                        result.get("metadata", {}).get(
                            "source", "knowledge_base"
                        )
                    ),
                    "category": (
                        result.get("metadata", {}).get("category", "general")
                    ),
                    "score": result.get("score", 0.0),
                    "source_query": result.get("source_query", original_query),
                },
            }
        )
    return documents


async def _process_with_rag_agent(
    original_query: str,
    all_results: List[Metadata],
    reformulated_queries: List[str],
    kb_to_use,
) -> Metadata:
    """Process results with RAG agent for synthesis (Issue #281: extracted)."""
    try:
        rag_agent = get_rag_agent()
        documents = _convert_results_to_documents(all_results, original_query)

        rag_result = await rag_agent.process_document_query(
            query=original_query,
            documents=documents,
            context={"reformulated_queries": reformulated_queries},
        )

        return {
            "status": "success",
            "synthesized_response": rag_result.get("synthesized_response", ""),
            "confidence_score": rag_result.get("confidence_score", 0.0),
            "document_analysis": rag_result.get("document_analysis", {}),
            "sources_used": rag_result.get("sources_used", []),
            "results": all_results,
            "total_results": len(all_results),
            "original_query": original_query,
            "reformulated_queries": (
                reformulated_queries[1:] if len(reformulated_queries) > 1 else []
            ),
            "kb_implementation": kb_to_use.__class__.__name__,
            "agent_metadata": rag_result.get("metadata", {}),
            "rag_enhanced": True,
        }

    except Exception as e:
        logger.error(f"RAG processing failed: {e}")
        return {
            "status": "partial_success",
            "synthesized_response": (
                f"Found {len(all_results)} relevant documents but synthesis failed: {str(e)}"
            ),
            "results": all_results,
            "total_results": len(all_results),
            "original_query": original_query,
            "reformulated_queries": (
                reformulated_queries[1:] if len(reformulated_queries) > 1 else []
            ),
            "error": str(e),
            "rag_enhanced": False,
        }


# ===== SEARCH ENDPOINTS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search_knowledge",
    error_code_prefix="KB",
)
@router.post("/search")
async def search_knowledge(request: dict, req: Request):
    """
    Search knowledge base with optional RAG enhancement (Issue #398: refactored).
    FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        return {
            "results": [],
            "total_results": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    # Parse request parameters
    query = request.get("query", "")
    top_k = request.get("top_k", 10)
    limit = request.get("limit", 10)
    mode = request.get("mode", "auto")
    use_rag = request.get("use_rag", False)
    enable_reranking = request.get("enable_reranking", False)
    search_limit = limit if request.get("limit") is not None else top_k
    kb_class_name = kb_to_use.__class__.__name__

    logger.info(
        f"Knowledge search request: '{query}' (top_k={search_limit}, mode={mode}, "
        f"use_rag={use_rag}, enable_reranking={enable_reranking})"
    )

    # Check if KB is empty
    try:
        stats = await kb_to_use.get_stats()
        if stats.get("total_facts", 0) == 0:
            logger.info("Knowledge base is empty - returning empty results immediately")
            return _build_search_response(
                results=[], query=query, mode=mode, kb_implementation=kb_class_name,
                message="Knowledge base is empty - no documents to search. "
                        "Add documents in the Manage tab.",
            )
    except Exception as stats_err:
        logger.warning(f"Could not check KB stats: {stats_err}")

    # Execute search
    results = await _execute_kb_search(kb_to_use, query, search_limit, mode)

    # Apply reranking if requested
    if enable_reranking:
        response = await _apply_reranking(query, results, kb_to_use)
        if response:
            return response

    # Apply RAG enhancement if requested (legacy support)
    if use_rag:
        response = await _apply_rag_enhancement(query, results, kb_class_name)
        if response:
            return response

    return _build_search_response(
        results=results, query=query, mode=mode, kb_implementation=kb_class_name
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_search",
    error_code_prefix="KB",
)
@router.post("/enhanced_search")
async def enhanced_search(request: EnhancedSearchRequest, req: Request):
    """
    Enhanced search with tag filtering, hybrid mode, and query preprocessing.

    Issue #78: Search Quality Improvements

    Features:
    - Hybrid search mode (semantic + keyword with RRF)
    - Tag-based filtering (match all or any)
    - Query preprocessing (abbreviation expansion)
    - Minimum score threshold
    - Optional cross-encoder reranking
    - Pagination support

    Request body:
    - query: Search query string
    - limit: Maximum results (default: 10, max: 100)
    - offset: Pagination offset (default: 0)
    - category: Optional category filter
    - tags: Optional list of tags to filter by
    - tags_match_any: If True, match ANY tag. If False, match ALL (default: False)
    - mode: "semantic", "keyword", or "hybrid" (default: "hybrid")
    - enable_reranking: Enable cross-encoder reranking (default: False)
    - min_score: Minimum similarity score 0.0-1.0 (default: 0.0)

    Returns:
    - success: Boolean status
    - results: List of search results
    - total_count: Total matching results (before pagination)
    - query_processed: The preprocessed query used
    - mode: Search mode used
    - tags_applied: Tags used for filtering
    - min_score_applied: Minimum score threshold used
    - reranking_applied: Whether reranking was applied
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "success": False,
            "results": [],
            "total_count": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    # Check if knowledge base supports enhanced_search
    if not hasattr(kb_to_use, "enhanced_search"):
        # Issue #372: Fallback using model method
        logger.warning("KB implementation does not support enhanced_search, using fallback")
        results = await kb_to_use.search(
            query=request.query,
            top_k=request.limit,
            mode=request.get_safe_mode(VALID_SEARCH_MODES),
        )
        return request.get_fallback_response(results)

    # Issue #372: Use model method for log summary
    logger.info(f"Enhanced search: {request.get_log_summary()}")

    # Issue #372: Use model method for search params
    result = await kb_to_use.enhanced_search(**request.to_search_params())

    return result


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_enhanced_search",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/rag_search")
async def rag_enhanced_search(request: dict, req: Request):
    """
    RAG-enhanced knowledge search for comprehensive document synthesis.

    Issue #281: Refactored from 200 lines to use extracted helper methods.

    Features:
    - Query reformulation for better search coverage
    - Multi-query search with deduplication
    - RAG agent synthesis of results
    - Graceful degradation on errors
    """
    if not RAG_AVAILABLE:
        raise HTTPException(
            status_code=503,
            detail="RAG functionality not available - AI Stack may not be running",
        )

    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "status": "error",
            "synthesized_response": "",
            "results": [],
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    query = request.get("query", "")
    top_k = request.get("top_k", 10)
    limit = request.get("limit", 10)
    reformulate_query = request.get("reformulate_query", True)

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    search_limit = limit if request.get("limit") is not None else top_k

    logger.info(
        f"RAG-enhanced search request: '{query}' "
        f"(top_k={search_limit}, reformulate={reformulate_query})"
    )

    # Check if knowledge base is empty (Issue #281: uses helper)
    empty_response = await _check_empty_kb_for_rag(kb_to_use, query)
    if empty_response:
        return empty_response

    # Step 1: Query reformulation (Issue #281: uses helper)
    original_query = query
    reformulated_queries = await _reformulate_query_if_requested(query, reformulate_query)

    # Step 2: Search with all queries (Issue #281: uses helper)
    all_results = await _search_with_all_queries(kb_to_use, reformulated_queries, search_limit)

    # Step 3: RAG processing for synthesis (Issue #281: uses helper)
    if all_results:
        return await _process_with_rag_agent(
            original_query, all_results, reformulated_queries, kb_to_use
        )
    else:
        return {
            "status": "success",
            "synthesized_response": (
                f"No relevant documents found for query: '{original_query}'"
            ),
            "results": [],
            "total_results": 0,
            "original_query": original_query,
            "reformulated_queries": (
                reformulated_queries[1:] if len(reformulated_queries) > 1 else []
            ),
            "rag_enhanced": True,
        }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="similarity_search",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/similarity_search")
async def similarity_search(request: dict, req: Request):
    """
    Perform similarity search with optional RAG enhancement.
    FIXED parameter mismatch between KnowledgeBase and KnowledgeBaseV2.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "results": [],
            "total_results": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }

    query = request.get("query", "")
    top_k = request.get("top_k", 10)
    threshold = request.get("threshold", 0.7)
    use_rag = request.get("use_rag", False)

    logger.info(
        f"Similarity search request: '{query}' "
        f"(top_k={top_k}, threshold={threshold}, use_rag={use_rag})"
    )

    # FIXED: Check which knowledge base implementation we're using and call with correct parameters
    kb_class_name = kb_to_use.__class__.__name__

    if kb_class_name == "KnowledgeBaseV2":
        # KnowledgeBaseV2 uses 'top_k' parameter
        results = await kb_to_use.search(query=query, top_k=top_k)
    else:
        # Original KnowledgeBase uses 'similarity_top_k' parameter
        results = await kb_to_use.search(query=query, similarity_top_k=top_k)

    # Filter by threshold if specified
    if threshold > 0:
        filtered_results = []
        for result in results:
            if result.get("score", 0) >= threshold:
                filtered_results.append(result)
        results = filtered_results

    # Enhanced search with RAG if requested and available
    if use_rag and RAG_AVAILABLE and results:
        try:
            rag_enhancement = await _enhance_search_with_rag(query, results)
            return {
                "results": results,
                "total_results": len(results),
                "query": query,
                "threshold": threshold,
                "kb_implementation": kb_class_name,
                "rag_enhanced": True,
                "rag_analysis": rag_enhancement,
            }
        except Exception as e:
            logger.error(f"RAG enhancement failed: {e}")
            # Continue with regular results if RAG fails

    return {
        "results": results,
        "total_results": len(results),
        "query": query,
        "threshold": threshold,
        "kb_implementation": kb_class_name,
        "rag_enhanced": False,
    }


# =============================================================================
# Issue #78: Enhanced Search v2 and Analytics Endpoints
# =============================================================================


def _extract_search_v2_params(request: dict) -> dict:
    """Extract enhanced_search_v2 parameters from request (Issue #398: extracted)."""
    return {
        "query": request.get("query", ""),
        "limit": request.get("limit", 10),
        "offset": request.get("offset", 0),
        "category": request.get("category"),
        "tags": request.get("tags"),
        "tags_match_any": request.get("tags_match_any", False),
        "mode": request.get("mode", "hybrid"),
        "enable_reranking": request.get("enable_reranking", False),
        "min_score": request.get("min_score", 0.0),
        "enable_query_expansion": request.get("enable_query_expansion", False),
        "enable_relevance_scoring": request.get("enable_relevance_scoring", False),
        "enable_clustering": request.get("enable_clustering", False),
        "track_analytics": request.get("track_analytics", True),
        "created_after": request.get("created_after"),
        "created_before": request.get("created_before"),
        "exclude_terms": request.get("exclude_terms"),
        "require_terms": request.get("require_terms"),
        "exclude_sources": request.get("exclude_sources"),
        "verified_only": request.get("verified_only", False),
        "session_id": request.get("session_id"),
    }


async def _fallback_to_enhanced_search(kb_to_use, params: dict):
    """Fallback to regular enhanced_search when v2 not available (Issue #398: extracted)."""
    logger.warning("KB does not support enhanced_search_v2, using fallback")
    return await kb_to_use.enhanced_search(
        query=params["query"],
        limit=params["limit"],
        offset=params["offset"],
        category=params["category"],
        tags=params["tags"],
        tags_match_any=params["tags_match_any"],
        mode=params["mode"],
        enable_reranking=params["enable_reranking"],
        min_score=params["min_score"],
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_search_v2",
    error_code_prefix="KB",
)
@router.post("/enhanced_search_v2")
async def enhanced_search_v2(request: dict, req: Request):
    """
    Enhanced search v2 with Issue #78 improvements (Issue #398: refactored).

    Features: Query expansion, relevance scoring, filtering, clustering, analytics.
    See API documentation for full parameter list.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if kb_to_use is None:
        return {
            "success": False,
            "results": [],
            "total_count": 0,
            "message": "Knowledge base not initialized",
        }

    # Extract parameters using helper
    params = _extract_search_v2_params(request)
    query = params["query"]

    if not query:
        raise HTTPException(status_code=400, detail="Query is required")

    # Fallback if KB doesn't support enhanced_search_v2
    if not hasattr(kb_to_use, "enhanced_search_v2"):
        return await _fallback_to_enhanced_search(kb_to_use, params)

    logger.info(
        "Enhanced search v2: '%s' (expansion=%s, clustering=%s, relevance=%s)",
        query,
        params["enable_query_expansion"],
        params["enable_clustering"],
        params["enable_relevance_scoring"],
    )

    return await kb_to_use.enhanced_search_v2(**params)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_search_analytics",
    error_code_prefix="KB",
)
@router.get("/search_analytics")
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
        from src.knowledge.search_quality import get_search_analytics

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="record_search_click",
    error_code_prefix="KB",
)
@router.post("/record_click")
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
        from src.knowledge.search_quality import get_search_analytics

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="expand_query",
    error_code_prefix="KB",
)
@router.post("/expand_query")
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
        from src.knowledge.search_quality import get_query_expander

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


# ===== HELPER FUNCTIONS =====


async def _enhance_search_with_rag(
    query: str, results: List[Metadata]
) -> Metadata:
    """Enhance search results with RAG analysis"""
    try:
        rag_agent = get_rag_agent()

        # Convert results to documents for RAG processing
        documents = []
        for result in results:
            documents.append(
                {
                    "content": result.get("content", ""),
                    "metadata": {
                        "filename": result.get("metadata", {}).get("title", "Unknown"),
                        "source": (
                            result.get("metadata", {}).get("source", "knowledge_base")
                        ),
                        "score": result.get("score", 0.0),
                    },
                }
            )

        # Analyze document relevance
        document_analysis = rag_agent._analyze_document_relevance(query, documents)

        # Rank documents
        ranked_documents = await rag_agent.rank_documents(query, documents)

        return {
            "document_analysis": document_analysis,
            "ranked_documents": ranked_documents[:5],  # Top 5 ranked documents
            "analysis_summary": {
                "total_analyzed": len(documents),
                "high_relevance_count": document_analysis.get("high_relevance", 0),
                "medium_relevance_count": document_analysis.get("medium_relevance", 0),
                "low_relevance_count": document_analysis.get("low_relevance", 0),
            },
        }

    except Exception as e:
        logger.error(f"RAG enhancement error: {e}")
        return {
            "error": str(e),
            "analysis_summary": {
                "total_analyzed": len(results),
                "error": "RAG analysis failed",
            },
        }
