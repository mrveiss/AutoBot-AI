#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Extraction API Endpoints

Provides REST API for automatic entity extraction and graph population
from conversations and messages.
from autobot_shared.logging_manager import get_logger

Architecture:
- Reuses GraphEntityExtractor, KnowledgeExtractionAgent, AutoBotMemoryGraph
- Dependency injection for testability
- Comprehensive error handling
- Request/response validation with Pydantic
- Performance metrics tracking

Endpoints:
- POST /entities/extract - Extract entities from conversation
- POST /entities/extract-batch - Batch extraction from multiple conversations
- GET /entities/extract/status/{task_id} - Check extraction task status
- GET /entities/extract/health - Service health check
"""

from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from agents.graph_entity_extractor import ExtractionResult, GraphEntityExtractor
from api.schemas_knowledge import (
    BatchExtractionRequest,
    BatchExtractionResponse,
    EntityExtractionHealthResponse,
    EntityExtractionRequest,
    EntityExtractionResponse,
    ExtractionMessage,
)
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from utils.request_utils import generate_request_id

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["entity-extraction"])
logger = get_logger(__name__)

# ====================================================================
# Dependency Injection
# ====================================================================


def get_entity_extractor(request: Request) -> GraphEntityExtractor:
    """
    Get GraphEntityExtractor instance from app state.

    This dependency provides the initialized GraphEntityExtractor for API endpoints.
    It's initialized in the application lifespan and stored in app state.

    Args:
        request: FastAPI request object

    Returns:
        GraphEntityExtractor: Initialized extractor instance

    Raises:
        HTTPException: If extractor is not available or not initialized
    """
    # Try to get extractor from app state
    extractor = getattr(request.app.state, "entity_extractor", None)

    if extractor is None:
        logger.error("GraphEntityExtractor not initialized in app state")
        raise HTTPException(
            status_code=503,
            detail="Entity extraction service not available. Service initialization required.",
        )

    return extractor


# ====================================================================
# Helper Functions for extract_entities (Issue #665)
# ====================================================================


def _prepare_extraction_messages(messages: List[ExtractionMessage]) -> list:
    """
    Convert Pydantic messages to dict format for extraction.

    Issue #665: Extracted from extract_entities to reduce function length.

    Args:
        messages: List of Pydantic Message objects

    Returns:
        List of message dictionaries
    """
    return [msg.dict() for msg in messages]


def _log_extraction_result(request_id: str, result: ExtractionResult) -> None:
    """
    Log extraction completion with metrics.

    Issue #665: Extracted from extract_entities to reduce function length.

    Args:
        request_id: Request tracking ID
        result: Extraction result with metrics
    """
    logger.info(
        f"[{request_id}] Extraction complete: {result.entities_created} entities, "
        f"{result.relations_created} relations in {result.processing_time:.3f}s"
    )


def _build_extraction_response(result: ExtractionResult, request_id: str) -> JSONResponse:
    """
    Build JSONResponse from extraction result.

    Issue #665: Extracted from extract_entities to reduce function length.

    Args:
        result: Extraction result with all metrics
        request_id: Request tracking ID

    Returns:
        JSONResponse with extraction results
    """
    return JSONResponse(
        status_code=200,
        content={
            "success": len(result.errors) == 0,
            "conversation_id": result.conversation_id,
            "facts_analyzed": result.facts_analyzed,
            "entities_created": result.entities_created,
            "relations_created": result.relations_created,
            "processing_time": result.processing_time,
            "errors": result.errors,
            "request_id": request_id,
        },
        media_type="application/json; charset=utf-8",
    )


# ====================================================================
# API Endpoints
# ====================================================================


@router.post("/extract", response_model=EntityExtractionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_entities",
    error_code_prefix="ENTITY_EXTRACTION",
)
async def extract_entities(
    extraction_request: EntityExtractionRequest = Body(...),
    extractor: GraphEntityExtractor = Depends(get_entity_extractor),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Extract entities from conversation and populate knowledge graph. Ref: #1088.

    Uses GraphEntityExtractor to extract entities/relationships from messages.
    Issues #665 (helpers), #744 (auth required).

    Returns:
        JSONResponse with extraction results and metrics
    """
    request_id = generate_request_id()

    try:
        logger.info(
            f"[{request_id}] Entity extraction: '{extraction_request.conversation_id}' "
            f"({len(extraction_request.messages)} messages)"
        )

        # Convert Pydantic messages to dict format (Issue #665: uses helper)
        messages_dict = _prepare_extraction_messages(extraction_request.messages)

        # Execute entity extraction
        result: ExtractionResult = await extractor.extract_and_populate(
            conversation_id=extraction_request.conversation_id,
            messages=messages_dict,
            session_metadata=extraction_request.session_metadata,
        )

        # Log completion (Issue #665: uses helper)
        _log_extraction_result(request_id, result)

        # Build response (Issue #665: uses helper)
        return _build_extraction_response(result, request_id)

    except ValueError as e:
        logger.warning("[%s] Validation error: %s", request_id, e)
        raise HTTPException(status_code=400, detail="Internal server error")

    except Exception as e:
        logger.error("[%s] Entity extraction failed: %s", request_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Entity extraction failed")


def _build_extraction_tasks(batch_request: "BatchExtractionRequest", extractor: GraphEntityExtractor) -> List:
    """
    Build extraction tasks for batch processing.

    Issue #281: Extracted helper for task building.

    Args:
        batch_request: Batch extraction request
        extractor: GraphEntityExtractor instance

    Returns:
        List of extraction coroutine tasks
    """
    tasks = []
    for conv_request in batch_request.conversations:
        messages_dict = [msg.dict() for msg in conv_request.messages]

        task = extractor.extract_and_populate(
            conversation_id=conv_request.conversation_id,
            messages=messages_dict,
            session_metadata=conv_request.session_metadata,
        )
        tasks.append(task)
    return tasks


def _process_extraction_results(results: List, batch_request: "BatchExtractionRequest", request_id: str) -> tuple:
    """
    Process extraction results into successful and failed lists.

    Issue #281: Extracted helper for result processing.

    Args:
        results: Raw results from asyncio.gather
        batch_request: Original batch request
        request_id: Request tracking ID

    Returns:
        Tuple of (successful_results, failed_results)
    """
    successful_results = []
    failed_results = []

    for idx, result in enumerate(results):
        conv_id = batch_request.conversations[idx].conversation_id

        if isinstance(result, Exception):
            logger.error("[%s] Extraction failed for %s: %s", request_id, conv_id, result)
            failed_results.append(
                {
                    "success": False,
                    "conversation_id": conv_id,
                    "facts_analyzed": 0,
                    "entities_created": 0,
                    "relations_created": 0,
                    "processing_time": 0.0,
                    "errors": [str(result)],
                    "request_id": request_id,
                }
            )
        else:
            successful_results.append(
                {
                    "success": len(result.errors) == 0,
                    "conversation_id": result.conversation_id,
                    "facts_analyzed": result.facts_analyzed,
                    "entities_created": result.entities_created,
                    "relations_created": result.relations_created,
                    "processing_time": result.processing_time,
                    "errors": result.errors,
                    "request_id": request_id,
                }
            )

    return successful_results, failed_results


@router.post("/extract-batch", response_model=BatchExtractionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="extract_entities_batch",
    error_code_prefix="ENTITY_EXTRACTION",
)
async def extract_entities_batch(
    batch_request: BatchExtractionRequest = Body(...),
    extractor: GraphEntityExtractor = Depends(get_entity_extractor),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Extract entities from multiple conversations in batch. Ref: #1088.

    Issues #281 (helpers), #744 (auth). Processes conversations in parallel.

    Returns:
        JSONResponse with batch extraction results
    """
    import asyncio
    import time

    request_id = generate_request_id()
    start_time = time.perf_counter()

    try:
        logger.info(f"[{request_id}] Batch extraction: {len(batch_request.conversations)} conversations")

        # Build extraction tasks (Issue #281: uses helper)
        tasks = _build_extraction_tasks(batch_request, extractor)

        # Wait for all extractions to complete
        results: List[ExtractionResult] = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results (Issue #281: uses helper)
        successful_results, failed_results = _process_extraction_results(results, batch_request, request_id)

        total_time = time.perf_counter() - start_time

        logger.info(
            f"[{request_id}] Batch extraction complete: "
            f"{len(successful_results)} successful, {len(failed_results)} failed "
            f"in {total_time:.3f}s"
        )

        return JSONResponse(
            status_code=200,
            content={
                "success": len(failed_results) == 0,
                "total_conversations": len(batch_request.conversations),
                "successful_extractions": len(successful_results),
                "failed_extractions": len(failed_results),
                "results": successful_results + failed_results,
                "total_processing_time": total_time,
                "request_id": request_id,
            },
            media_type="application/json; charset=utf-8",
        )

    except Exception as e:
        logger.error("[%s] Batch extraction failed: %s", request_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Batch extraction failed")


@router.get("/extract/health", response_model=EntityExtractionHealthResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="entity_extraction_health",
    error_code_prefix="ENTITY_EXTRACTION",
)
async def entity_extraction_health(
    extractor: GraphEntityExtractor = Depends(get_entity_extractor),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Check entity extraction service health. Ref: #1088.

    Issue #744 (auth). Returns status of extractor/graph/agent components.
    """
    try:
        # Check component health
        components = {
            "entity_extractor": "healthy",
            "knowledge_extraction_agent": ("healthy" if extractor.extractor else "unavailable"),
            "memory_graph": ("healthy" if extractor.graph and extractor.graph.initialized else "unavailable"),
        }

        # Determine overall status
        if all(status == "healthy" for status in components.values()):
            overall_status = "healthy"
        elif any(status == "unavailable" for status in components.values()):
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

        return JSONResponse(
            status_code=200 if overall_status == "healthy" else 503,
            content={
                "status": overall_status,
                "components": components,
                "timestamp": utc_timestamp(),
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
                "timestamp": utc_timestamp(),
                "error": "Internal server error",
            },
            media_type="application/json; charset=utf-8",
        )
