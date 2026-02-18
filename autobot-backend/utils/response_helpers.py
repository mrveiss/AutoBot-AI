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
from typing import TYPE_CHECKING, Any

from backend.type_defs.common import Metadata
from fastapi import HTTPException
from fastapi.responses import JSONResponse

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
    request_id: str = None,
) -> JSONResponse:
    """
    Create standardized error response.

    Args:
        error_code: Machine-readable error code (e.g., "INTERNAL_ERROR", "VALIDATION_ERROR")
        message: Human-readable error message
        status_code: HTTP status code (default: 500)
        request_id: Optional request ID for error tracking

    Returns:
        JSONResponse with error details

    Common Error Codes:
        - INTERNAL_ERROR: Server-side error (500)
        - VALIDATION_ERROR: Invalid input (400)
        - NOT_FOUND: Resource not found (404)
        - UNAUTHORIZED: Authentication required (401)
        - FORBIDDEN: Insufficient permissions (403)

    Example:
        >>> response = create_error_response(
        ...     error_code="VALIDATION_ERROR",
        ...     message="Invalid session ID",
        ...     request_id="abc-123",
        ...     status_code=400
        ... )
    """
    error_content = {
        "code": error_code,
        "message": message,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Include request_id if provided
    if request_id is not None:
        error_content["request_id"] = request_id

    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error_content,
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
    logger.error("%s failed: %s", context, error.message)
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
