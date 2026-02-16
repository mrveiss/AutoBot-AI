#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Entity Extraction API Endpoints

Provides REST API for automatic entity extraction and graph population
from conversations and messages.

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

import logging
from typing import Dict, List, Optional

from agents.graph_entity_extractor import ExtractionResult, GraphEntityExtractor
from auth_middleware import get_current_user
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.type_defs.common import Metadata
from backend.utils.request_utils import generate_request_id

# Issue #380: Module-level frozenset for valid message roles
_VALID_ROLES = frozenset({"user", "assistant", "system"})

# ====================================================================
# Router Configuration
# ====================================================================

router = APIRouter(tags=["entity-extraction"])
logger = logging.getLogger(__name__)

# ====================================================================
# Request/Response Models
# ====================================================================


class Message(BaseModel):
    """Message in conversation."""

    role: str = Field(..., description="Message role (user/assistant/system)")
    content: str = Field(..., min_length=1, description="Message content")

    @validator("role")
    def validate_role(cls, v):
        """Validate role is valid."""
        if v not in _VALID_ROLES:  # Issue #380: use module constant
            raise ValueError(f"Role must be one of {_VALID_ROLES}")
        return v


class EntityExtractionRequest(BaseModel):
    """Request model for entity extraction."""

    conversation_id: str = Field(
        ..., min_length=1, max_length=200, description="Conversation identifier"
    )
    messages: List[Message] = Field(
        ..., min_items=1, description="Conversation messages"
    )
    session_metadata: Optional[Metadata] = Field(
        None, description="Optional session metadata"
    )

    @validator("conversation_id")
    def validate_conversation_id(cls, v):
        """Validate conversation ID is not just whitespace."""
        if not v.strip():
            raise ValueError("Conversation ID cannot be empty or whitespace")
        return v.strip()


class BatchExtractionRequest(BaseModel):
    """Request model for batch entity extraction."""

    conversations: List[EntityExtractionRequest] = Field(
        ..., min_items=1, max_items=50, description="Conversations to process (max 50)"
    )


class EntityExtractionResponse(BaseModel):
    """Response model for entity extraction."""

    success: bool = Field(..., description="Whether extraction succeeded")
    conversation_id: str = Field(..., description="Conversation identifier")
    facts_analyzed: int = Field(..., description="Number of facts analyzed")
    entities_created: int = Field(..., description="Number of entities created")
    relations_created: int = Field(..., description="Number of relations created")
    processing_time: float = Field(..., description="Processing time in seconds")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    request_id: str = Field(..., description="Unique request identifier")


class BatchExtractionResponse(BaseModel):
    """Response model for batch extraction."""

    success: bool = Field(..., description="Whether batch succeeded")
    total_conversations: int = Field(..., description="Total conversations processed")
    successful_extractions: int = Field(
        ..., description="Number of successful extractions"
    )
    failed_extractions: int = Field(..., description="Number of failed extractions")
    results: List[EntityExtractionResponse] = Field(
        ..., description="Individual extraction results"
    )
    total_processing_time: float = Field(
        ..., description="Total processing time in seconds"
    )
    request_id: str = Field(..., description="Unique request identifier")


class HealthResponse(BaseModel):
    """Response model for health check."""

    status: str = Field(
        ..., description="Service status (healthy, degraded, unhealthy)"
    )
    components: Dict[str, str] = Field(..., description="Component health status")
    timestamp: str = Field(..., description="Timestamp of health check")


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


def _prepare_extraction_messages(messages: List[Message]) -> list:
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


def _build_extraction_response(
    result: ExtractionResult, request_id: str
) -> JSONResponse:
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="entity_extraction",
    error_code_prefix="ENTITY_EXTRACT",
)
@router.post("/extract", response_model=EntityExtractionResponse)
async def extract_entities(
    extraction_request: EntityExtractionRequest = Body(...),
    extractor: GraphEntityExtractor = Depends(get_entity_extractor),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Extract entities from conversation and populate graph.

    This endpoint uses the GraphEntityExtractor to automatically extract
    entities and relationships from conversation messages and populate the
    knowledge graph.

    Args:
        extraction_request: Extraction request parameters
        extractor: GraphEntityExtractor dependency

    Returns:
        JSONResponse with extraction results and metrics

    Raises:
        HTTPException: If extraction fails

    Example Request:
        ```json
        {
            "conversation_id": "conv-abc-123",
            "messages": [
                {"role": "user", "content": "Redis is timing out"},
                {"role": "assistant", "content": "Fixed by increasing timeout to 30s"}
            ],
            "session_metadata": {
                "user_id": "user-123",
                "timestamp": "2025-01-15T10:30:00Z"
            }
        }
        ```

    Example Response:
        ```json
        {
            "success": true,
            "conversation_id": "conv-abc-123",
            "facts_analyzed": 3,
            "entities_created": 2,
            "relations_created": 1,
            "processing_time": 1.23,
            "errors": [],
            "request_id": "req-def-456"
        }
        ```
    Issue #665: Refactored from 97 lines to use extracted helper methods.
    Issue #744: Requires authenticated user.
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
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        logger.error("[%s] Entity extraction failed: %s", request_id, e, exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Entity extraction failed: {str(e)}"
        )


def _build_extraction_tasks(
    batch_request: "BatchExtractionRequest", extractor: GraphEntityExtractor
) -> List:
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


def _process_extraction_results(
    results: List, batch_request: "BatchExtractionRequest", request_id: str
) -> tuple:
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
            logger.error(
                "[%s] Extraction failed for %s: %s", request_id, conv_id, result
            )
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


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="batch_entity_extraction",
    error_code_prefix="ENTITY_EXTRACT",
)
@router.post("/extract-batch", response_model=BatchExtractionResponse)
async def extract_entities_batch(
    batch_request: BatchExtractionRequest = Body(...),
    extractor: GraphEntityExtractor = Depends(get_entity_extractor),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Extract entities from multiple conversations in batch.

    Issue #281: Refactored from 137 lines to use extracted helper methods.
    Issue #744: Requires authenticated user.

    This endpoint processes multiple conversations in parallel for efficient
    batch entity extraction.

    Args:
        batch_request: Batch extraction request
        extractor: GraphEntityExtractor dependency

    Returns:
        JSONResponse with batch extraction results

    Raises:
        HTTPException: If batch extraction fails
    """
    import asyncio
    import time

    request_id = generate_request_id()
    start_time = time.perf_counter()

    try:
        logger.info(
            f"[{request_id}] Batch extraction: {len(batch_request.conversations)} conversations"
        )

        # Build extraction tasks (Issue #281: uses helper)
        tasks = _build_extraction_tasks(batch_request, extractor)

        # Wait for all extractions to complete
        results: List[ExtractionResult] = await asyncio.gather(
            *tasks, return_exceptions=True
        )

        # Process results (Issue #281: uses helper)
        successful_results, failed_results = _process_extraction_results(
            results, batch_request, request_id
        )

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
        raise HTTPException(
            status_code=500, detail=f"Batch extraction failed: {str(e)}"
        )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="entity_extraction_health",
    error_code_prefix="ENTITY_EXTRACT",
)
@router.get("/extract/health", response_model=HealthResponse)
async def entity_extraction_health(
    extractor: GraphEntityExtractor = Depends(get_entity_extractor),
    current_user: dict = Depends(get_current_user),
) -> JSONResponse:
    """
    Check entity extraction service health.

    Returns health status of the service and its components.

    Issue #744: Requires authenticated user.

    Returns:
        JSONResponse with health status

    Example Response:
        ```json
        {
            "status": "healthy",
            "components": {
                "entity_extractor": "healthy",
                "knowledge_extraction_agent": "healthy",
                "memory_graph": "healthy"
            },
            "timestamp": "2025-01-15T10:30:00Z"
        }
        ```
    """
    from datetime import datetime

    try:
        # Check component health
        components = {
            "entity_extractor": "healthy",
            "knowledge_extraction_agent": (
                "healthy" if extractor.extractor else "unavailable"
            ),
            "memory_graph": (
                "healthy"
                if extractor.graph and extractor.graph.initialized
                else "unavailable"
            ),
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
