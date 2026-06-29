# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Enhanced Knowledge Base API with AI Stack RAG Integration.

This module enhances the existing knowledge base with advanced AI capabilities
including RAG (Retrieval-Augmented Generation), knowledge extraction, and
intelligent content analysis using the AI Stack VM.
"""

import asyncio
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_knowledge import (
    AIStackDocumentAnalysisData,
    AIStackEnhancedHealthData,
    AIStackEnhancedSearchData,
    AIStackSearchRequest,
    AIStackEnhancedStatsData,
    AIStackKnowledgeExtractData,
    AIStackKnowledgeExtractionRequest,
    AIStackQueryReformulateData,
    AIStackRAGQueryRequest,
    AIStackRagSearchData,
    AIStackSystemInsightsData,
    DocumentAnalysisRequest,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from dependencies import get_knowledge_base
from knowledge_factory import get_or_create_knowledge_base
from services.ai_stack_client import AIStackError, get_ai_stack_client
from utils.response_helpers import (
    create_error_response,
    create_success_response,
    handle_ai_stack_error,
)

logger = get_logger(__name__)

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["knowledge-enhanced"])

# ====================================================================
# Request/Response Models
# ====================================================================


# ====================================================================
# Utility Functions - Now imported from backend.utils.response_helpers
# (Issue #292: Duplicate code elimination)
# ====================================================================


# ====================================================================
# Enhanced Search Helpers (Issue #281)
# ====================================================================


async def _search_local_knowledge_base(
    req: Request,
    query: str,
    max_results: int,
    confidence_threshold: float,
) -> Dict[str, Any]:
    """
    Search local knowledge base with confidence filtering.

    Issue #281: Extracted helper for local KB search.

    Args:
        req: FastAPI request for app state access
        query: Search query string
        max_results: Maximum results to return
        confidence_threshold: Minimum confidence score

    Returns:
        Dictionary with search results and metadata
    """
    try:
        kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
        if kb_to_use:
            local_results = await kb_to_use.search(query=query, top_k=max_results)

            # Filter by confidence threshold
            filtered_local = [result for result in local_results if result.get("score", 0) >= confidence_threshold]

            logger.info(f"Local KB search: {len(local_results)} results, " f"{len(filtered_local)} above threshold")

            return {
                "results": filtered_local,
                "total_found": len(local_results),
                "filtered_count": len(filtered_local),
                "source": "local_kb",
            }

        return {"results": [], "source": "local_kb", "error": "KB not available"}

    except Exception as e:
        logger.warning("Local knowledge base search failed: %s", e)
        return {"results": [], "error": "Internal server error", "source": "local_kb"}


async def _search_rag_enhanced(
    query: str,
    max_results: int,
    local_docs: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    """
    Search using AI Stack RAG capabilities.

    Issue #281: Extracted helper for RAG search.

    Args:
        query: Search query string
        max_results: Maximum results to return
        local_docs: Optional local documents to enhance with

    Returns:
        Dictionary with RAG search results
    """
    try:
        ai_client = await get_ai_stack_client()
        rag_results = await ai_client.rag_query(
            query=query,
            documents=local_docs,
            max_results=max_results,
        )

        logger.info("RAG search completed successfully")
        return {"results": rag_results, "source": "ai_stack_rag"}

    except AIStackError as e:
        logger.warning("AI Stack RAG search failed: %s", e)
        return {"results": [], "error": e.message, "source": "ai_stack_rag"}


async def _search_enhanced_librarian(
    query: str,
    search_type: str,
    max_results: int,
) -> Dict[str, Any]:
    """
    Search using AI Stack enhanced librarian.

    Issue #281: Extracted helper for librarian search.

    Args:
        query: Search query string
        search_type: Type of search (precise, comprehensive, broad)
        max_results: Maximum results to return

    Returns:
        Dictionary with librarian search results
    """
    try:
        ai_client = await get_ai_stack_client()
        enhanced_results = await ai_client.search_knowledge_enhanced(
            query=query,
            search_type=search_type,
            max_results=max_results,
        )

        logger.info("Enhanced librarian search completed")
        return {"results": enhanced_results, "source": "ai_stack_librarian"}

    except AIStackError as e:
        logger.warning("Enhanced librarian search failed: %s", e)
        return {"results": [], "error": e.message, "source": "ai_stack_librarian"}


def _combine_search_results(
    results: Dict[str, Dict[str, Any]],
) -> tuple:
    """
    Combine and rank results from multiple sources.

    Issue #281: Extracted helper for result combination.

    Args:
        results: Dictionary of results from different sources

    Returns:
        Tuple of (combined_results, source_count)
    """
    combined_results = []
    source_count = 0

    for source_key, source_data in results.items():
        if source_data.get("results") and isinstance(source_data["results"], list):
            source_count += 1
            for result in source_data["results"]:
                result["source_type"] = source_data["source"]
                combined_results.append(result)

    # Sort combined results by relevance score
    combined_results.sort(key=lambda x: x.get("score", 0), reverse=True)

    return combined_results, source_count


# ====================================================================
# Enhanced Search Endpoints
# ====================================================================


async def _run_all_search_sources(
    request_data: "AIStackSearchRequest",
    req: Request,
    knowledge_base,
) -> Dict[str, Any]:
    """Helper for enhanced_search. Ref: #1088.

    Executes local KB, RAG, and librarian searches and returns a combined
    results dict keyed by source name.

    Args:
        request_data: Validated search request parameters
        req: FastAPI request for app state access
        knowledge_base: Injected knowledge base dependency

    Returns:
        Dict mapping source name to search result data
    """
    results: Dict[str, Any] = {}

    if request_data.include_local and knowledge_base:
        results["local_knowledge_base"] = await _search_local_knowledge_base(
            req=req,
            query=request_data.query,
            max_results=request_data.max_results,
            confidence_threshold=request_data.confidence_threshold,
        )

    if request_data.include_rag:
        local_docs = results.get("local_knowledge_base", {}).get("results")
        results["rag_enhanced"] = await _search_rag_enhanced(
            query=request_data.query,
            max_results=request_data.max_results,
            local_docs=local_docs,
        )

    results["enhanced_librarian"] = await _search_enhanced_librarian(
        query=request_data.query,
        search_type=request_data.search_type,
        max_results=request_data.max_results,
    )

    return results


@router.post("/search/enhanced", response_model=DataResponse[AIStackEnhancedSearchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="search",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def search(
    request_data: AIStackSearchRequest,
    req: Request,
    knowledge_base=Depends(get_knowledge_base),
    current_user: dict = Depends(get_current_user),
):
    """
    Enhanced search combining local knowledge base with AI Stack RAG capabilities.

    Issue #281: Refactored from 144 lines to use extracted helper methods.
    Issue #744: Requires authenticated user.

    This endpoint provides superior search results by combining:
    - Local knowledge base semantic search
    - AI Stack RAG-enhanced retrieval
    - Intelligent result ranking and synthesis
    """
    try:
        results = await _run_all_search_sources(request_data, req, knowledge_base)
        combined_results, source_count = _combine_search_results(results)

        return create_success_response(
            {
                "query": request_data.query,
                "search_type": request_data.search_type,
                "total_sources": source_count,
                "combined_results": combined_results[: request_data.max_results],
                "source_breakdown": results,
                "search_metadata": {
                    "confidence_threshold": request_data.confidence_threshold,
                    "max_results": request_data.max_results,
                    "sources_used": list(results.keys()),
                },
            }
        )

    except Exception as e:
        logger.error("Enhanced search failed: %s", e)
        return create_error_response(
            error_code="SEARCH_ERROR",
            message="Enhanced search failed",
            status_code=500,
        )


@router.post("/search/rag", response_model=DataResponse[AIStackRagSearchData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_search",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def rag_search(
    request_data: AIStackRAGQueryRequest,
    knowledge_base=Depends(get_knowledge_base),
    current_user: dict = Depends(get_current_user),
):
    """
    Pure RAG search using AI Stack for document synthesis and generation.

    This endpoint uses the AI Stack's RAG agent for advanced document
    understanding and context-aware response generation.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        # If no specific documents provided, search local knowledge base first
        documents = request_data.documents
        if not documents and knowledge_base:
            try:
                kb_results = await knowledge_base.search(
                    query=request_data.query,
                    top_k=15,  # Get more documents for RAG context
                )
                documents = kb_results if isinstance(kb_results, list) else []
                logger.info(f"Retrieved {len(documents)} documents from local KB for RAG")
            except Exception as e:
                logger.warning("Local KB document retrieval failed: %s", e)
                documents = []

        # Perform RAG query
        rag_result = await ai_client.rag_query(
            query=request_data.query,
            documents=documents,
            context=request_data.context,
            max_results=request_data.max_results,
        )

        return create_success_response(
            {
                "query": request_data.query,
                "rag_response": rag_result,
                "documents_used": len(documents) if documents else 0,
                "include_reasoning": request_data.include_reasoning,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "RAG search")


# ====================================================================
# Knowledge Extraction and Analysis Endpoints
# ====================================================================


async def _store_single_fact_with_semaphore(
    kb,
    fact: Dict[str, Any],
    semaphore: asyncio.Semaphore,
    title: str | None,
    source: str | None,
    category: str | None,
) -> Dict[str, Any]:
    """Store a single fact with semaphore-bounded concurrency."""
    async with semaphore:
        try:
            return await kb.store_fact(
                content=fact.get("content", ""),
                metadata={
                    "title": title or fact.get("title", "Extracted Knowledge"),
                    "source": source,
                    "category": category,
                    "extraction_confidence": fact.get("confidence", 0.5),
                    "extracted_at": utc_timestamp(),
                },
            )
        except Exception as e:
            logger.warning("Failed to store extracted fact: %s", e)
            return {"status": "error", "message": "Operation failed"}


async def _store_extracted_facts(
    req: Request, extraction_result: dict, request_data: AIStackKnowledgeExtractionRequest
) -> List[Dict[str, Any]]:
    """Store extracted facts in knowledge base with parallel processing."""
    kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)

    if not kb_to_use:
        return []

    extracted_facts = extraction_result.get("extracted_facts")
    if not extracted_facts:
        return []

    # Use asyncio.gather for parallel fact storage with bounded concurrency
    semaphore = asyncio.Semaphore(50)

    # Store all facts in parallel
    results = await asyncio.gather(
        *[
            _store_single_fact_with_semaphore(
                kb_to_use,
                fact,
                semaphore,
                request_data.title,
                request_data.source,
                request_data.category,
            )
            for fact in extracted_facts
        ],
        return_exceptions=True,
    )

    # Filter successful results
    stored_facts = [result for result in results if isinstance(result, dict) and result.get("status") != "error"]

    logger.info("Stored %s extracted facts in knowledge base", len(stored_facts))
    return stored_facts


@router.post("/extract", response_model=DataResponse[AIStackKnowledgeExtractData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_knowledge",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def extract_knowledge(
    request_data: AIStackKnowledgeExtractionRequest,
    req: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Extract structured knowledge from content using AI Stack capabilities.

    This endpoint uses AI Stack's knowledge extraction agent to identify
    and structure knowledge from various content types.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Extract knowledge using AI Stack
        extraction_result = await ai_client.extract_knowledge(
            content=request_data.content,
            content_type=request_data.content_type,
            extraction_mode=request_data.extraction_mode,
        )

        # Optionally store extracted knowledge in local knowledge base
        stored_facts = []
        if request_data.auto_store:
            try:
                stored_facts = await _store_extracted_facts(req, extraction_result, request_data)
            except Exception as e:
                logger.warning("Auto-storage of extracted knowledge failed: %s", e)

        return create_success_response(
            {
                "extraction_result": extraction_result,
                "auto_stored": request_data.auto_store,
                "stored_facts_count": len(stored_facts),
                "stored_facts": stored_facts if stored_facts else None,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Knowledge extraction")


@router.post("/analyze/documents", response_model=DataResponse[AIStackDocumentAnalysisData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_documents",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def analyze_documents(
    request_data: DocumentAnalysisRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Analyze multiple documents using AI Stack capabilities.

    This endpoint provides comprehensive document analysis including
    entity extraction, summarization, and cross-document insights.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Analyze documents using AI Stack
        analysis_result = await ai_client.analyze_documents(documents=request_data.documents)

        return create_success_response(
            {
                "documents_analyzed": len(request_data.documents),
                "analysis_type": request_data.analysis_type,
                "analysis_result": analysis_result,
                "extract_entities": request_data.extract_entities,
                "generate_summary": request_data.generate_summary,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Document analysis")


# ====================================================================
# Query Enhancement Endpoints
# ====================================================================


@router.post("/query/reformulate", response_model=DataResponse[AIStackQueryReformulateData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reformulate_query",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def reformulate_query(
    query: str,
    context: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Reformulate query for better search results using AI Stack.

    This endpoint uses AI Stack's RAG agent to suggest improved
    query formulations for better retrieval performance.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        reformulation_result = await ai_client.reformulate_query(query=query, context=context)

        return create_success_response(
            {
                "original_query": query,
                "reformulated_queries": reformulation_result,
                "context_provided": context is not None,
            }
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "Query reformulation")


# ====================================================================
# System Knowledge Management
# ====================================================================


@router.get("/system/insights", response_model=DataResponse[AIStackSystemInsightsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_knowledge_insights",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def get_system_knowledge_insights(
    knowledge_category: str | None = None,
    current_user: dict = Depends(get_current_user),
):
    """
    Get system-wide knowledge insights and analytics.

    This endpoint provides insights about the knowledge base
    using AI Stack's system knowledge manager.

    Issue #744: Requires authenticated user.
    """
    try:
        ai_client = await get_ai_stack_client()

        insights = await ai_client.get_system_knowledge(knowledge_category=knowledge_category)

        return create_success_response({"knowledge_category": knowledge_category, "system_insights": insights})

    except AIStackError as e:
        await handle_ai_stack_error(e, "System knowledge insights")


# ====================================================================
# Enhanced Statistics and Health
# ====================================================================


@router.get("/stats/enhanced", response_model=DataResponse[AIStackEnhancedStatsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_enhanced_stats",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def get_enhanced_stats(
    req: Request,
    current_user: dict = Depends(get_current_user),
):
    """
    Get enhanced knowledge base statistics including AI Stack metrics.

    Issue #744: Requires authenticated user.
    """
    try:
        # Get local KB stats
        local_stats = {}
        try:
            kb_to_use = await get_or_create_knowledge_base(req.app, force_refresh=False)
            if kb_to_use:
                local_stats = await kb_to_use.get_stats()
        except Exception as e:
            logger.warning("Failed to get local KB stats: %s", e)
            local_stats = {"error": "Internal server error"}

        # Get AI Stack system knowledge insights
        ai_stats = {}
        try:
            ai_client = await get_ai_stack_client()
            ai_insights = await ai_client.get_system_knowledge()
            ai_stats = ai_insights
        except Exception as e:
            logger.warning("Failed to get AI Stack stats: %s", e)
            ai_stats = {"error": "Internal server error"}

        return create_success_response(
            {
                "local_knowledge_base": local_stats,
                "ai_stack_insights": ai_stats,
                "enhanced_capabilities": True,
                "timestamp": utc_timestamp(),
            }
        )

    except Exception as e:
        logger.error("Enhanced stats retrieval failed: %s", e)
        return create_error_response(
            error_code="STATS_ERROR",
            message="Failed to retrieve enhanced stats",
            status_code=500,
        )


@router.get("/health/enhanced", response_model=DataResponse[AIStackEnhancedHealthData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="knowledge_health",
    error_code_prefix="KNOWLEDGE_AI_STACK",
)
async def knowledge_health(
    current_user: dict = Depends(get_current_user),
):
    """
    Enhanced health check including AI Stack connectivity.

    Issue #744: Requires authenticated user.
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": utc_timestamp(),
            "components": {},
        }

        # Check AI Stack connectivity
        try:
            ai_client = await get_ai_stack_client()
            ai_health = await ai_client.health_check()
            health_status["components"]["ai_stack"] = ai_health["status"]
        except Exception:
            health_status["components"]["ai_stack"] = "unavailable"
            health_status["ai_stack_error"] = "unavailable"

        # Overall health assessment
        overall_healthy = health_status["components"]["ai_stack"] == "healthy"
        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(status_code=200 if overall_healthy else 503, content=health_status)

    except Exception as e:
        logger.error("Enhanced knowledge health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": "Internal server error",
                "timestamp": utc_timestamp(),
            },
        )
