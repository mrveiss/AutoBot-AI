# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Feedback API Router (Issue #905)

Endpoints for completion feedback tracking and model improvement.
"""

import logging
from typing import Dict, List, Optional

from backend.services.feedback_tracker import FeedbackTracker
from backend.services.incremental_trainer import IncrementalTrainer
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/code-completion/feedback", tags=["feedback"])

# Initialize services
feedback_tracker = FeedbackTracker()


# =============================================================================
# Request/Response Models
# =============================================================================


class FeedbackRequest(BaseModel):
    """Request to record completion feedback."""

    context: str = Field(..., description="Code context before completion")
    suggestion: str = Field(..., description="Suggested completion text")
    action: str = Field(..., description="User action: 'accepted' or 'rejected'")
    user_id: Optional[str] = Field(None, description="User identifier")
    language: Optional[str] = Field(None, description="Programming language")
    file_path: Optional[str] = Field(None, description="File path")
    pattern_id: Optional[int] = Field(None, description="Pattern ID if applicable")
    confidence_score: Optional[float] = Field(
        None, description="Model confidence (0-1)"
    )
    completion_rank: Optional[int] = Field(
        None, description="Position in top-k suggestions"
    )


class FeedbackResponse(BaseModel):
    """Response from feedback recording."""

    status: str
    feedback_id: int
    message: str


class MetricsResponse(BaseModel):
    """Acceptance rate metrics."""

    time_window_days: int
    total_feedback: int
    accepted: int
    rejected: int
    acceptance_rate: float
    language_breakdown: Dict
    top_patterns: List[Dict]


class RetrainRequest(BaseModel):
    """Request to trigger retraining."""

    mode: str = Field(
        default="incremental",
        description="Training mode: 'incremental' or 'full'",
    )
    language: Optional[str] = Field(None, description="Filter by language")
    num_epochs: int = Field(
        default=5, ge=1, le=20, description="Epochs for full retrain"
    )


class RetrainResponse(BaseModel):
    """Response from retraining trigger."""

    status: str
    message: str
    training_started: bool


# =============================================================================
# API Endpoints
# =============================================================================


@router.post("/", response_model=FeedbackResponse)
async def record_feedback(request: FeedbackRequest):
    """
    Record completion feedback event.

    Logs whether user accepted or rejected a completion suggestion.
    Updates pattern statistics for learning loop.

    - **context**: Code context before completion
    - **suggestion**: Suggested completion text
    - **action**: 'accepted' or 'rejected'
    - **pattern_id**: Optional link to CodePattern
    """
    # Validate action
    if request.action not in ["accepted", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="action must be 'accepted' or 'rejected'",
        )

    try:
        feedback = feedback_tracker.record_feedback(
            context=request.context,
            suggestion=request.suggestion,
            action=request.action,
            user_id=request.user_id,
            language=request.language,
            file_path=request.file_path,
            pattern_id=request.pattern_id,
            confidence_score=request.confidence_score,
            completion_rank=request.completion_rank,
        )

        return FeedbackResponse(
            status="success",
            feedback_id=feedback.id,
            message=f"Feedback recorded: {request.action}",
        )

    except Exception as e:
        logger.error(f"Failed to record feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/metrics", response_model=MetricsResponse)
async def get_acceptance_metrics(
    language: Optional[str] = Query(None, description="Filter by language"),
    pattern_type: Optional[str] = Query(None, description="Filter by pattern type"),
    time_window_days: int = Query(7, ge=1, le=90, description="Time window in days"),
):
    """
    Get acceptance rate metrics.

    Returns statistics about completion acceptance rates:
    - Overall acceptance rate
    - Per-language breakdown
    - Top performing patterns

    - **language**: Filter by programming language
    - **time_window_days**: Time window for metrics (1-90 days)
    """
    try:
        metrics = feedback_tracker.get_acceptance_metrics(
            language=language,
            pattern_type=pattern_type,
            time_window_days=time_window_days,
        )

        return MetricsResponse(**metrics)

    except Exception as e:
        logger.error(f"Failed to get metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/recent")
async def get_recent_feedback(
    limit: int = Query(50, ge=1, le=500, description="Maximum events to return"),
    action: Optional[str] = Query(None, description="Filter by action"),
):
    """
    Get recent feedback events.

    Returns recent completion feedback for analysis.

    - **limit**: Maximum number of events (1-500)
    - **action**: Filter by 'accepted' or 'rejected'
    """
    # Validate action if provided
    if action and action not in ["accepted", "rejected"]:
        raise HTTPException(
            status_code=400,
            detail="action must be 'accepted' or 'rejected'",
        )

    try:
        events = feedback_tracker.get_recent_feedback(limit=limit, action=action)

        return {
            "events": events,
            "count": len(events),
        }

    except Exception as e:
        logger.error(f"Failed to get recent feedback: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retrain", response_model=RetrainResponse)
async def trigger_retraining(
    request: RetrainRequest, background_tasks: BackgroundTasks
):
    """
    Trigger model retraining with feedback.

    Two modes available:
    - **incremental**: Fast online learning update from recent feedback
    - **full**: Complete model retraining (slow, recommended weekly)

    - **mode**: 'incremental' (default) or 'full'
    - **language**: Optional language filter
    - **num_epochs**: Epochs for full retrain (default: 5)
    """
    # Validate mode
    if request.mode not in ["incremental", "full"]:
        raise HTTPException(
            status_code=400,
            detail="mode must be 'incremental' or 'full'",
        )

    def _run_training():
        """Background training task."""
        try:
            if request.mode == "incremental":
                logger.info("Starting incremental training...")
                trainer = IncrementalTrainer()
                result = trainer.update_from_feedback(time_window_hours=24)
                logger.info(f"Incremental training result: {result}")

            else:  # full retrain
                logger.info("Starting full retraining...")
                trainer = IncrementalTrainer()
                result = trainer.trigger_full_retrain(
                    language=request.language, num_epochs=request.num_epochs
                )
                logger.info(f"Full retrain result: {result}")

                # Mark retrain as completed
                if result["status"] == "success":
                    feedback_tracker.mark_retrain_completed()

        except Exception as e:
            logger.error(f"Training failed: {e}", exc_info=True)

    # Start background training
    background_tasks.add_task(_run_training)

    mode_desc = (
        "incremental update" if request.mode == "incremental" else "full retrain"
    )

    return RetrainResponse(
        status="success",
        message=f"Started {mode_desc} in background",
        training_started=True,
    )


@router.get("/statistics")
async def get_feedback_statistics():
    """
    Get overall feedback statistics.

    Returns high-level statistics about feedback collection
    and learning loop performance.
    """
    try:
        # Get 7-day and 30-day metrics
        metrics_7d = feedback_tracker.get_acceptance_metrics(time_window_days=7)
        metrics_30d = feedback_tracker.get_acceptance_metrics(time_window_days=30)

        return {
            "last_7_days": {
                "total_feedback": metrics_7d["total_feedback"],
                "acceptance_rate": metrics_7d["acceptance_rate"],
            },
            "last_30_days": {
                "total_feedback": metrics_30d["total_feedback"],
                "acceptance_rate": metrics_30d["acceptance_rate"],
            },
            "language_breakdown_7d": metrics_7d["language_breakdown"],
            "top_patterns": metrics_7d["top_patterns"],
        }

    except Exception as e:
        logger.error(f"Failed to get statistics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
