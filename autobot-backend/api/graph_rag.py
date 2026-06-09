#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from typing import Dict, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_knowledge import (
    GraphRagMetricsData,
    GraphRAGSearchRequest,
    GraphRAGSearchResponse,
)
from api.system_health import register_app_state_probe
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.graph_rag_service import GraphRAGService
from type_defs.common import Metadata
from utils.request_utils import generate_request_id

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["graph-rag"])
logger = get_logger(__name__)

# ====================================================================
# Request/Response Models
# ====================================================================


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
        "memory_graph": ("healthy" if service.graph and service.graph.initialized else "unavailable"),
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


@router.post("/search", response_model=GraphRAGSearchResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="graph_rag_search",
    error_code_prefix="GRAPH_RAG",
)
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
            f"[{request_id}] Graph-RAG search complete: " f"{len(results)} results in {metrics.total_time:.3f}s"
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
        raise HTTPException(status_code=400, detail="Internal server error")

    except Exception as e:
        logger.error("[%s] Graph-RAG search failed: %s", request_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Graph-RAG search failed")


register_app_state_probe("graph_rag", "graph_rag_service")


@router.get("/metrics", response_model=DataResponse[GraphRagMetricsData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="graph_rag_metrics",
    error_code_prefix="GRAPH_RAG",
)
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
        raise HTTPException(status_code=500, detail="Failed to retrieve metrics")
