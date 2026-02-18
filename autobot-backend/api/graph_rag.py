#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Graph-RAG API Endpoints

Provides REST API for graph-aware RAG retrieval combining semantic search
with knowledge graph relationships.

Architecture:
- Reuses existing RAGService and AutoBotMemoryGraph
- Dependency injection for testability
- Comprehensive error handling
- Request/response validation with Pydantic
- Performance metrics tracking

Endpoints:
- POST /graph-rag/search - Graph-aware search
- GET /graph-rag/health - Service health check
- GET /graph-rag/metrics - Performance metrics
"""

import logging
from typing import Dict, List, Optional

from auth_middleware import get_current_user
from backend.services.graph_rag_service import GraphRAGService
from backend.type_defs.common import Metadata
from backend.utils.request_utils import generate_request_id
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["graph-rag"])
logger = logging.getLogger(__name__)

# ====================================================================
# Request/Response Models
# ====================================================================


class GraphRAGSearchRequest(BaseModel):
    """Request model for graph-aware RAG search."""

    query: str = Field(
        ..., min_length=1, max_length=1000, description="Search query string"
    )
    start_entity: Optional[str] = Field(
        None,
        max_length=200,
        description="Optional starting entity name for graph traversal",
    )
    max_depth: int = Field(
        2, ge=1, le=3, description="Maximum graph traversal depth (1-3 hops)"
    )
    max_results: int = Field(
        5, ge=1, le=20, description="Maximum number of results to return"
    )
    enable_reranking: bool = Field(
        True, description="Whether to apply cross-encoder reranking"
    )
    timeout: Optional[float] = Field(
        None, ge=1.0, le=30.0, description="Optional timeout in seconds (1-30s)"
    )

    @validator("query")
    def validate_query(cls, v):
        """Validate query is not just whitespace."""
        if not v.strip():
            raise ValueError("Query cannot be empty or whitespace")
        return v.strip()


class GraphRAGSearchResponse(BaseModel):
    """Response model for graph-aware RAG search."""

    success: bool = Field(..., description="Whether the search succeeded")
    results: List[Metadata] = Field(..., description="Search results")
    metrics: Metadata = Field(..., description="Performance metrics")
    request_id: str = Field(..., description="Unique request identifier")


class GraphRAGHealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(
        ..., description="Service status (healthy, degraded, unhealthy)"
    )
    components: Dict[str, str] = Field(..., description="Component health status")
    timestamp: str = Field(..., description="Timestamp of health check")


# ====================================================================
# Dependency Injection
# ====================================================================


def get_graph_rag_service(request: Request) -> GraphRAGService:
    """
    Get GraphRAGService instance from app state.

    This dependency provides the initialized GraphRAGService for API endpoints.
    It's initialized in the application lifespan and stored in app state.

    Args:
        request: FastAPI request object

    Returns:
        GraphRAGService: Initialized service instance

    Raises:
        HTTPException: If service is not available or not initialized
    """
    # Try to get service from app state
    service = getattr(request.app.state, "graph_rag_service", None)

    if service is None:
        logger.error("GraphRAGService not initialized in app state")
        raise HTTPException(
            status_code=503,
            detail="Graph-RAG service not available. Service initialization required.",
        )

    return service


# ====================================================================
# API Endpoints
# ====================================================================


def _serialize_search_results(results) -> List[Metadata]:
    """
    Convert search results to serializable format.

    Issue #398: Extracted from graph_rag_search to reduce method length.
    """
    return [
        {
            "content": r.content,
            "metadata": r.metadata,
            "semantic_score": r.semantic_score,
            "keyword_score": r.keyword_score,
            "hybrid_score": r.hybrid_score,
            "relevance_rank": r.relevance_rank,
            "source_path": r.source_path,
        }
        for r in results
    ]


def _check_component_health(service: GraphRAGService) -> Dict[str, str]:
    """
    Check health status of service components.

    Issue #398: Extracted from graph_rag_health to reduce method length.
    """
    return {
        "graph_rag_service": "healthy",
        "rag_service": "healthy" if service.rag else "unavailable",
        "memory_graph": (
            "healthy" if service.graph and service.graph.initialized else "unavailable"
        ),
    }


def _determine_overall_status(components: Dict[str, str]) -> str:
    """
    Determine overall health status from component statuses.

    Issue #398: Extracted from graph_rag_health to reduce method length.
    """
    if all(status == "healthy" for status in components.values()):
        return "healthy"
    elif any(status == "unavailable" for status in components.values()):
        return "degraded"
    return "unhealthy"


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="graph_rag_search",
    error_code_prefix="GRAPH_RAG",
)
@router.post("/search", response_model=GraphRAGSearchResponse)
async def graph_rag_search(
    search_request: GraphRAGSearchRequest = Body(...),
    service: GraphRAGService = Depends(get_graph_rag_service),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Perform graph-aware RAG search combining semantic search with graph traversal.

    Issue #398: Refactored with extracted serialization helper.
    Issue #744: Requires authenticated user.
    """
    request_id = generate_request_id()

    try:
        logger.info(
            f"[{request_id}] Graph-RAG search: '{search_request.query[:50]}...' "
            f"(start_entity={search_request.start_entity}, max_depth={search_request.max_depth})"
        )

        results, metrics = await service.graph_aware_search(
            query=search_request.query,
            start_entity=search_request.start_entity,
            max_depth=search_request.max_depth,
            max_results=search_request.max_results,
            enable_reranking=search_request.enable_reranking,
            timeout=search_request.timeout,
        )

        results_data = _serialize_search_results(results)
        metrics_data = metrics.to_response_dict()

        logger.info(
            f"[{request_id}] Graph-RAG search complete: "
            f"{len(results)} results in {metrics.total_time:.3f}s"
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "results": results_data,
                "metrics": metrics_data,
                "request_id": request_id,
            },
            media_type="application/json; charset=utf-8",
        )

    except ValueError as e:
        logger.warning("[%s] Validation error: %s", request_id, e)
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error("[%s] Graph-RAG search failed: %s", request_id, e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Graph-RAG search failed: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="graph_rag_health",
    error_code_prefix="GRAPH_RAG",
)
@router.get("/health", response_model=GraphRAGHealthResponse)
async def graph_rag_health(
    service: GraphRAGService = Depends(get_graph_rag_service),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Check Graph-RAG service health.

    Returns health status of the service and its components (RAGService,
    AutoBotMemoryGraph).

    Issue #744: Requires authenticated user.

    Returns:
        JSONResponse with health status

    Example Response:
        ```json
        {
            "status": "healthy",
            "components": {
                "graph_rag_service": "healthy",
                "rag_service": "healthy",
                "memory_graph": "healthy",
                "knowledge_base": "healthy"
            },
            "timestamp": "2025-01-15T10:30:00Z"
        }
        ```
    """
    from datetime import datetime

    try:
        service_metrics = await service.get_metrics()
        components = _check_component_health(service)
        overall_status = _determine_overall_status(components)

        return JSONResponse(
            status_code=200 if overall_status == "healthy" else 503,
            content={
                "status": overall_status,
                "components": components,
                "metrics": service_metrics,
                "timestamp": datetime.utcnow().isoformat(),
            },
            media_type="application/json; charset=utf-8",
        )

    except Exception as e:
        logger.error("Health check failed: %s", e, exc_info=True)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "components": {},
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
            },
            media_type="application/json; charset=utf-8",
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="graph_rag_metrics",
    error_code_prefix="GRAPH_RAG",
)
@router.get("/metrics")
async def graph_rag_metrics(
    service: GraphRAGService = Depends(get_graph_rag_service),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Get Graph-RAG service performance metrics.

    Returns detailed metrics about service configuration and performance.

    Issue #744: Requires authenticated user.

    Returns:
        JSONResponse with service metrics

    Example Response:
        ```json
        {
            "service": "GraphRAGService",
            "graph_weight": 0.3,
            "entity_extraction_enabled": true,
            "rag_service": {
                "enable_advanced_rag": true,
                "timeout_seconds": 10.0
            },
            "graph_initialized": true
        }
        ```
    """
    try:
        metrics = await service.get_metrics()

        return JSONResponse(
            status_code=200,
            content=metrics,
            media_type="application/json; charset=utf-8",
        )

    except Exception as e:
        logger.error("Metrics retrieval failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to retrieve metrics: {str(e)}"
        )
