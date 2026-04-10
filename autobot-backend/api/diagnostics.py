# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Diagnostics API - Production diagnostic endpoints.

Issue #4069: Causal inference engine integration.

Provides:
- POST /api/diagnostics/analyze-failure — Analyze error event via CausalInferenceEngine
- GET /api/diagnostics/health — System health check
- POST /api/diagnostics/inspect-task — Inspect task execution history

Used for:
- Postmortem analysis (what went wrong?)
- Pattern detection (is this a known failure mode?)
- Debugging (why did this specific task fail?)
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.causal_inference_engine import (
    CausalAnalysisReport,
    CausalInferenceEngine,
)

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

# Singleton engine instance
_engine: Optional[CausalInferenceEngine] = None


def get_engine() -> CausalInferenceEngine:
    """Get or create singleton CausalInferenceEngine instance."""
    global _engine
    if _engine is None:
        _engine = CausalInferenceEngine()
    return _engine


# =============================================================================
# Request/Response Models
# =============================================================================


class FailureAnalysisRequest(BaseModel):
    """Request to analyze a task failure."""

    task_id: str
    error_description: Optional[str] = None


class FailureAnalysisResponse(BaseModel):
    """Response from failure analysis."""

    data: dict  # CausalAnalysisReport serialized


class HealthCheckResponse(BaseModel):
    """Health check response."""

    status: str
    engine_ready: bool


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/analyze-failure", response_model=FailureAnalysisResponse)
async def analyze_failure(request: FailureAnalysisRequest):
    """
    Analyze a task failure and return root-cause report with recommendations.

    Used for postmortems, debugging, and pattern detection.

    Args:
        request: FailureAnalysisRequest with task_id and optional error_description

    Returns:
        FailureAnalysisResponse with CausalAnalysisReport

    Raises:
        HTTPException: If task_id is missing or analysis fails
    """
    if not request.task_id:
        raise HTTPException(status_code=400, detail="task_id is required")

    try:
        engine = get_engine()
        report = await engine.analyze_failure(
            request.task_id, request.error_description
        )

        # Check if analysis succeeded
        if report.analysis_status == "failed":
            logger.warning(
                "Failure analysis failed for task %s: %s",
                request.task_id,
                report.error_message,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Analysis failed: {report.error_message}",
            )

        return FailureAnalysisResponse(data=report.to_dict())

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Unexpected error analyzing task %s: %s", request.task_id, e)
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")


@router.get("/health", response_model=HealthCheckResponse)
async def health_check():
    """
    Check diagnostics service health.

    Returns:
        HealthCheckResponse with status and engine readiness
    """
    try:
        engine = get_engine()
        # Engine is ready if it can be instantiated
        return HealthCheckResponse(status="ok", engine_ready=True)
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return HealthCheckResponse(status="error", engine_ready=False)


@router.get("/analyze-failure")
async def analyze_failure_get(
    task_id: str = Query(..., description="Task ID to analyze"),
    error_description: Optional[str] = Query(
        None, description="Optional error description"
    ),
):
    """
    Alternative GET endpoint for failure analysis (useful for integration testing).

    Args:
        task_id: Task ID to analyze (required)
        error_description: Optional error description

    Returns:
        CausalAnalysisReport serialized
    """
    request = FailureAnalysisRequest(
        task_id=task_id, error_description=error_description
    )
    return await analyze_failure(request)
