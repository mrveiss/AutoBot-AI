# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Knowledge Base API with AI Stack RAG Integration.

This module enhances the existing knowledge base with advanced AI capabilities
including RAG (Retrieval-Augmented Generation), knowledge extraction, and
intelligent content analysis using the AI Stack VM.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from backend.dependencies import get_knowledge_base
from backend.knowledge_factory import get_or_create_knowledge_base
from backend.services.ai_stack_client import AIStackError, get_ai_stack_client
from src.constants.network_constants import NetworkConstants
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

    documents: List[Dict[str, Any]] = Field(..., description="Documents to analyze")
    analysis_type: str = Field("comprehensive", description="Analysis type")
    extract_entities: bool = Field(True, description="Extract entities")
    generate_summary: bool = Field(True, description="Generate summary")


class RAGQueryRequest(BaseModel):
    """Request model for RAG queries."""

    query: str = Field(..., min_length=1, max_length=5000, description="RAG query")
    documents: Optional[List[Dict[str, Any]]] = Field(
        None, description="Specific documents to query"
    )
    context: Optional[str] = Field(None, description="Additional context")
    max_results: int = Field(10, ge=1, le=30, description="Maximum results")
    include_reasoning: bool = Field(False, description="Include reasoning steps")


# ====================================================================
# Utility Functions
# ====================================================================


def create_success_response(
    data: Any, message: str = "Operation completed successfully"
) -> Dict[str, Any]:
    """Create standardized success response."""
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }


def create_error_response(
    error_code: str = "INTERNAL_ERROR",
    message: str = "An error occurred",
    status_code: int = 500,
) -> JSONResponse:
    """Create standardized error response."""
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
            },
        },
    )


async def handle_ai_stack_error(error: AIStackError, context: str):
    """Handle AI Stack errors gracefully."""
    logger.error(f"{context} failed: {error.message}")
    status_code = (
        503 if error.status_code is None else (400 if error.status_code < 500 else 503)
    )

    raise HTTPException(
        status_code=status_code,
        detail={
            "error": error.message,
            "context": context,
            "ai_stack_details": error.details,
        },
    )


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

    This endpoint provides superior search results by combining:
    - Local knowledge base semantic search
    - AI Stack RAG-enhanced retrieval
    - Intelligent result ranking and synthesis
    """
    try:
        results = {}

        # Local knowledge base search
        if request_data.include_local and knowledge_base:
            try:
                kb_to_use = await get_or_create_knowledge_base(
                    req.app, force_refresh=False
                )
                if kb_to_use:
                    local_results = await kb_to_use.search(
                        query=request_data.query, top_k=request_data.max_results
                    )

                    # Filter by confidence threshold
                    filtered_local = [
                        result
                        for result in local_results
                        if result.get("score", 0) >= request_data.confidence_threshold
                    ]

                    results["local_knowledge_base"] = {
                        "results": filtered_local,
                        "total_found": len(local_results),
                        "filtered_count": len(filtered_local),
                        "source": "local_kb",
                    }

                    logger.info(
                        f"Local KB search: {len(local_results)} results, {len(filtered_local)} above threshold"
                    )

            except Exception as e:
                logger.warning(f"Local knowledge base search failed: {e}")
                results["local_knowledge_base"] = {
                    "results": [],
                    "error": str(e),
                    "source": "local_kb",
                }

        # AI Stack enhanced search
        if request_data.include_rag:
            try:
                ai_client = await get_ai_stack_client()

                # Use documents from local search if available
                local_docs = None
                if results.get("local_knowledge_base", {}).get("results"):
                    local_docs = results["local_knowledge_base"]["results"]

                rag_results = await ai_client.rag_query(
                    query=request_data.query,
                    documents=local_docs,
                    max_results=request_data.max_results,
                )

                results["rag_enhanced"] = {
                    "results": rag_results,
                    "source": "ai_stack_rag",
                }

                logger.info(f"RAG search completed successfully")

            except AIStackError as e:
                logger.warning(f"AI Stack RAG search failed: {e}")
                results["rag_enhanced"] = {
                    "results": [],
                    "error": e.message,
                    "source": "ai_stack_rag",
                }

        # Enhanced search through AI Stack librarian
        try:
            ai_client = await get_ai_stack_client()
            enhanced_results = await ai_client.search_knowledge_enhanced(
                query=request_data.query,
                search_type=request_data.search_type,
                max_results=request_data.max_results,
            )

            results["enhanced_librarian"] = {
                "results": enhanced_results,
                "source": "ai_stack_librarian",
            }

            logger.info(f"Enhanced librarian search completed")

        except AIStackError as e:
            logger.warning(f"Enhanced librarian search failed: {e}")
            results["enhanced_librarian"] = {
                "results": [],
                "error": e.message,
                "source": "ai_stack_librarian",
            }

        # Combine and rank results if multiple sources available
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
        logger.error(f"Enhanced search failed: {e}")
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
                logger.warning(f"Local KB document retrieval failed: {e}")
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
                kb_to_use = await get_or_create_knowledge_base(
                    req.app, force_refresh=False
                )
                if kb_to_use and extraction_result.get("extracted_facts"):
                    for fact in extraction_result["extracted_facts"]:
                        try:
                            store_result = await kb_to_use.store_fact(
                                content=fact.get("content", ""),
                                metadata={
                                    "title": (
                                        request_data.title
                                        or fact.get("title", "Extracted Knowledge")
                                    ),
                                    "source": request_data.source,
                                    "category": request_data.category,
                                    "extraction_confidence": fact.get(
                                        "confidence", 0.5
                                    ),
                                    "extracted_at": datetime.utcnow().isoformat(),
                                },
                            )
                            stored_facts.append(store_result)
                        except Exception as e:
                            logger.warning(f"Failed to store extracted fact: {e}")

                    logger.info(
                        f"Stored {len(stored_facts)} extracted facts in knowledge base"
                    )

            except Exception as e:
                logger.warning(f"Auto-storage of extracted knowledge failed: {e}")

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
            logger.warning(f"Failed to get local KB stats: {e}")
            local_stats = {"error": str(e)}

        # Get AI Stack system knowledge insights
        ai_stats = {}
        try:
            ai_client = await get_ai_stack_client()
            ai_insights = await ai_client.get_system_knowledge()
            ai_stats = ai_insights
        except Exception as e:
            logger.warning(f"Failed to get AI Stack stats: {e}")
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
        logger.error(f"Enhanced stats retrieval failed: {e}")
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
        logger.error(f"Enhanced knowledge health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
