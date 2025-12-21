# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Knowledge Base API with AI Stack RAG Integration.

This module enhances the existing knowledge base with advanced AI capabilities
including RAG (Retrieval-Augmented Generation), knowledge extraction, and
intelligent content analysis using the AI Stack VM.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from backend.type_defs.common import Metadata

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.dependencies import get_knowledge_base
from backend.knowledge_factory import get_or_create_knowledge_base
from backend.services.ai_stack_client import AIStackError, get_ai_stack_client
from backend.utils.response_helpers import (
    create_error_response,
    create_success_response,
    handle_ai_stack_error,
)
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["knowledge-enhanced"])

# ====================================================================
# Request/Response Models
# ====================================================================


class EnhancedSearchRequest(BaseModel):
    """Enhanced search request with AI Stack integration."""

    query: str = Field(..., min_length=1, max_length=5000, description="Search query")
    search_type: str = Field(
        "comprehensive", description="Search type (precise, comprehensive, broad)"
    )
    max_results: int = Field(10, ge=1, le=50, description="Maximum results to return")
    include_rag: bool = Field(True, description="Include RAG-enhanced results")
    include_local: bool = Field(
        True, description="Include local knowledge base results"
    )
    confidence_threshold: float = Field(
        0.3, ge=0.0, le=1.0, description="Minimum confidence score"
    )


class KnowledgeExtractionRequest(BaseModel):
    """Request model for knowledge extraction."""

    content: str = Field(
        ..., min_length=1, description="Content to extract knowledge from"
    )
    title: Optional[str] = Field(None, description="Content title")
    source: Optional[str] = Field("api", description="Content source")
    category: Optional[str] = Field("general", description="Content category")
    content_type: str = Field("text", description="Content type (text, document, url)")
    extraction_mode: str = Field("comprehensive", description="Extraction mode")
    auto_store: bool = Field(
        True, description="Automatically store extracted knowledge"
    )


class DocumentAnalysisRequest(BaseModel):
    """Request model for document analysis."""

    documents: List[Metadata] = Field(..., description="Documents to analyze")
    analysis_type: str = Field("comprehensive", description="Analysis type")
    extract_entities: bool = Field(True, description="Extract entities")
    generate_summary: bool = Field(True, description="Generate summary")


class RAGQueryRequest(BaseModel):
    """Request model for RAG queries."""

    query: str = Field(..., min_length=1, max_length=5000, description="RAG query")
    documents: Optional[List[Metadata]] = Field(
        None, description="Specific documents to query"
    )
    context: Optional[str] = Field(None, description="Additional context")
    max_results: int = Field(10, ge=1, le=30, description="Maximum results")
    include_reasoning: bool = Field(False, description="Include reasoning steps")


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
            filtered_local = [
                result
                for result in local_results
                if result.get("score", 0) >= confidence_threshold
            ]

            logger.info(
                f"Local KB search: {len(local_results)} results, "
                f"{len(filtered_local)} above threshold"
            )

            return {
                "results": filtered_local,
                "total_found": len(local_results),
                "filtered_count": len(filtered_local),
                "source": "local_kb",
            }

        return {"results": [], "source": "local_kb", "error": "KB not available"}

    except Exception as e:
        logger.warning("Local knowledge base search failed: %s", e)
        return {"results": [], "error": str(e), "source": "local_kb"}


async def _search_rag_enhanced(
    query: str,
    max_results: int,
    local_docs: Optional[List[Dict[str, Any]]] = None,
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_search",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.post("/search/enhanced")
async def enhanced_search(
    request_data: EnhancedSearchRequest,
    req: Request,
    knowledge_base=Depends(get_knowledge_base),
):
    """
    Enhanced search combining local knowledge base with AI Stack RAG capabilities.

    Issue #281: Refactored from 144 lines to use extracted helper methods.

    This endpoint provides superior search results by combining:
    - Local knowledge base semantic search
    - AI Stack RAG-enhanced retrieval
    - Intelligent result ranking and synthesis
    """
    try:
        results = {}

        # Local knowledge base search (Issue #281: uses helper)
        if request_data.include_local and knowledge_base:
            results["local_knowledge_base"] = await _search_local_knowledge_base(
                req=req,
                query=request_data.query,
                max_results=request_data.max_results,
                confidence_threshold=request_data.confidence_threshold,
            )

        # AI Stack RAG search (Issue #281: uses helper)
        if request_data.include_rag:
            local_docs = results.get("local_knowledge_base", {}).get("results")
            results["rag_enhanced"] = await _search_rag_enhanced(
                query=request_data.query,
                max_results=request_data.max_results,
                local_docs=local_docs,
            )

        # Enhanced librarian search (Issue #281: uses helper)
        results["enhanced_librarian"] = await _search_enhanced_librarian(
            query=request_data.query,
            search_type=request_data.search_type,
            max_results=request_data.max_results,
        )

        # Combine and rank results (Issue #281: uses helper)
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
            message=f"Enhanced search failed: {str(e)}",
            status_code=500,
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rag_search",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.post("/search/rag")
async def rag_search(
    request_data: RAGQueryRequest, knowledge_base=Depends(get_knowledge_base)
):
    """
    Pure RAG search using AI Stack for document synthesis and generation.

    This endpoint uses the AI Stack's RAG agent for advanced document
    understanding and context-aware response generation.
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
                logger.info(
                    f"Retrieved {len(documents)} documents from local KB for RAG"
                )
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
    kb, fact: Dict[str, Any], semaphore: asyncio.Semaphore,
    title: Optional[str], source: Optional[str], category: Optional[str]
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
                    "extracted_at": datetime.utcnow().isoformat(),
                },
            )
        except Exception as e:
            logger.warning("Failed to store extracted fact: %s", e)
            return {"status": "error", "message": str(e)}


async def _store_extracted_facts(
    req: Request, extraction_result: dict, request_data: KnowledgeExtractionRequest
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
                kb_to_use, fact, semaphore,
                request_data.title, request_data.source, request_data.category
            )
            for fact in extracted_facts
        ],
        return_exceptions=True
    )

    # Filter successful results
    stored_facts = [
        result for result in results
        if isinstance(result, dict) and result.get("status") != "error"
    ]

    logger.info("Stored %s extracted facts in knowledge base", len(stored_facts))
    return stored_facts


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_knowledge",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.post("/extract")
async def extract_knowledge(request_data: KnowledgeExtractionRequest, req: Request):
    """
    Extract structured knowledge from content using AI Stack capabilities.

    This endpoint uses AI Stack's knowledge extraction agent to identify
    and structure knowledge from various content types.
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
                stored_facts = await _store_extracted_facts(
                    req, extraction_result, request_data
                )
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_documents",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.post("/analyze/documents")
async def analyze_documents(request_data: DocumentAnalysisRequest):
    """
    Analyze multiple documents using AI Stack capabilities.

    This endpoint provides comprehensive document analysis including
    entity extraction, summarization, and cross-document insights.
    """
    try:
        ai_client = await get_ai_stack_client()

        # Analyze documents using AI Stack
        analysis_result = await ai_client.analyze_documents(
            documents=request_data.documents
        )

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reformulate_query",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.post("/query/reformulate")
async def reformulate_query(query: str, context: Optional[str] = None):
    """
    Reformulate query for better search results using AI Stack.

    This endpoint uses AI Stack's RAG agent to suggest improved
    query formulations for better retrieval performance.
    """
    try:
        ai_client = await get_ai_stack_client()

        reformulation_result = await ai_client.reformulate_query(
            query=query, context=context
        )

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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_system_knowledge_insights",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.get("/system/insights")
async def get_system_knowledge_insights(knowledge_category: Optional[str] = None):
    """
    Get system-wide knowledge insights and analytics.

    This endpoint provides insights about the knowledge base
    using AI Stack's system knowledge manager.
    """
    try:
        ai_client = await get_ai_stack_client()

        insights = await ai_client.get_system_knowledge(
            knowledge_category=knowledge_category
        )

        return create_success_response(
            {"knowledge_category": knowledge_category, "system_insights": insights}
        )

    except AIStackError as e:
        await handle_ai_stack_error(e, "System knowledge insights")


# ====================================================================
# Enhanced Statistics and Health
# ====================================================================


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_enhanced_stats",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.get("/stats/enhanced")
async def get_enhanced_stats(req: Request):
    """
    Get enhanced knowledge base statistics including AI Stack metrics.
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
            local_stats = {"error": str(e)}

        # Get AI Stack system knowledge insights
        ai_stats = {}
        try:
            ai_client = await get_ai_stack_client()
            ai_insights = await ai_client.get_system_knowledge()
            ai_stats = ai_insights
        except Exception as e:
            logger.warning("Failed to get AI Stack stats: %s", e)
            ai_stats = {"error": str(e)}

        return create_success_response(
            {
                "local_knowledge_base": local_stats,
                "ai_stack_insights": ai_stats,
                "enhanced_capabilities": True,
                "timestamp": datetime.utcnow().isoformat(),
            }
        )

    except Exception as e:
        logger.error("Enhanced stats retrieval failed: %s", e)
        return create_error_response(
            error_code="STATS_ERROR",
            message=f"Failed to retrieve enhanced stats: {str(e)}",
            status_code=500,
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enhanced_knowledge_health",
    error_code_prefix="KNOWLEDGE_ENHANCED",
)
@router.get("/health/enhanced")
async def enhanced_knowledge_health():
    """
    Enhanced health check including AI Stack connectivity.
    """
    try:
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "components": {},
        }

        # Check AI Stack connectivity
        try:
            ai_client = await get_ai_stack_client()
            ai_health = await ai_client.health_check()
            health_status["components"]["ai_stack"] = ai_health["status"]
        except Exception as e:
            health_status["components"]["ai_stack"] = "unavailable"
            health_status["ai_stack_error"] = str(e)

        # Overall health assessment
        overall_healthy = health_status["components"]["ai_stack"] == "healthy"
        if not overall_healthy:
            health_status["status"] = "degraded"

        return JSONResponse(
            status_code=200 if overall_healthy else 503, content=health_status
        )

    except Exception as e:
        logger.error("Enhanced knowledge health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
