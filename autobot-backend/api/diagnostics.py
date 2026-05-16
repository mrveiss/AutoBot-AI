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

from fastapi import APIRouter, HTTPException, Query

from api.schemas_system import (
    FailureAnalysisRequest,
    FailureAnalysisResponse,
)
from api.system_health import register_singleton_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from services.causal_inference_engine import CausalInferenceEngine

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/api/diagnostics", tags=["diagnostics"])

# Singleton engine instance
_engine: CausalInferenceEngine | None = None


def get_engine() -> CausalInferenceEngine:
    """Get or create singleton CausalInferenceEngine instance."""
    global _engine
    if _engine is None:
        _engine = CausalInferenceEngine()
    return _engine


# =============================================================================
# Endpoints
# =============================================================================


@router.post("/analyze-failure", response_model=FailureAnalysisResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_failure",
    error_code_prefix="DIAGNOSTICS",
)
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
        report = await engine.analyze_failure(request.task_id, request.error_description)

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


register_singleton_probe("diagnostics", get_engine)


@router.get("/analyze-failure", response_model=FailureAnalysisResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="analyze_failure_get",
    error_code_prefix="DIAGNOSTICS",
)
async def analyze_failure_get(
    task_id: str = Query(..., description="Task ID to analyze"),
    error_description: str | None = Query(None, description="Optional error description"),
):
    """
    Alternative GET endpoint for failure analysis (useful for integration testing).

    Args:
        task_id: Task ID to analyze (required)
        error_description: Optional error description

    Returns:
        CausalAnalysisReport serialized
    """
    request = FailureAnalysisRequest(task_id=task_id, error_description=error_description)
    return await analyze_failure(request)
