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
from utils.cancel_tokens import begin_cancel_scope, end_cancel_scope, signal_cancel_scope

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

    # #13740: the exception's own type and message used to be interpolated into
    # `message` and repeated in `details`, so any unhandled failure reflected
    # internals verbatim to the caller. They are logged here — where the
    # exception is still in scope — against the same trace_id the client
    # receives, so a report of "trace_id X" still resolves to the real cause.
    logger.error(
        "Error in %s: %s: %s (trace_id: %s, code: %s)",
        func_operation,
        type(e).__name__,
        e,
        trace_id,
        error_code,
        exc_info=True,
    )

    return APIErrorResponse(
        category=category,
        message=APIErrorResponse.get_client_message_for_category(category),
        code=error_code,
        status_code=status_code,
        details={"operation": func_operation},
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

    Note:
        The diagnostic log is emitted by :func:`_create_api_error_response`,
        which still has the exception in scope (#13740). Logging
        ``error_response.message`` here would now record only the static,
        client-safe text and lose the cause.
    """
    raise HTTPException(status_code=error_response.status_code, detail=error_response.to_dict())


# #14015: the request-layer deadline.
#
# Before this, bounding was opt-in and per-call-site: every handler that wanted
# a limit hand-rolled `asyncio.wait_for`, with its own constant. `report.py`
# alone carried three different ones — and one analysis with none at all, which
# is #13602: the endpoint held the socket open past 180s and logged nothing,
# because the handler never ran.
#
# The problem is the pattern, not that one omission. When bounding is opt-in, an
# unbounded path is invisible — it looks exactly like every other handler until
# it hangs. So the deadline is a decorator that stacks with with_error_handling,
# and `tools/lint/check_route_deadlines.py` requires every covered route to
# carry one or to be listed as deliberately unbounded WITH A REASON. An
# unbounded route becomes a declaration rather than a default.
DEFAULT_ROUTE_DEADLINE_SECONDS = 60.0

# Margin a route-level deadline must clear above the largest internal budget
# reachable from that route. #14015 review: a blanket 60s outer bound sat BELOW
# pre-existing internal timeouts of 120s, 180s and 240s, which would have turned
# previously-slow-but-successful requests into guaranteed 504s. And on /report
# the outer bound was tighter than its own fan-out ceiling, so it would have won
# the race with a generic message where report.py's design says the inner
# deadline should win and name the analysis that ran long.
ROUTE_DEADLINE_GRACE = 15.0


def bounded(seconds: float = DEFAULT_ROUTE_DEADLINE_SECONDS, *, operation: str | None = None):
    """Bound an async route handler, returning a structured error on timeout.

    Wraps the handler in ``asyncio.wait_for``. On expiry the client gets a 504
    naming the endpoint and the limit, instead of a socket held open with
    nothing logged.

    Deliberately raises ``HTTPException`` rather than returning a response
    object: that is what ``with_error_handling`` already does on this stack, so
    a timeout and a failure surface through the same path.

    Args:
        seconds: Wall-clock limit. Must be positive — a zero or negative
            deadline would make ``wait_for`` expire immediately, turning every
            request into a 504, which is the kind of always-on failure that
            reads as a broken endpoint rather than a misconfiguration.
        operation: Name for the error payload and the log line. Defaults to the
            handler's own name, which is what an operator greps for.

    Raises:
        ValueError: at decoration time (import time) for a non-positive
            deadline, so the mistake surfaces at startup rather than on the
            first request.

    Issue #14256: opens a cancel scope for the duration of the call. Any
    pooled work the handler dispatches via
    ``utils.cancel_tokens.submit_cancellable``/``run_cancellable`` registers
    its cancel token here; on expiry (or on this call being cancelled from
    outside, e.g. graceful shutdown) every registered token is signalled
    before the 504/CancelledError propagates. The route deadline and the
    cancellation of the work it dispatched are therefore the same event
    rather than two facts that can drift (#14244).
    """
    if seconds <= 0:
        raise ValueError(f"bounded() needs a positive deadline, got {seconds!r}")

    def decorator(func: Callable) -> Callable:
        name = operation or getattr(func, "__name__", "unknown")

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            scope = begin_cancel_scope()
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=seconds)
            except asyncio.TimeoutError:
                # The one thing #13602 could not do: say something. A hang with
                # no output is indistinguishable from a slow network, a stuck
                # proxy or a dead process.
                logger.warning(
                    "Request deadline exceeded: %s did not complete within %.1fs (#14015)",
                    name,
                    seconds,
                )
                # #14256: the deadline stopping the CALLER is only half the fix --
                # signal every cancel token this call dispatched so pooled work
                # stops cooperatively instead of running to completion for a
                # result nobody reads (#14244).
                signal_cancel_scope(f"route deadline for {name} exceeded {seconds:.1f}s")
                raise HTTPException(
                    status_code=504,
                    detail={
                        "status": "error",
                        "error": "deadline_exceeded",
                        "operation": name,
                        "timeout_seconds": seconds,
                        "message": (
                            f"{name} did not complete within {seconds:.0f}s. The work may still be "
                            "running server-side; retry or narrow the request."
                        ),
                    },
                ) from None
            except asyncio.CancelledError:
                # Reachable via graceful shutdown or an outer deadline tighter
                # than this one -- same treatment as a timeout (#14256): signal,
                # then re-raise. Never swallowed.
                signal_cancel_scope(f"{name} was cancelled before its {seconds:.1f}s deadline")
                raise
            finally:
                end_cancel_scope(scope)

        wrapper.__route_deadline_seconds__ = seconds
        return wrapper

    return decorator


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

    Raises:
        TypeError: if used bare (``@with_error_handling`` with no parentheses).
            That form calls this factory with the decorated function as
            ``category``, which would otherwise silently hand back the inner
            ``decorator`` instead of a wrapped endpoint (#14191, and the bare
            usage #14186 had to fix by hand because nothing caught it).
    """
    if callable(category) and not isinstance(category, ErrorCategory):
        raise TypeError(
            "with_error_handling() must be called with parentheses: "
            "use @with_error_handling() or @with_error_handling(category=...), "
            "not bare @with_error_handling."
        )

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
