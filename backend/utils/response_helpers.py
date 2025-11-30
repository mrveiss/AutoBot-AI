# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Response Helpers - Centralized response creation utilities.

This module provides standardized response creation functions used across
multiple API modules. Extracted to eliminate code duplication (Issue #292).

Functions:
    create_success_response: Create standardized success response dict
    create_error_response: Create standardized error JSONResponse
    handle_ai_stack_error: Handle AI Stack errors gracefully
"""

import logging
from datetime import datetime
from typing import Any, TYPE_CHECKING

from fastapi import HTTPException
from fastapi.responses import JSONResponse

from backend.type_defs.common import Metadata

if TYPE_CHECKING:
    from backend.services.ai_stack_client import AIStackError

logger = logging.getLogger(__name__)


def create_success_response(
    data: Any = None,
    message: str = "Operation successful",
) -> Metadata:
    """
    Create standardized success response dictionary.

    Args:
        data: The response payload data
        message: Human-readable success message

    Returns:
        Dict with success status, data, message, and timestamp
    """
    return {
        "success": True,
        "data": data,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }


def create_error_response(
    error_code: str = "INTERNAL_ERROR",
    message: str = "An error occurred",
    status_code: int = 500,
) -> JSONResponse:
    """
    Create standardized error response.

    Args:
        error_code: Machine-readable error code
        message: Human-readable error message
        status_code: HTTP status code

    Returns:
        JSONResponse with error details
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": {
                "code": error_code,
                "message": message,
                "timestamp": datetime.utcnow().isoformat(),
            },
        },
    )


async def handle_ai_stack_error(error: "AIStackError", context: str):
    """
    Handle AI Stack errors gracefully.

    Args:
        error: The AIStackError exception from ai_stack_client
        context: Description of the operation that failed

    Raises:
        HTTPException with appropriate status code and details
    """
    logger.error(f"{context} failed: {error.message}")
    status_code = (
        503 if error.status_code is None else (400 if error.status_code < 500 else 503)
    )

    raise HTTPException(
        status_code=status_code,
        detail={
            "error": error.message,
            "context": context,
            "ai_stack_details": error.details,
        },
    )
