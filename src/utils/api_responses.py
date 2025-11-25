# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Response Utilities - Standardized Response Pattern

This module provides utilities for creating standardized API responses across
all FastAPI endpoints. Eliminates duplicate response construction code.

CONSOLIDATES PATTERNS FROM:
===========================
- 65+ success response patterns across 19 API files
- 803+ error handling patterns across 76 API files
- Inconsistent response structures
- Repetitive try/except + HTTPException blocks

BENEFITS:
=========
✅ Eliminates 200+ lines of duplicate response code
✅ Standardizes response structure across all endpoints
✅ Type-safe responses with Pydantic models
✅ Consistent error handling and status codes
✅ Built-in pagination support
✅ Reduces 3-8 lines per endpoint to single function call

USAGE PATTERN:
==============
from src.utils.api_responses import success_response, error_response, not_found

# Old pattern (8 lines)
try:
    result = do_something()
    return {"success": True, "data": result, "message": "Success"}
except ValueError as e:
    raise HTTPException(status_code=400, detail=str(e))
except Exception as e:
    raise HTTPException(status_code=500, detail=f"Failed: {str(e)}")

# New pattern (1 line for success, 1 line for errors)
result = do_something()
return success_response(data=result, message="Success")

# Or with error handling
try:
    result = do_something()
    return success_response(data=result)
except ValueError as e:
    return bad_request(str(e))
except Exception as e:
    return internal_error(f"Failed: {str(e)}")

ADVANCED USAGE:
===============
# Pagination
return paginated_response(
    items=results,
    total=total_count,
    page=page_num,
    page_size=page_size
)

# Custom status codes
return success_response(data=item, status_code=201)  # Created

# With error codes
return error_response(
    message="Resource not found",
    status_code=404,
    error_code="RESOURCE_404"
)
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

# ============================================================================
# Response Models (Pydantic)
# ============================================================================


class StandardResponse(BaseModel):
    """
    Standard API response model.

    All successful API responses should follow this structure for consistency.
    """

    success: bool = Field(True, description="Whether the operation succeeded")
    message: Optional[str] = Field(None, description="Human-readable message")
    data: Optional[Any] = Field(None, description="Response data payload")
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Response timestamp (ISO 8601)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Operation completed successfully",
                "data": {"id": "123", "name": "Example"},
                "timestamp": "2025-01-09T10:00:00.000000",
            }
        }


class ErrorResponse(BaseModel):
    """
    Standard error response model.

    All error API responses should follow this structure for consistency.
    """

    success: bool = Field(False, description="Always false for errors")
    error: str = Field(..., description="Error message")
    error_code: Optional[str] = Field(None, description="Machine-readable error code")
    details: Optional[Dict[str, Any]] = Field(
        None, description="Additional error details"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Error timestamp (ISO 8601)",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "success": False,
                "error": "Resource not found",
                "error_code": "RESOURCE_404",
                "details": {"resource_id": "123", "resource_type": "workflow"},
                "timestamp": "2025-01-09T10:00:00.000000",
            }
        }


class PaginatedResponse(BaseModel):
    """
    Paginated response model for list endpoints.
    """

    success: bool = Field(True, description="Whether the operation succeeded")
    message: Optional[str] = Field(None, description="Human-readable message")
    data: List[Any] = Field(..., description="List of items for current page")
    pagination: Dict[str, Any] = Field(
        ...,
        description="Pagination metadata",
        json_schema_extra={
            "example": {
                "page": 1,
                "page_size": 20,
                "total_items": 100,
                "total_pages": 5,
                "has_next": True,
                "has_previous": False,
            }
        },
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.utcnow().isoformat(),
        description="Response timestamp",
    )


# ============================================================================
# Success Response Factories
# ============================================================================


def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = status.HTTP_200_OK,
    **kwargs,
) -> JSONResponse:
    """
    Create a standardized success response.

    Args:
        data: Response payload data
        message: Optional success message
        status_code: HTTP status code (default: 200)
        **kwargs: Additional fields to include in response

    Returns:
        JSONResponse with standardized success structure

    Examples:
        >>> return success_response(data={"id": "123"}, message="Created")

        >>> return success_response(
        ...     data=workflow_data,
        ...     message="Workflow started",
        ...     status_code=201
        ... )

        >>> # With additional fields
        >>> return success_response(
        ...     data=results,
        ...     workflow_id="abc123",
        ...     execution_time=1.5
        ... )
    """
    response_data = {
        "success": True,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if message is not None:
        response_data["message"] = message

    if data is not None:
        response_data["data"] = data

    # Add any additional fields
    response_data.update(kwargs)

    return JSONResponse(
        content=response_data,
        status_code=status_code,
        media_type="application/json; charset=utf-8",
    )


def paginated_response(
    items: List[Any],
    total: int,
    page: int = 1,
    page_size: int = 20,
    message: Optional[str] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a standardized paginated response.

    Args:
        items: List of items for current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page
        message: Optional message
        **kwargs: Additional fields to include

    Returns:
        JSONResponse with pagination metadata

    Examples:
        >>> return paginated_response(
        ...     items=workflows,
        ...     total=150,
        ...     page=2,
        ...     page_size=20
        ... )
    """
    total_pages = (total + page_size - 1) // page_size  # Ceiling division

    response_data = {
        "success": True,
        "data": items,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_items": total,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_previous": page > 1,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }

    if message:
        response_data["message"] = message

    # Add any additional fields
    response_data.update(kwargs)

    return JSONResponse(
        content=response_data,
        status_code=status.HTTP_200_OK,
        media_type="application/json; charset=utf-8",
    )


# ============================================================================
# Error Response Factories
# ============================================================================


def error_response(
    message: str,
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a standardized error response.

    Args:
        message: Error message
        status_code: HTTP status code (default: 500)
        error_code: Machine-readable error code
        details: Additional error details
        **kwargs: Additional fields to include

    Returns:
        JSONResponse with standardized error structure

    Examples:
        >>> return error_response(
        ...     message="Workflow not found",
        ...     status_code=404,
        ...     error_code="WORKFLOW_404"
        ... )

        >>> return error_response(
        ...     message="Invalid input",
        ...     status_code=400,
        ...     details={"field": "username", "issue": "too_short"}
        ... )
    """
    response_data = {
        "success": False,
        "error": message,
        "timestamp": datetime.utcnow().isoformat(),
    }

    if error_code:
        response_data["error_code"] = error_code

    if details:
        response_data["details"] = details

    # Add any additional fields
    response_data.update(kwargs)

    return JSONResponse(
        content=response_data,
        status_code=status_code,
        media_type="application/json; charset=utf-8",
    )


# ============================================================================
# Common HTTP Error Helpers
# ============================================================================


def not_found(
    message: str = "Resource not found",
    error_code: Optional[str] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a 404 Not Found response.

    Args:
        message: Error message (default: "Resource not found")
        error_code: Optional error code
        **kwargs: Additional fields

    Returns:
        404 error response

    Examples:
        >>> return not_found("Workflow not found", error_code="WORKFLOW_404")
    """
    return error_response(
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
        error_code=error_code,
        **kwargs,
    )


def bad_request(
    message: str = "Invalid request",
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a 400 Bad Request response.

    Args:
        message: Error message
        error_code: Optional error code
        details: Validation error details
        **kwargs: Additional fields

    Returns:
        400 error response

    Examples:
        >>> return bad_request(
        ...     "Invalid input",
        ...     details={"field": "email", "issue": "invalid_format"}
        ... )
    """
    return error_response(
        message=message,
        status_code=status.HTTP_400_BAD_REQUEST,
        error_code=error_code,
        details=details,
        **kwargs,
    )


def unauthorized(
    message: str = "Unauthorized",
    error_code: Optional[str] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a 401 Unauthorized response.

    Args:
        message: Error message
        error_code: Optional error code
        **kwargs: Additional fields

    Returns:
        401 error response

    Examples:
        >>> return unauthorized("Invalid token", error_code="AUTH_INVALID_TOKEN")
    """
    return error_response(
        message=message,
        status_code=status.HTTP_401_UNAUTHORIZED,
        error_code=error_code,
        **kwargs,
    )


def forbidden(
    message: str = "Forbidden",
    error_code: Optional[str] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a 403 Forbidden response.

    Args:
        message: Error message
        error_code: Optional error code
        **kwargs: Additional fields

    Returns:
        403 error response

    Examples:
        >>> return forbidden(
        ...     "Insufficient permissions",
        ...     error_code="AUTH_INSUFFICIENT_PERMS"
        ... )
    """
    return error_response(
        message=message,
        status_code=status.HTTP_403_FORBIDDEN,
        error_code=error_code,
        **kwargs,
    )


def internal_error(
    message: str = "Internal server error",
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a 500 Internal Server Error response.

    Args:
        message: Error message
        error_code: Optional error code
        details: Error details (be careful not to leak sensitive info)
        **kwargs: Additional fields

    Returns:
        500 error response

    Examples:
        >>> return internal_error(
        ...     "Database connection failed",
        ...     error_code="DB_CONNECTION_ERROR"
        ... )
    """
    return error_response(
        message=message,
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        error_code=error_code,
        details=details,
        **kwargs,
    )


def conflict(
    message: str = "Resource conflict",
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a 409 Conflict response.

    Args:
        message: Error message
        error_code: Optional error code
        details: Conflict details
        **kwargs: Additional fields

    Returns:
        409 error response

    Examples:
        >>> return conflict(
        ...     "Workflow already exists",
        ...     error_code="WORKFLOW_EXISTS",
        ...     details={"workflow_id": "abc123"}
        ... )
    """
    return error_response(
        message=message,
        status_code=status.HTTP_409_CONFLICT,
        error_code=error_code,
        details=details,
        **kwargs,
    )


def service_unavailable(
    message: str = "Service temporarily unavailable",
    error_code: Optional[str] = None,
    retry_after: Optional[int] = None,
    **kwargs,
) -> JSONResponse:
    """
    Create a 503 Service Unavailable response.

    Args:
        message: Error message
        error_code: Optional error code
        retry_after: Seconds to wait before retrying (optional)
        **kwargs: Additional fields

    Returns:
        503 error response

    Examples:
        >>> return service_unavailable(
        ...     "Redis connection unavailable",
        ...     retry_after=30
        ... )
    """
    response = error_response(
        message=message,
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        error_code=error_code,
        **kwargs,
    )

    # Add Retry-After header if specified
    if retry_after:
        response.headers["Retry-After"] = str(retry_after)

    return response


# ============================================================================
# HTTPException Compatibility (for raising instead of returning)
# ============================================================================


def raise_not_found(message: str = "Resource not found", **kwargs):
    """Raise HTTPException for 404 Not Found"""
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def raise_bad_request(message: str = "Invalid request", **kwargs):
    """Raise HTTPException for 400 Bad Request"""
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def raise_unauthorized(message: str = "Unauthorized", **kwargs):
    """Raise HTTPException for 401 Unauthorized"""
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)


def raise_forbidden(message: str = "Forbidden", **kwargs):
    """Raise HTTPException for 403 Forbidden"""
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def raise_internal_error(message: str = "Internal server error", **kwargs):
    """Raise HTTPException for 500 Internal Server Error"""
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=message
    )


def raise_conflict(message: str = "Resource conflict", **kwargs):
    """Raise HTTPException for 409 Conflict"""
    raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)
