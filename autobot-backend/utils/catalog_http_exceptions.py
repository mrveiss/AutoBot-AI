# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Catalog-based HTTP Exception Helpers

Provides convenience functions for raising HTTPExceptions using the error catalog
Makes migration from hardcoded errors to catalog-based errors straightforward
"""

from fastapi import HTTPException, status

from autobot_shared.logging_manager import get_logger
from utils.error_catalog import get_error

logger = get_logger(__name__)


def raise_catalog_error(
    error_code: str,
    additional_context: str | None = None,
    override_status_code: int | None = None,
) -> None:
    """
    Raise HTTPException using error catalog

    Args:
        error_code: Error code from catalog (e.g., "KB_0001")
        additional_context: Additional context to append to error message
        override_status_code: Override catalog status code if needed

    Raises:
        HTTPException: With catalog message and status code

    Example:
        raise_catalog_error("KB_0001")
        raise_catalog_error("AUTH_0002", additional_context="Token expired")
        raise_catalog_error("API_0003", additional_context=str(e))
    """
    error = get_error(error_code)

    if error is None:
        logger.error("Unknown error code: %s", error_code)
        raise HTTPException(
            status_code=500,
            detail=f"Internal error (invalid error code: {error_code})",
        )

    # Build error message
    message = error.message
    if additional_context:
        message = f"{message}: {additional_context}"

    # Get status code
    status_code = override_status_code if override_status_code else error.status_code

    # Build error response with metadata
    detail = {
        "message": message,
        "code": error_code,
        "category": error.category.value,
        "retry": error.retry,
    }

    if error.retry and error.retry_after:
        detail["retry_after"] = error.retry_after

    if error.details:
        detail["details"] = error.details

    raise HTTPException(status_code=status_code, detail=detail)


def raise_catalog_error_simple(error_code: str, additional_context: str | None = None) -> None:
    """
    Raise HTTPException with simple string detail (backward compatible)

    Args:
        error_code: Error code from catalog
        additional_context: Additional context to append

    Raises:
        HTTPException: With string detail

    Example:
        raise_catalog_error_simple("AUTH_0001")
        raise_catalog_error_simple("KB_0004", "Vector search timeout")
    """
    error = get_error(error_code)

    if error is None:
        logger.error("Unknown error code: %s", error_code)
        raise HTTPException(status_code=500, detail="Internal error")

    message = error.message
    if additional_context:
        message = f"{message}: {additional_context}"

    raise HTTPException(status_code=error.status_code, detail=message)


def get_catalog_http_exception(
    error_code: str,
    additional_context: str | None = None,
    override_status_code: int | None = None,
) -> HTTPException:
    """
    Create HTTPException from catalog without raising

    Useful for conditional error handling or exception chaining

    Args:
        error_code: Error code from catalog
        additional_context: Additional context
        override_status_code: Override status code

    Returns:
        HTTPException instance

    Example:
        exc = get_catalog_http_exception("LLM_0001")
        if should_raise:
            raise exc
    """
    error = get_error(error_code)

    if error is None:
        logger.error("Unknown error code: %s", error_code)
        return HTTPException(status_code=500, detail="Internal error")

    message = error.message
    if additional_context:
        message = f"{message}: {additional_context}"

    status_code = override_status_code if override_status_code else error.status_code

    return HTTPException(status_code=status_code, detail=message)


def catalog_error_response(
    error_code: str,
    additional_context: str | None = None,
    include_metadata: bool = True,
) -> dict:
    """
    Create error response dictionary from catalog

    Useful for manual error responses without raising HTTPException

    Args:
        error_code: Error code from catalog
        additional_context: Additional context
        include_metadata: Include retry/category metadata

    Returns:
        Error response dictionary

    Example:
        return JSONResponse(
            status_code=500,
            content=catalog_error_response("DB_0001", "Connection refused")
        )
    """
    error = get_error(error_code)

    if error is None:
        logger.error("Unknown error code: %s", error_code)
        return {"error": "Internal error", "code": "UNKNOWN"}

    response = {
        "error": error.message,
        "code": error_code,
    }

    if additional_context:
        response["error"] = f"{error.message}: {additional_context}"

    if include_metadata:
        response["category"] = error.category.value
        response["retry"] = error.retry
        if error.retry and error.retry_after:
            response["retry_after"] = error.retry_after
        if error.details:
            response["details"] = error.details

    return response


# Convenience functions for common error categories


def raise_auth_error(error_code: str = "AUTH_0002", context: str | None = None) -> None:
    """Raise authentication error"""
    raise_catalog_error_simple(error_code, context)


def raise_validation_error(error_code: str = "API_0001", context: str | None = None) -> None:
    """Raise validation error"""
    raise_catalog_error_simple(error_code, context)


def raise_server_error(error_code: str = "API_0003", context: str | None = None) -> None:
    """Raise internal server error"""
    raise_catalog_error_simple(error_code, context)


def raise_service_unavailable(error_code: str = "API_0005", context: str | None = None) -> None:
    """Raise service unavailable error"""
    raise_catalog_error_simple(error_code, context)


def raise_kb_error(error_code: str, context: str | None = None) -> None:
    """Raise knowledge base error"""
    raise_catalog_error_simple(error_code, context)


def raise_llm_error(error_code: str, context: str | None = None) -> None:
    """Raise LLM service error"""
    raise_catalog_error_simple(error_code, context)


def raise_db_error(error_code: str = "DB_0003", context: str | None = None) -> None:
    """Raise database error"""
    raise_catalog_error_simple(error_code, context)


# Direct raise helpers for common HTTP error patterns


def raise_not_found(resource_type: str, resource_id: str | None = None) -> None:
    """
    Raise 404 HTTPException for a missing resource.

    Args:
        resource_type: Human-readable resource name (e.g. "Worker", "File")
        resource_id: Optional identifier appended to the detail message

    Raises:
        HTTPException: 404 with detail "<resource_type> not found[: <resource_id>]"

    Example:
        raise_not_found("Worker", worker_id)
        raise_not_found("File")
    """
    detail = f"{resource_type} not found"
    if resource_id is not None:
        detail += f": {resource_id}"
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)


def raise_rate_limit(retry_after: int | None = None) -> None:
    """
    Raise 429 HTTPException for rate limit violations.

    Args:
        retry_after: Optional seconds until the client may retry (sets Retry-After header)

    Raises:
        HTTPException: 429 with detail "Rate limit exceeded"

    Example:
        raise_rate_limit()
        raise_rate_limit(retry_after=60)
    """
    headers = {"Retry-After": str(retry_after)} if retry_after is not None else None
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
        headers=headers,
    )


def raise_invalid_input(field: str, reason: str = "invalid value") -> None:
    """
    Raise 400 HTTPException for invalid request input.

    Args:
        field: The field or parameter that is invalid
        reason: Human-readable reason (default "invalid value")

    Raises:
        HTTPException: 400 with detail "<field>: <reason>"

    Example:
        raise_invalid_input("log_level", "must be one of: DEBUG, INFO, WARNING, ERROR")
        raise_invalid_input("filename", "unsafe characters")
    """
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"{field}: {reason}",
    )


def raise_internal_error(context: str = "") -> None:
    """
    Raise 500 HTTPException for unexpected internal errors.

    Args:
        context: Optional short description of what failed

    Raises:
        HTTPException: 500 with detail "Internal server error[: <context>]"

    Example:
        raise_internal_error("Failed to retrieve workers")
        raise_internal_error()
    """
    detail = f"Internal server error: {context}" if context else "Internal server error"
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail)


# Migration helpers for backward compatibility


def migrate_http_exception(
    original_status_code: int,
    original_detail: str,
    suggested_error_code: str,
    additional_context: str | None = None,
) -> None:
    """
    Helper for migrating existing HTTPException calls

    Before:
        raise HTTPException(status_code=500, detail="Database error")

    After:
        migrate_http_exception(500, "Database error", "DB_0003")

    Eventually:
        raise_catalog_error_simple("DB_0003")

    Args:
        original_status_code: Original HTTP status code
        original_detail: Original error message
        suggested_error_code: Suggested catalog error code
        additional_context: Additional context
    """
    # Log migration suggestion
    logger.debug(f"Migrating HTTPException: {original_status_code} - {original_detail} " f"-> {suggested_error_code}")

    # Use catalog error
    raise_catalog_error_simple(suggested_error_code, additional_context)
