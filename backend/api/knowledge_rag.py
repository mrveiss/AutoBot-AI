#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Advanced RAG endpoints for knowledge base - Reranking and optimized search.

These endpoints provide enhanced search capabilities using the AdvancedRAGOptimizer
with cross-encoder reranking for improved relevance scoring.
"""

import logging
from typing import List

from backend.type_defs.common import Metadata

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from backend.knowledge_factory import get_or_create_knowledge_base
from backend.services.rag_config import get_rag_config, update_rag_config
from backend.services.rag_service import RAGService
from src.constants.threshold_constants import QueryDefaults
from src.utils.error_boundaries import ErrorCategory, with_error_handling

logger = logging.getLogger(__name__)

router = APIRouter()


# ===== PYDANTIC MODELS =====


class AdvancedSearchRequest(BaseModel):
    """Request model for advanced RAG search with reranking"""

    query: str = Field(..., min_length=1, max_length=1000, description="Search query")
    max_results: int = Field(default=QueryDefaults.RAG_DEFAULT_RESULTS, ge=1, le=50, description="Maximum results")
    enable_reranking: bool = Field(
        default=True, description="Enable cross-encoder reranking"
    )
    return_context: bool = Field(
        default=False, description="Return optimized context for RAG"
    )
    timeout: float = Field(default=None, description="Optional timeout in seconds")


class RerankRequest(BaseModel):
    """Request model for reranking existing search results"""

    query: str = Field(
        ..., min_length=1, max_length=1000, description="Original search query"
    )
    results: List[Metadata] = Field(..., description="Search results to rerank")


class RAGConfigUpdate(BaseModel):
    """Request model for updating RAG configuration"""

    hybrid_weight_semantic: float = Field(default=None, ge=0.0, le=1.0)
    hybrid_weight_keyword: float = Field(default=None, ge=0.0, le=1.0)
    enable_reranking: bool = Field(default=None)
    diversity_threshold: float = Field(default=None, ge=0.0, le=1.0)
    max_results_per_stage: int = Field(default=None, ge=1, le=100)


# ===== DEPENDENCY INJECTION =====


async def get_rag_service_dependency(request: Request) -> RAGService:
    """
    Dependency function to get RAGService instance.

    Args:
        request: FastAPI request object

    Returns:
        RAGService instance initialized with knowledge base
    """
    kb = await get_or_create_knowledge_base(request.app, force_refresh=False)

    if kb is None:
        raise HTTPException(status_code=503, detail="Knowledge base not available")

    # Create RAG service (it will initialize itself)
    rag_service = RAGService(kb)
    await rag_service.initialize()

    return rag_service


# ===== ENDPOINTS =====


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="advanced_rag_search",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/advanced_search")
async def advanced_search(
    request: AdvancedSearchRequest,
    rag_service: RAGService = Depends(get_rag_service_dependency),
):
    """
    Perform advanced RAG search with cross-encoder reranking.

    This endpoint provides state-of-the-art retrieval using:
    - Hybrid search (semantic + keyword)
    - Query expansion
    - Result diversification
    - Cross-encoder reranking for improved relevance

    **Parameters:**
    - **query**: Search query string
    - **max_results**: Number of results to return (1-50)
    - **enable_reranking**: Whether to apply cross-encoder reranking
    - **return_context**: Return optimized context for RAG generation
    - **timeout**: Optional timeout in seconds

    **Returns:**
    - **results**: List of search results with rerank scores
    - **metrics**: Performance metrics (timing, result counts)
    - **context**: Optimized context (if return_context=true)
    """
    logger.info(
        f"Advanced search: '{request.query}' (max_results={request.max_results}, "
        f"reranking={request.enable_reranking})"
    )

    # Perform advanced search
    results, metrics = await rag_service.advanced_search(
        query=request.query,
        max_results=request.max_results,
        enable_reranking=request.enable_reranking,
        timeout=request.timeout,
    )

    # Convert SearchResult objects to dictionaries
    results_dicts = [
        {
            "content": r.content,
            "metadata": r.metadata,
            "source_path": r.source_path,
            "semantic_score": r.semantic_score,
            "keyword_score": r.keyword_score,
            "hybrid_score": r.hybrid_score,
            "rerank_score": r.rerank_score,
            "relevance_rank": r.relevance_rank,
        }
        for r in results
    ]

    response = {
        "results": results_dicts,
        "total_results": len(results_dicts),
        "query": request.query,
        "metrics": {
            "query_processing_time": metrics.query_processing_time,
            "retrieval_time": metrics.retrieval_time,
            "reranking_time": metrics.reranking_time,
            "total_time": metrics.total_time,
            "documents_considered": metrics.documents_considered,
            "final_results_count": metrics.final_results_count,
            "hybrid_search_enabled": metrics.hybrid_search_enabled,
        },
        "reranking_enabled": request.enable_reranking,
    }

    # Optionally include optimized context
    if request.return_context:
        context, context_metrics = await rag_service.get_optimized_context(
            query=request.query
        )
        response["context"] = context
        response["context_length"] = len(context)

    return response


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="rerank_results",
    error_code_prefix="KNOWLEDGE",
)
@router.post("/rerank_results")
async def rerank_results(
    request: RerankRequest,
    rag_service: RAGService = Depends(get_rag_service_dependency),
):
    """
    Rerank existing search results using cross-encoder model.

    This endpoint allows you to post-process results from basic searches
    with advanced cross-encoder reranking for improved relevance.

    **Parameters:**
    - **query**: Original search query
    - **results**: List of search results to rerank

    **Returns:**
    - **reranked_results**: Results sorted by rerank score
    - **original_count**: Number of input results
    """
    logger.info(
        f"Reranking {len(request.results)} results for query: '{request.query}'"
    )

    # Perform reranking
    reranked_results = await rag_service.rerank_results(
        query=request.query,
        results=request.results,
    )

    return {
        "reranked_results": reranked_results,
        "original_count": len(request.results),
        "query": request.query,
        "reranking_applied": True,
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rag_config",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/config/rag")
async def get_rag_configuration():
    """
    Get current RAG configuration settings.

    Returns all configurable parameters for the advanced RAG system including:
    - Hybrid search weights
    - Reranking settings
    - Performance parameters
    """
    config = get_rag_config()

    return {
        "config": config.to_dict(),
        "source": "config/complete.yaml",
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_rag_config",
    error_code_prefix="KNOWLEDGE",
)
@router.put("/config/rag")
async def update_rag_configuration(request: RAGConfigUpdate):
    """
    Update RAG configuration at runtime.

    Allows dynamic adjustment of RAG parameters without restarting the service.
    Only provided parameters will be updated; others remain unchanged.

    **Parameters:**
    - **hybrid_weight_semantic**: Weight for semantic search (0-1)
    - **hybrid_weight_keyword**: Weight for keyword search (0-1)
    - **enable_reranking**: Enable/disable cross-encoder reranking
    - **diversity_threshold**: Similarity threshold for diversification (0-1)
    - **max_results_per_stage**: Max results per retrieval stage
    """
    # Filter out None values
    updates = {k: v for k, v in request.dict().items() if v is not None}

    if not updates:
        return {
            "message": "No configuration changes provided",
            "config": get_rag_config().to_dict(),
        }

    logger.info("Updating RAG configuration: %s", list(updates.keys()))

    # Update configuration
    new_config = update_rag_config(updates)

    return {
        "message": "RAG configuration updated successfully",
        "updated_fields": list(updates.keys()),
        "config": new_config.to_dict(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_rag_stats",
    error_code_prefix="KNOWLEDGE",
)
@router.get("/stats/rag")
async def get_rag_stats(rag_service: RAGService = Depends(get_rag_service_dependency)):
    """
    Get RAG service statistics and status.

    Returns information about:
    - Service initialization status
    - Knowledge base implementation
    - Cache statistics
    - Current configuration
    """
    stats = rag_service.get_stats()

    return {
        "stats": stats,
        "service_available": True,
    }
