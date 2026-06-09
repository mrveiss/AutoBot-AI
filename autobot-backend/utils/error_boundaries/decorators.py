# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Error Boundary Decorators Module

Issue #381: Extracted from error_boundaries.py god class refactoring.
Contains decorators for function-level error boundaries and API error handling.
"""

import asyncio
import functools
import time
from typing import Callable

from fastapi import HTTPException

from autobot_shared.async_compat import run_or_schedule
from autobot_shared.logging_manager import get_logger
from constants.threshold_constants import RetryConfig, exponential_backoff_delay

from .boundary_manager import get_error_boundary_manager
from .types import APIErrorResponse, ErrorCategory, ErrorContext, RecoveryStrategy

logger = get_logger(__name__)


async def _handle_async_attempt(
    func: Callable,
    args: tuple,
    kwargs: dict,
    attempt: int,
    max_retries: int,
    recovery_strategy: RecoveryStrategy,
    manager,
    context: ErrorContext,
) -> tuple:
    """
    Handle single async retry attempt.

    Args:
        func: Async function to call
        args: Positional arguments
        kwargs: Keyword arguments
        attempt: Current attempt number
        max_retries: Maximum retry attempts
        recovery_strategy: Recovery strategy to use
        manager: Error boundary manager instance
        context: Error context

    Returns:
        Tuple of (success: bool, result: Any)
    """
    try:
        result = await func(*args, **kwargs)
        return (True, result)
    except Exception as e:
        if attempt == max_retries:
            return (True, await manager.handle_error(e, context))
        if recovery_strategy == RecoveryStrategy.RETRY:
            await asyncio.sleep(exponential_backoff_delay(attempt))
            return (False, None)
        return (True, await manager.handle_error(e, context))


def _handle_sync_attempt(
    func: Callable,
    args: tuple,
    kwargs: dict,
    attempt: int,
    max_retries: int,
    recovery_strategy: RecoveryStrategy,
    manager,
    context: ErrorContext,
) -> tuple:
    """
    Handle single sync retry attempt.

    Args:
        func: Sync function to call
        args: Positional arguments
        kwargs: Keyword arguments
        attempt: Current attempt number
        max_retries: Maximum retry attempts
        recovery_strategy: Recovery strategy to use
        manager: Error boundary manager instance
        context: Error context

    Returns:
        Tuple of (success: bool, result: Any)
    """
    try:
        result = func(*args, **kwargs)
        return (True, result)
    except Exception as e:
        if attempt == max_retries:
            # #7469: defensive sync/async-context handler. Bare asyncio.run()
            # crashes when this sync wrapper is dispatched from a running
            # event loop (e.g. via loop.run_in_executor with shared thread).
            return (True, run_or_schedule(manager.handle_error(e, context)))
        if recovery_strategy == RecoveryStrategy.RETRY:
            time.sleep(exponential_backoff_delay(attempt))
            return (False, None)
        # #7469: same defensive pattern as the max-retries branch above.
        return (True, run_or_schedule(manager.handle_error(e, context)))


def _create_async_boundary_wrapper(
    func: Callable,
    comp_name: str,
    func_name: str,
    recovery_strategy: RecoveryStrategy,
    max_retries: int,
) -> Callable:
    """
    Create async wrapper for error boundary decorator. Issue #620.

    Args:
        func: Async function to wrap
        comp_name: Component name for error context
        func_name: Function name for error context
        recovery_strategy: Recovery strategy to use
        max_retries: Maximum retry attempts

    Returns:
        Async wrapper function with error boundary protection
    """

    @functools.wraps(func)
    async def async_wrapper(*args, **kwargs):
        """Async wrapper that executes function with error boundary protection."""
        manager = get_error_boundary_manager()
        context = ErrorContext(component=comp_name, function=func_name, args=args, kwargs=kwargs)

        for attempt in range(max_retries + 1):
            done, result = await _handle_async_attempt(
                func,
                args,
                kwargs,
                attempt,
                max_retries,
                recovery_strategy,
                manager,
                context,
            )
            if done:
                return result

    return async_wrapper


def _create_sync_boundary_wrapper(
    func: Callable,
    comp_name: str,
    func_name: str,
    recovery_strategy: RecoveryStrategy,
    max_retries: int,
) -> Callable:
    """
    Create sync wrapper for error boundary decorator. Issue #620.

    Args:
        func: Sync function to wrap
        comp_name: Component name for error context
        func_name: Function name for error context
        recovery_strategy: Recovery strategy to use
        max_retries: Maximum retry attempts

    Returns:
        Sync wrapper function with error boundary protection
    """

    @functools.wraps(func)
    def sync_wrapper(*args, **kwargs):
        """Sync wrapper that executes function with error boundary protection."""
        manager = get_error_boundary_manager()
        context = ErrorContext(component=comp_name, function=func_name, args=args, kwargs=kwargs)

        for attempt in range(max_retries + 1):
            done, result = _handle_sync_attempt(
                func,
                args,
                kwargs,
                attempt,
                max_retries,
                recovery_strategy,
                manager,
                context,
            )
            if done:
                return result

    return sync_wrapper


def error_boundary(
    component: str = None,
    function: str = None,
    recovery_strategy: RecoveryStrategy = RecoveryStrategy.RETRY,
    max_retries: int = RetryConfig.DEFAULT_RETRIES,
):
    """
    Decorator for function-level error boundaries.

    Args:
        component: Component name (default: function module)
        function: Function name (default: function name)
        recovery_strategy: Recovery strategy to use (default: RETRY)
        max_retries: Maximum retry attempts (default: 3)

    Returns:
        Decorated function with error boundary
    """

    def decorator(func):
        """Inner decorator that wraps the target function with error handling."""
        comp_name = component or func.__module__
        func_name = function or func.__name__

        if asyncio.iscoroutinefunction(func):
            return _create_async_boundary_wrapper(func, comp_name, func_name, recovery_strategy, max_retries)
        else:
            return _create_sync_boundary_wrapper(func, comp_name, func_name, recovery_strategy, max_retries)

    return decorator


def _create_api_error_response(
    e: Exception,
    category: ErrorCategory,
    func_operation: str,
    error_code_prefix: str,
) -> APIErrorResponse:
    """
    Create API error response from exception.

    Args:
        e: Exception that occurred
        category: Error category
        func_operation: Operation name
        error_code_prefix: Error code prefix

    Returns:
        APIErrorResponse object
    """
    trace_id = f"{func_operation}_{int(time.time() * 1000)}"
    error_code = f"{error_code_prefix}_{abs(hash(type(e).__name__)) % 10000:04d}"
    status_code = APIErrorResponse.get_status_code_for_category(category)

    exc_type = type(e).__name__
    exc_msg = str(e)
    message = (
        f"Operation failed ({func_operation}): {exc_type}: {exc_msg}"
        if exc_msg
        else f"Operation failed ({func_operation}): {exc_type}"
    )

    return APIErrorResponse(
        category=category,
        message=message,
        code=error_code,
        status_code=status_code,
        details={"operation": func_operation, "exception_type": exc_type, "exception_message": exc_msg},
        trace_id=trace_id,
    )


def _raise_or_return_error(error_response: APIErrorResponse):
    """
    Raise HTTPException or return error dict.

    Args:
        error_response: API error response object

    Raises:
        HTTPException if FastAPI is available

    Returns:
        Error dictionary if FastAPI not available
    """
    logger.error(
        "Error in %s: %s (trace_id: %s, code: %s)",
        error_response.details.get("operation", "unknown"),
        error_response.message,
        error_response.trace_id,
        error_response.code,
    )
    raise HTTPException(status_code=error_response.status_code, detail=error_response.to_dict())


def with_error_handling(
    category: ErrorCategory = ErrorCategory.SERVER_ERROR,
    operation: str = None,
    error_code_prefix: str = "API",
):
    """
    Simplified decorator for API endpoints with automatic HTTP error conversion.

    Usage:
        @with_error_handling(
            category=ErrorCategory.VALIDATION,
            operation="validate_user_input"
        )
        async def create_user(user_data: dict):
            # Implementation
            pass

    Args:
        category: Error category (determines HTTP status code)
        operation: Operation name for logging/tracing
        error_code_prefix: Prefix for error codes (e.g., "KB", "AUTH")

    Returns:
        Decorated function with error handling
    """

    def decorator(func):
        """Inner decorator that wraps function with API error handling."""
        func_operation = operation or func.__name__

        if asyncio.iscoroutinefunction(func):

            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                """Async wrapper that catches exceptions and converts to API errors."""
                try:
                    return await func(*args, **kwargs)
                except HTTPException:
                    raise  # Preserve intentional HTTP status codes
                except Exception as e:
                    error_response = _create_api_error_response(e, category, func_operation, error_code_prefix)
                    return _raise_or_return_error(error_response)

            return async_wrapper
        else:

            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                """Sync wrapper that catches exceptions and converts to API errors."""
                try:
                    return func(*args, **kwargs)
                except HTTPException:
                    raise  # Preserve intentional HTTP status codes
                except Exception as e:
                    error_response = _create_api_error_response(e, category, func_operation, error_code_prefix)
                    return _raise_or_return_error(error_response)

            return sync_wrapper

    return decorator


def with_error_boundary(component: str, function: str):
    """
    Context manager for error boundaries.

    Args:
        component: Component name
        function: Function name

    Returns:
        Error boundary context manager
    """
    return get_error_boundary_manager().error_boundary(component, function)


async def with_async_error_boundary(component: str, function: str):
    """
    Async context manager for error boundaries.

    Args:
        component: Component name
        function: Function name

    Returns:
        Async error boundary context manager
    """
    return get_error_boundary_manager().async_error_boundary(component, function)


def get_error_statistics():
    """
    Get system error statistics.

    Returns:
        Dictionary with error statistics
    """
    return get_error_boundary_manager().get_error_statistics()
