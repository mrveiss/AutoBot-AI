# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Search API - Search and RAG-enhanced query endpoints.

This module contains all search-related API endpoints for the knowledge base.
Extracted from knowledge.py for better maintainability (Issue #185, #209).

Endpoints:
- POST /search - Single canonical search endpoint with all features (#555, #10666)

Migration guide (deprecated routes removed in #10666):
- /enhanced_search  → /search with tags/mode/enable_reranking params
- /rag_search       → /search with enable_rag=true (+ reformulate_query=true)
- /similarity_search → /search with mode=semantic, min_score=<threshold>
- /enhanced_search_v2 → /search with enable_query_expansion/enable_clustering etc.

Related Issues: #78 (Search Quality), #185 (Split), #209 (Knowledge split),
                #555 (Consolidation), #10666 (Deprecated duplicate removal)
"""

import logging
from typing import List

from fastapi import APIRouter, Request

from api.schemas_knowledge import SearchRequest
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from knowledge.schemas import (
    ExpandQueryResponse,
    KnowledgeSearchResponse,
    RecordClickResponse,
    SearchAnalyticsResponse,
)
from knowledge.vector_search_engine import SearchResult as _EngineResult
from knowledge.vector_search_engine import get_vector_search_engine
from knowledge_factory import get_or_create_knowledge_base
from type_defs.common import Metadata

# Import RAG Agent for enhanced search capabilities
try:
    from agents.rag_agent import get_rag_agent

    RAG_AVAILABLE = True
except ImportError:
    RAG_AVAILABLE = False
    logging.warning("RAG Agent not available - enhanced search features disabled")

# Import Advanced RAG Service for reranking
try:
    from services.rag_service import RAGService

    ADVANCED_RAG_AVAILABLE = True
except ImportError:
    ADVANCED_RAG_AVAILABLE = False
    logging.warning("Advanced RAG Service not available - reranking features disabled")

logger = get_logger(__name__)

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
    """Execute search on knowledge base via VectorSearchEngine (Issue #3828).

    Routes through the canonical VectorSearchEngine for unified hardware
    dispatch (NPU > GPU > CPU).  Falls back to the per-implementation KB
    search methods only when the engine raises.

    Issue #398: original KB-dispatch logic preserved as fallback.
    """
    try:
        engine = await get_vector_search_engine()
        engine_results: list[_EngineResult] = await engine.search(
            query=query,
            top_k=search_limit,
            hardware_backend="auto",
        )
        return [
            {
                "content": r.text,
                "score": r.score,
                "metadata": r.metadata,
                "node_id": r.source,
                "doc_id": r.source,
            }
            for r in engine_results
        ]
    except Exception as exc:
        logger.warning(
            "_execute_kb_search: VectorSearchEngine failed (%s), falling back to direct KB",
            exc,
        )

    # Legacy per-implementation fallback
    kb_class_name = kb_to_use.__class__.__name__
    if kb_class_name == "KnowledgeBaseV2":
        return await kb_to_use.search(query=query, top_k=search_limit)
    return await kb_to_use.search(query=query, similarity_top_k=search_limit, mode=mode)


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
        logger.error("Advanced reranking failed: %s, returning original results", e)
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
        logger.error("RAG enhancement failed: %s", e)
        return None


# =============================================================================
# Helper Functions for rag_enhanced_search (Issue #281)
# =============================================================================


def _build_no_results_response(query: str, reformulated_queries: List[str]) -> Metadata:
    """
    Build response when no results are found.

    Issue #665: Extracted from rag_enhanced_search to reduce function length.

    Args:
        query: Original search query
        reformulated_queries: List of reformulated queries used

    Returns:
        Response dictionary for empty results
    """
    return {
        "status": "success",
        "synthesized_response": f"No relevant documents found for query: '{query}'",
        "results": [],
        "total_results": 0,
        "original_query": query,
        "reformulated_queries": (reformulated_queries[1:] if len(reformulated_queries) > 1 else []),
        "rag_enhanced": True,
    }


def _build_kb_not_initialized_response() -> Metadata:
    """
    Build response when KB is not initialized.

    Issue #665: Extracted from rag_enhanced_search to reduce function length.

    Returns:
        Response dictionary for uninitialized KB
    """
    return {
        "status": "error",
        "synthesized_response": "",
        "results": [],
        "message": "Knowledge base not initialized - please check logs for errors",
    }


async def _check_empty_kb_for_rag(kb_to_use, query: str) -> Metadata | None:
    """Check if KB is empty and return early response if so (Issue #281: extracted)."""
    try:
        stats = await kb_to_use.get_stats()
        fact_count = stats.get("total_facts", 0)

        if fact_count == 0:
            logger.info("Knowledge base is empty - " "returning empty RAG results immediately")
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
        logger.warning("Could not check KB stats: %s", stats_err)

    return None


async def _reformulate_query_if_requested(query: str, reformulate_query: bool) -> List[str]:
    """Reformulate query using RAG agent if requested (Issue #281: extracted)."""
    reformulated_queries = [query]

    if reformulate_query:
        try:
            rag_agent = get_rag_agent()
            reformulation_result = await rag_agent.reformulate_query(query)

            if reformulation_result.get("status") == "success":
                additional_queries = reformulation_result.get("reformulated_queries", [])
                reformulated_queries.extend(additional_queries[:3])  # Limit to avoid too many queries

        except Exception as e:
            logger.warning("Query reformulation failed: %s", e)

    return reformulated_queries


async def _search_with_all_queries(kb_to_use, reformulated_queries: List[str], search_limit: int) -> List[Metadata]:
    """Search with all reformulated queries and deduplicate (Issue #281: extracted)."""
    all_results = []
    seen_content = set()

    for search_query in reformulated_queries:
        try:
            kb_class_name = kb_to_use.__class__.__name__

            if kb_class_name == "KnowledgeBaseV2":
                query_results = await kb_to_use.search(query=search_query, top_k=search_limit)
            else:
                query_results = await kb_to_use.search(query=search_query, similarity_top_k=search_limit)

            # Deduplicate results
            for result in query_results:
                content = result.get("content", "")
                if content and content not in seen_content:
                    seen_content.add(content)
                    result["source_query"] = search_query
                    all_results.append(result)

        except Exception as e:
            logger.error("Search failed for query '%s': %s", search_query, e)

    return all_results[:search_limit]


def _convert_results_to_documents(results: List[Metadata], original_query: str) -> List[Metadata]:
    """Convert search results to RAG-compatible document format (Issue #281: extracted)."""
    documents = []
    for result in results:
        documents.append(
            {
                "content": result.get("content", ""),
                "metadata": {
                    "filename": (result.get("metadata", {}).get("title", "Unknown")),
                    "source": (result.get("metadata", {}).get("source", "knowledge_base")),
                    "category": (result.get("metadata", {}).get("category", "general")),
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
            "reformulated_queries": (reformulated_queries[1:] if len(reformulated_queries) > 1 else []),
            "kb_implementation": kb_to_use.__class__.__name__,
            "agent_metadata": rag_result.get("metadata", {}),
            "rag_enhanced": True,
        }

    except Exception as e:
        logger.error("RAG processing failed: %s", e)
        return {
            "status": "partial_success",
            "synthesized_response": (f"Found {len(all_results)} relevant documents" " but synthesis failed"),
            "results": all_results,
            "total_results": len(all_results),
            "original_query": original_query,
            "reformulated_queries": (reformulated_queries[1:] if len(reformulated_queries) > 1 else []),
            "error": "Internal server error",
            "rag_enhanced": False,
        }


# =============================================================================
# Helper Functions for consolidated_search (Issue #665)
# =============================================================================


async def _check_kb_initialization(req: Request) -> tuple:
    """
    Check KB initialization and return (kb_instance, error_response).

    Issue #665: Extracted from consolidated_search to reduce function length.

    Args:
        req: FastAPI request object

    Returns:
        Tuple of (kb_instance, error_response). If kb_instance is None,
        error_response contains the error dict to return.
    """
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
    if kb_to_use is None:
        return None, {
            "results": [],
            "total_results": 0,
            "message": "Knowledge base not initialized - please check logs for errors",
        }
    return kb_to_use, None


async def _check_empty_kb_for_search(kb_to_use, query: str, mode: str) -> dict | None:
    """
    Check if KB is empty and return early response if so.

    Issue #665: Extracted from consolidated_search to reduce function length.

    Args:
        kb_to_use: Knowledge base instance
        query: Search query
        mode: Search mode

    Returns:
        Response dict if KB is empty, None otherwise
    """
    try:
        stats = await kb_to_use.get_stats()
        if stats.get("total_facts", 0) == 0:
            logger.info("Knowledge base is empty - returning empty results immediately")
            return _build_search_response(
                results=[],
                query=query,
                mode=mode,
                kb_implementation=kb_to_use.__class__.__name__,
                message="Knowledge base is empty - no documents to search. " "Add documents in the Manage tab.",
            )
    except Exception as stats_err:
        logger.warning("Could not check KB stats: %s", stats_err)

    return None


async def _execute_basic_search_with_reranking(request: SearchRequest, kb_to_use, query: str) -> dict:
    """
    Execute basic search with optional reranking.

    Issue #665: Extracted from consolidated_search to reduce function length.

    Args:
        request: Search request parameters
        kb_to_use: Knowledge base instance
        query: Search query

    Returns:
        Response dict with search results
    """
    kb_class_name = kb_to_use.__class__.__name__

    # Execute basic search
    results = await _execute_kb_search(kb_to_use, query, request.limit, request.mode)

    # Apply reranking if requested
    if request.enable_reranking:
        response = await _apply_reranking(query, results, kb_to_use)
        if response:
            return response

    return _build_search_response(
        results=results,
        query=query,
        mode=request.mode,
        kb_implementation=kb_class_name,
    )


# ===== SEARCH ENDPOINTS =====


@router.post("/search", response_model=KnowledgeSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="consolidated_search",
    error_code_prefix="KNOWLEDGE_SEARCH",
)
async def search(request: SearchRequest, req: Request):
    """
    Canonical knowledge base search endpoint (#555, #10666).

    Single entry point combining all search capabilities:
    - Basic search (query, limit/top_k)
    - Enhanced search (tags, hybrid mode, reranking)
    - RAG search (query reformulation, synthesis)
    - Advanced filtering (date filters, term filters, clustering)
    - Analytics tracking

    **Parameters:**
    - **query** (required): Search query string
    - **limit** / **top_k**: Maximum results (default: 10, max: 100)
    - **category**: Filter by category
    - **mode**: Search mode — 'semantic', 'keyword', 'hybrid' (default), 'auto'
    - **enable_rag**: Enable RAG enhancement for synthesized responses
    - **enable_reranking**: Enable cross-encoder reranking
    - **reformulate_query**: Expand query for better coverage
    - **return_context**: Return optimized context for chat integration
    - **tags** / **tags_match_any**: Tag filtering
    - **min_score**: Minimum score threshold (0.0-1.0)
    - **offset**: Pagination offset
    - **include_documentation**: Also search project documentation
    - **include_relations**: Include related facts
    - **enable_query_expansion**: Synonym/related-term expansion
    - **enable_relevance_scoring**: Additional relevance scoring
    - **enable_clustering**: Cluster results by topic
    - **exclude_sources**: Exclude results from these source IDs
    - **verified_only**: Return only verified/approved facts
    - **created_after** / **created_before**: Date range filters (YYYY-MM-DD)
    - **exclude_terms** / **require_terms**: Term inclusion/exclusion
    - **session_id** / **track_analytics**: Analytics correlation

    **Returns:** results, total_results, query, mode, rag_enhanced,
    reranking_applied, synthesized_response (if enable_rag=true).

    Migration (#10666): /enhanced_search→tags/reranking params,
    /rag_search→enable_rag=true, /similarity_search→mode=semantic+min_score,
    /enhanced_search_v2→enable_query_expansion/enable_clustering etc.
    """
    # Check KB initialization (Issue #665: uses helper)
    kb_to_use, error_response = await _check_kb_initialization(req)
    if kb_to_use is None:
        return error_response

    query = request.query
    logger.info("Search: %s", request.get_log_summary())

    # Check if KB is empty (Issue #665: uses helper)
    empty_response = await _check_empty_kb_for_search(kb_to_use, query, request.mode)
    if empty_response:
        return empty_response

    # Path 1: Full RAG search with synthesis
    if request.enable_rag and RAG_AVAILABLE:
        return await _consolidated_rag_search(request, kb_to_use)

    # Path 2: Enhanced search with tags/filtering/advanced options
    has_enhanced = hasattr(kb_to_use, "enhanced_search")
    if request.tags or request.min_score > 0 or has_enhanced or request.uses_advanced_features():
        return await _consolidated_enhanced_search(request, kb_to_use)

    # Path 3: Basic search (Issue #665: uses helper)
    return await _execute_basic_search_with_reranking(request, kb_to_use, query)


async def _consolidated_enhanced_search(request: SearchRequest, kb_to_use) -> dict:
    """
    Handle enhanced search path for consolidated endpoint (#555, #10666).

    Dispatches to enhanced_search_v2 when advanced params are set (folded from
    former /enhanced_search_v2 route — #10666).  Falls back to enhanced_search
    or basic search + filtering when those KB methods are unavailable.
    """
    kb_class_name = kb_to_use.__class__.__name__

    # Dispatch to enhanced_search_v2 when advanced features are requested (#10666)
    if request.uses_advanced_features() and hasattr(kb_to_use, "enhanced_search_v2"):
        return await kb_to_use.enhanced_search_v2(**request.to_advanced_params())

    # Use enhanced_search if available
    if hasattr(kb_to_use, "enhanced_search"):
        result = await kb_to_use.enhanced_search(**request.to_legacy_params())
        return result

    # Fallback: basic search with post-filtering
    results = await _execute_kb_search(kb_to_use, request.query, request.limit, request.mode)

    # Apply min_score filter
    if request.min_score > 0:
        results = [r for r in results if r.get("score", 0) >= request.min_score]

    # Apply reranking if requested
    if request.enable_reranking:
        response = await _apply_reranking(request.query, results, kb_to_use)
        if response:
            return response

    return _build_search_response(
        results=results,
        query=request.query,
        mode=request.mode,
        kb_implementation=kb_class_name,
    )


async def _consolidated_rag_search(request: SearchRequest, kb_to_use) -> dict:
    """
    Handle RAG-enhanced search path for consolidated endpoint (Issue #555).

    Performs query reformulation (if enabled), multi-query search, and RAG synthesis.
    """
    query = request.query
    kb_class_name = kb_to_use.__class__.__name__

    # Check if KB is empty first
    empty_response = await _check_empty_kb_for_rag(kb_to_use, query)
    if empty_response:
        return empty_response

    # Query reformulation if requested
    reformulated_queries = await _reformulate_query_if_requested(query, request.reformulate_query)

    # Search with all queries
    all_results = await _search_with_all_queries(kb_to_use, reformulated_queries, request.limit)

    # Apply min_score filter
    if request.min_score > 0:
        all_results = [r for r in all_results if r.get("score", 0) >= request.min_score]

    # RAG processing for synthesis
    if all_results:
        return await _process_with_rag_agent(query, all_results, reformulated_queries, kb_to_use)
    else:
        return {
            "status": "success",
            "synthesized_response": f"No relevant documents found for query: '{query}'",
            "results": [],
            "total_results": 0,
            "original_query": query,
            "reformulated_queries": (reformulated_queries[1:] if len(reformulated_queries) > 1 else []),
            "rag_enhanced": True,
            "kb_implementation": kb_class_name,
        }


# =============================================================================
# Issue #78: Analytics Endpoints
# =============================================================================


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
    from fastapi import HTTPException

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
    from fastapi import HTTPException

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


# ===== HELPER FUNCTIONS =====


async def _enhance_search_with_rag(query: str, results: List[Metadata]) -> Metadata:
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
                        "source": (result.get("metadata", {}).get("source", "knowledge_base")),
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
        logger.error("RAG enhancement error: %s", e)
        return {
            "error": "Internal server error",
            "analysis_summary": {
                "total_analyzed": len(results),
                "error": "RAG analysis failed",
            },
        }
