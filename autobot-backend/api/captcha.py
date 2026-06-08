# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import JSONResponse

from api.schemas_common import DataResponse
from api.schemas_system import CaptchaPendingData
from api.schemas_workflows import CaptchaResolutionRequest, CaptchaResolutionResponse
from api.system_health import register_singleton_probe
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from services.captcha_human_loop import CaptchaResolutionStatus, get_captcha_human_loop

router = APIRouter(prefix="/captcha", tags=["captcha"])
logger = get_logger(__name__)


@router.post("/{captcha_id}/resolve", response_model=CaptchaResolutionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resolve_captcha",
    error_code_prefix="CAPTCHA",
)
async def resolve_captcha(
    captcha_id: str = Path(..., description="CAPTCHA ID to mark as solved"),
    request: CaptchaResolutionRequest | None = None,
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
                "timestamp": utc_timestamp(),
            },
            media_type="application/json; charset=utf-8",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error resolving CAPTCHA %s: %s", captcha_id, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to resolve CAPTCHA",
        )


@router.post("/{captcha_id}/skip", response_model=CaptchaResolutionResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="skip_captcha",
    error_code_prefix="CAPTCHA",
)
async def skip_captcha(
    captcha_id: str = Path(..., description="CAPTCHA ID to skip"),
    request: CaptchaResolutionRequest | None = None,
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
                "timestamp": utc_timestamp(),
            },
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error skipping CAPTCHA %s: %s", captcha_id, e)
        raise HTTPException(
            status_code=500,
            detail="Failed to skip CAPTCHA",
        )


@router.get("/pending", response_model=DataResponse[CaptchaPendingData])
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_pending_captchas",
    error_code_prefix="CAPTCHA",
)
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
                "timestamp": utc_timestamp(),
            },
        )

    except Exception as e:
        logger.error("Error getting pending CAPTCHAs: %s", e)
        raise HTTPException(
            status_code=500,
            detail="Failed to get pending CAPTCHAs",
        )


register_singleton_probe("captcha", get_captcha_human_loop)
