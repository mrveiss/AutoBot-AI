# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
CAPTCHA Resolution API Endpoints

This module provides REST API endpoints for the human-in-the-loop CAPTCHA
handling system. Allows frontend to mark CAPTCHAs as resolved or skipped.

Endpoints:
- POST /api/captcha/{captcha_id}/resolve - Mark CAPTCHA as solved
- POST /api/captcha/{captcha_id}/skip - Mark CAPTCHA as skipped
- GET /api/captcha/pending - Get list of pending CAPTCHAs
- GET /api/captcha/health - Health check

Related: Issue #206
"""

import logging
from datetime import datetime
from typing import Optional

from backend.services.captcha_human_loop import (
    CaptchaResolutionStatus,
    get_captcha_human_loop,
)
from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter(prefix="/captcha", tags=["captcha"])
logger = logging.getLogger(__name__)


class CaptchaResolutionRequest(BaseModel):
    """Request model for CAPTCHA resolution"""

    notes: Optional[str] = None


class CaptchaResolutionResponse(BaseModel):
    """Response model for CAPTCHA resolution"""

    success: bool
    captcha_id: str
    status: str
    message: str
    timestamp: Optional[str] = None


@router.post("/{captcha_id}/resolve", response_model=CaptchaResolutionResponse)
async def resolve_captcha(
    captcha_id: str = Path(..., description="CAPTCHA ID to mark as solved"),
    request: Optional[CaptchaResolutionRequest] = None,
) -> JSONResponse:
    """
    Mark a CAPTCHA as successfully solved by user.

    This endpoint is called from the frontend when user confirms they have
    solved the CAPTCHA through the VNC interface.

    Args:
        captcha_id: UUID of the CAPTCHA to resolve
        request: Optional notes about resolution

    Returns:
        CaptchaResolutionResponse with success status
    """
    logger.info("Marking CAPTCHA %s as resolved", captcha_id)

    try:
        captcha_service = get_captcha_human_loop()
        success = await captcha_service.mark_captcha_resolved(
            captcha_id=captcha_id,
            status=CaptchaResolutionStatus.SOLVED,
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"CAPTCHA not found or already resolved: {captcha_id}",
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "captcha_id": captcha_id,
                "status": "solved",
                "message": "CAPTCHA marked as solved. Research will continue.",
                "timestamp": datetime.utcnow().isoformat(),
            },
            media_type="application/json; charset=utf-8",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resolving CAPTCHA %s: %s", captcha_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to resolve CAPTCHA: {str(e)}",
        )


@router.post("/{captcha_id}/skip", response_model=CaptchaResolutionResponse)
async def skip_captcha(
    captcha_id: str = Path(..., description="CAPTCHA ID to skip"),
    request: Optional[CaptchaResolutionRequest] = None,
) -> JSONResponse:
    """
    Mark a CAPTCHA as skipped (user chose not to solve).

    This endpoint is called from the frontend when user decides to skip
    solving the CAPTCHA. The source will be excluded from research results.

    Args:
        captcha_id: UUID of the CAPTCHA to skip
        request: Optional notes about why skipped

    Returns:
        CaptchaResolutionResponse with skip status
    """
    logger.info("Marking CAPTCHA %s as skipped", captcha_id)

    try:
        captcha_service = get_captcha_human_loop()
        success = await captcha_service.mark_captcha_resolved(
            captcha_id=captcha_id,
            status=CaptchaResolutionStatus.SKIPPED,
        )

        if not success:
            raise HTTPException(
                status_code=404,
                detail=f"CAPTCHA not found or already resolved: {captcha_id}",
            )

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "captcha_id": captcha_id,
                "status": "skipped",
                "message": "CAPTCHA skipped. Source will be excluded from results.",
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error skipping CAPTCHA %s: %s", captcha_id, e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to skip CAPTCHA: {str(e)}",
        )


@router.get("/pending")
async def get_pending_captchas() -> JSONResponse:
    """
    Get list of CAPTCHAs currently awaiting human resolution.

    Returns:
        List of pending CAPTCHA IDs and their statuses
    """
    try:
        captcha_service = get_captcha_human_loop()
        pending = captcha_service.get_pending_captchas()

        return JSONResponse(
            status_code=200,
            content={
                "success": True,
                "pending_captchas": pending,
                "count": len(pending),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        logger.error("Error getting pending CAPTCHAs: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get pending CAPTCHAs: {str(e)}",
        )


@router.get("/health")
async def captcha_health() -> JSONResponse:
    """
    Health check for CAPTCHA service.

    Returns:
        Health status of the CAPTCHA handling service
    """
    try:
        captcha_service = get_captcha_human_loop()
        pending_count = len(captcha_service.get_pending_captchas())

        return JSONResponse(
            status_code=200,
            content={
                "status": "healthy",
                "service": "captcha_human_loop",
                "pending_captchas": pending_count,
                "timeout_seconds": captcha_service.timeout_seconds,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

    except Exception as e:
        logger.error("CAPTCHA health check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": "captcha_human_loop",
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat(),
            },
        )
