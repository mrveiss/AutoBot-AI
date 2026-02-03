# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
API Response Builder Utilities

Provides standardized response building functions for consistent API responses.
All API endpoints should use these utilities to ensure uniform response format.

Standard Response Format:
{
    "success": true/false,
    "data": {...} or null,
    "message": "Human readable message",
    "error": null or "Error description",
    "error_code": null or "ERROR_CODE",
    "timestamp": "2025-01-01T00:00:00Z"
}

Usage:
    from backend.utils.response_builder import success_response, error_response

    @router.get("/items")
    async def get_items():
        items = await fetch_items()
        return success_response(data=items, message="Items retrieved")

    @router.get("/items/{id}")
    async def get_item(id: str):
        try:
            item = await fetch_item(id)
            if not item:
                return error_response("Item not found", status_code=404, error_code="ITEM_NOT_FOUND")
            return success_response(data=item)
        except Exception as e:
            return error_response(str(e), status_code=500)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, TypeVar, Union

from fastapi.responses import JSONResponse

from backend.type_defs.common import Metadata

T = TypeVar("T")


def get_timestamp() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).isoformat()


def success_response(
    data: Any = None,
    message: Optional[str] = None,
    status_code: int = 200,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """
    Build a standardized success response.

    Args:
        data: Response data (any JSON-serializable value)
        message: Optional human-readable success message
        status_code: HTTP status code (default: 200)
        headers: Optional response headers

    Returns:
        JSONResponse with standardized format
    """
    content = {
        "success": True,
        "data": data,
        "message": message,
        "error": None,
        "error_code": None,
        "timestamp": get_timestamp(),
    }

    return JSONResponse(
        content=content,
        status_code=status_code,
        headers=headers,
        media_type="application/json; charset=utf-8",
    )


def error_response(
    error: str,
    status_code: int = 400,
    error_code: Optional[str] = None,
    details: Optional[Metadata] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """
    Build a standardized error response.

    Args:
        error: Human-readable error message
        status_code: HTTP status code (default: 400)
        error_code: Optional machine-readable error code (e.g., "VALIDATION_ERROR")
        details: Optional additional error details
        headers: Optional response headers

    Returns:
        JSONResponse with standardized format
    """
    content = {
        "success": False,
        "data": None,
        "message": None,
        "error": error,
        "error_code": error_code,
        "timestamp": get_timestamp(),
    }

    if details:
        content["details"] = details

    return JSONResponse(
        content=content,
        status_code=status_code,
        headers=headers,
        media_type="application/json; charset=utf-8",
    )


def paginated_response(
    items: List[T],
    total: int,
    page: int = 1,
    page_size: int = 20,
    message: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
) -> JSONResponse:
    """
    Build a standardized paginated response.

    Args:
        items: List of items for current page
        total: Total number of items across all pages
        page: Current page number (1-indexed)
        page_size: Number of items per page
        message: Optional message
        headers: Optional response headers

    Returns:
        JSONResponse with pagination metadata
    """
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
    has_next = page < total_pages
    has_prev = page > 1

    content = {
        "success": True,
        "data": {
            "items": items,
            "pagination": {
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "has_next": has_next,
                "has_prev": has_prev,
            },
        },
        "message": message,
        "error": None,
        "error_code": None,
        "timestamp": get_timestamp(),
    }

    return JSONResponse(
        content=content,
        status_code=200,
        headers=headers,
        media_type="application/json; charset=utf-8",
    )


def created_response(
    data: Any = None,
    message: str = "Resource created successfully",
    location: Optional[str] = None,
) -> JSONResponse:
    """
    Build a standardized 201 Created response.

    Args:
        data: Created resource data
        message: Success message
        location: Optional Location header for the new resource

    Returns:
        JSONResponse with 201 status
    """
    headers = {"Location": location} if location else None
    return success_response(data=data, message=message, status_code=201, headers=headers)


def no_content_response() -> JSONResponse:
    """
    Build a 204 No Content response.

    Returns:
        JSONResponse with 204 status and no body
    """
    return JSONResponse(content=None, status_code=204)


def not_found_response(
    resource: str = "Resource",
    resource_id: Optional[str] = None,
) -> JSONResponse:
    """
    Build a standardized 404 Not Found response.

    Args:
        resource: Name of the resource type
        resource_id: Optional ID of the resource

    Returns:
        JSONResponse with 404 status
    """
    if resource_id:
        message = f"{resource} with ID '{resource_id}' not found"
    else:
        message = f"{resource} not found"

    return error_response(
        error=message,
        status_code=404,
        error_code="NOT_FOUND",
    )


def validation_error_response(
    errors: Union[List[str], Dict[str, List[str]]],
    message: str = "Validation failed",
) -> JSONResponse:
    """
    Build a standardized validation error response.

    Args:
        errors: List of error messages or dict mapping field names to errors
        message: Overall error message

    Returns:
        JSONResponse with 422 status
    """
    return error_response(
        error=message,
        status_code=422,
        error_code="VALIDATION_ERROR",
        details={"validation_errors": errors},
    )


def unauthorized_response(
    message: str = "Authentication required",
) -> JSONResponse:
    """
    Build a standardized 401 Unauthorized response.

    Args:
        message: Error message

    Returns:
        JSONResponse with 401 status
    """
    return error_response(
        error=message,
        status_code=401,
        error_code="UNAUTHORIZED",
    )


def forbidden_response(
    message: str = "Access denied",
) -> JSONResponse:
    """
    Build a standardized 403 Forbidden response.

    Args:
        message: Error message

    Returns:
        JSONResponse with 403 status
    """
    return error_response(
        error=message,
        status_code=403,
        error_code="FORBIDDEN",
    )


def server_error_response(
    error: str = "Internal server error",
    error_code: str = "INTERNAL_ERROR",
    details: Optional[Metadata] = None,
) -> JSONResponse:
    """
    Build a standardized 500 Internal Server Error response.

    Args:
        error: Error message
        error_code: Error code
        details: Optional error details (for logging, not exposed to client in prod)

    Returns:
        JSONResponse with 500 status
    """
    return error_response(
        error=error,
        status_code=500,
        error_code=error_code,
        details=details,
    )


def service_unavailable_response(
    service: str = "Service",
    retry_after: Optional[int] = None,
) -> JSONResponse:
    """
    Build a standardized 503 Service Unavailable response.

    Args:
        service: Name of the unavailable service
        retry_after: Optional seconds to wait before retrying

    Returns:
        JSONResponse with 503 status
    """
    headers = {"Retry-After": str(retry_after)} if retry_after else None
    return error_response(
        error=f"{service} is temporarily unavailable",
        status_code=503,
        error_code="SERVICE_UNAVAILABLE",
        headers=headers,
    )
