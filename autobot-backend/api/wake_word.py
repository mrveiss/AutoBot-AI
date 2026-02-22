# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Wake Word Detection API Endpoints
Issue #54 - Advanced Wake Word Detection Optimization
"""

import logging
from typing import List

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from backend.services.wake_word_service import WakeWordDetector, get_wake_word_detector
from backend.type_defs.common import Metadata

logger = logging.getLogger(__name__)
router = APIRouter(tags=["wake_word", "voice"])


class WakeWordCheckRequest(BaseModel):
    """Request to check text for wake word"""

    text: str = Field(..., description="Text to check for wake word")
    confidence: float = Field(
        default=1.0, ge=0.0, le=1.0, description="Recognition confidence"
    )


class WakeWordCheckResponse(BaseModel):
    """Response for wake word check"""

    detected: bool
    wake_word: str = ""
    confidence: float = 0.0
    timestamp: float = 0.0
    metadata: Metadata = {}


class WakeWordConfigRequest(BaseModel):
    """Request to update wake word configuration"""

    enabled: bool = None
    wake_words: List[str] = None
    confidence_threshold: float = None
    cooldown_seconds: float = None
    adaptive_threshold: bool = None
    max_false_positive_rate: float = None
    max_cpu_percent: float = None  # Issue #927: CPU cap for always-on detection


class AddWakeWordRequest(BaseModel):
    """Request to add a new wake word"""

    wake_word: str = Field(..., min_length=2, max_length=50)


class ReportFeedbackRequest(BaseModel):
    """Request to report detection feedback"""

    is_correct: bool = Field(
        ..., description="True if detection was correct, False if false positive"
    )


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="check_wake_word",
    error_code_prefix="WAKE_WORD",
)
@router.post("/check", response_model=WakeWordCheckResponse)
async def check_wake_word(request: WakeWordCheckRequest) -> WakeWordCheckResponse:
    """
    Check if text contains a wake word.

    This endpoint analyzes the provided text to detect wake words with
    confidence scoring and false positive reduction.
    """
    detector = get_wake_word_detector()
    event = detector.check_text_for_wake_word(request.text, request.confidence)

    if event:
        return WakeWordCheckResponse(
            detected=True,
            wake_word=event.wake_word,
            confidence=event.confidence,
            timestamp=event.timestamp,
            metadata=event.metadata,
        )

    return WakeWordCheckResponse(detected=False)


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_wake_words",
    error_code_prefix="WAKE_WORD",
)
@router.get("/words")
async def get_wake_words() -> Metadata:
    """Get list of configured wake words"""
    detector = get_wake_word_detector()
    return {
        "wake_words": detector.get_wake_words(),
        "total": len(detector.get_wake_words()),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="add_wake_word",
    error_code_prefix="WAKE_WORD",
)
@router.post("/words")
async def add_wake_word(request: AddWakeWordRequest) -> Metadata:
    """Add a new wake word to the detection list"""
    detector = get_wake_word_detector()
    success = detector.add_wake_word(request.wake_word)

    if success:
        return {
            "success": True,
            "message": f"Wake word '{request.wake_word}' added successfully",
            "wake_words": detector.get_wake_words(),
        }

    return {
        "success": False,
        "message": f"Wake word '{request.wake_word}' already exists",
        "wake_words": detector.get_wake_words(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="remove_wake_word",
    error_code_prefix="WAKE_WORD",
)
@router.delete("/words/{wake_word}")
async def remove_wake_word(wake_word: str) -> Metadata:
    """Remove a wake word from the detection list"""
    detector = get_wake_word_detector()

    # Ensure at least one wake word remains
    if len(detector.get_wake_words()) <= 1:
        raise HTTPException(
            status_code=400,
            detail="Cannot remove the last wake word. At least one must remain.",
        )

    success = detector.remove_wake_word(wake_word)

    if success:
        return {
            "success": True,
            "message": f"Wake word '{wake_word}' removed successfully",
            "wake_words": detector.get_wake_words(),
        }

    raise HTTPException(status_code=404, detail=f"Wake word '{wake_word}' not found")


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_wake_word_config",
    error_code_prefix="WAKE_WORD",
)
@router.get("/config")
async def get_wake_word_config() -> Metadata:
    """Get current wake word detection configuration"""
    detector = get_wake_word_detector()
    return detector.get_config()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_wake_word_config",
    error_code_prefix="WAKE_WORD",
)
@router.put("/config")
async def update_wake_word_config(request: WakeWordConfigRequest) -> Metadata:
    """Update wake word detection configuration"""
    detector = get_wake_word_detector()

    updates = {}
    if request.enabled is not None:
        updates["enabled"] = request.enabled
    if request.wake_words is not None:
        updates["wake_words"] = request.wake_words
    if request.confidence_threshold is not None:
        updates["confidence_threshold"] = request.confidence_threshold
    if request.cooldown_seconds is not None:
        updates["cooldown_seconds"] = request.cooldown_seconds
    if request.adaptive_threshold is not None:
        updates["adaptive_threshold"] = request.adaptive_threshold
    if request.max_false_positive_rate is not None:
        updates["max_false_positive_rate"] = request.max_false_positive_rate
    if request.max_cpu_percent is not None:
        updates["max_cpu_percent"] = request.max_cpu_percent

    if updates:
        detector.update_config(updates)

    return {
        "success": True,
        "message": "Configuration updated",
        "config": detector.get_config(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_wake_word_stats",
    error_code_prefix="WAKE_WORD",
)
@router.get("/stats")
async def get_wake_word_stats() -> Metadata:
    """Get wake word detection statistics"""
    detector = get_wake_word_detector()
    return detector.get_stats()


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="reset_wake_word_stats",
    error_code_prefix="WAKE_WORD",
)
@router.post("/stats/reset")
async def reset_wake_word_stats() -> Metadata:
    """Reset wake word detection statistics"""
    detector = get_wake_word_detector()
    detector.reset_stats()
    return {
        "success": True,
        "message": "Statistics reset successfully",
        "stats": detector.get_stats(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="report_detection_feedback",
    error_code_prefix="WAKE_WORD",
)
@router.post("/feedback")
async def report_detection_feedback(request: ReportFeedbackRequest) -> Metadata:
    """
    Report feedback on the last wake word detection.

    This helps the adaptive threshold system improve accuracy over time.
    """
    detector = get_wake_word_detector()

    if request.is_correct:
        detector.report_true_positive()
        message = (
            "True positive reported - threshold may be adjusted for better convenience"
        )
    else:
        detector.report_false_positive()
        message = "False positive reported - threshold increased to reduce false alarms"

    return {"success": True, "message": message, "stats": detector.get_stats()}


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="enable_wake_word",
    error_code_prefix="WAKE_WORD",
)
@router.post("/enable")
async def enable_wake_word() -> Metadata:
    """Enable wake word detection"""
    detector = get_wake_word_detector()
    detector.enable()
    return {
        "success": True,
        "message": "Wake word detection enabled",
        "config": detector.get_config(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="disable_wake_word",
    error_code_prefix="WAKE_WORD",
)
@router.post("/disable")
async def disable_wake_word() -> Metadata:
    """Disable wake word detection"""
    detector = get_wake_word_detector()
    detector.disable()
    return {
        "success": True,
        "message": "Wake word detection disabled",
        "config": detector.get_config(),
    }


# -------------------------------------------------------------------------
# Background listening loop endpoints (issue #927: CPU optimization)
# -------------------------------------------------------------------------


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="start_listening",
    error_code_prefix="WAKE_WORD",
)
@router.post("/listening/start")
async def start_listening() -> Metadata:
    """
    Start the always-on background listening loop.

    The loop runs with CPU-aware duty cycling: it automatically throttles
    polling frequency when CPU usage approaches max_cpu_percent.
    """
    detector: WakeWordDetector = get_wake_word_detector()
    await detector.start_listening()
    return {
        "success": True,
        "message": "Background listening started",
        "status": detector.get_listening_status(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="stop_listening",
    error_code_prefix="WAKE_WORD",
)
@router.post("/listening/stop")
async def stop_listening() -> Metadata:
    """Stop the always-on background listening loop."""
    detector: WakeWordDetector = get_wake_word_detector()
    await detector.stop_listening()
    return {
        "success": True,
        "message": "Background listening stopped",
        "status": detector.get_listening_status(),
    }


@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_listening_status",
    error_code_prefix="WAKE_WORD",
)
@router.get("/listening/status")
async def get_listening_status() -> Metadata:
    """
    Get background listening status including real-time CPU metrics.

    Returns duty cycle, throttle event count, and current CPU usage
    to help operators tune max_cpu_percent for their hardware.
    """
    detector: WakeWordDetector = get_wake_word_detector()
    return detector.get_listening_status()
