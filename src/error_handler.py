# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Handling Utilities for AutoBot

This module provides utilities for consistent error handling,
including logging, retry mechanisms, and error recovery strategies.
"""

import asyncio
import functools
import logging
import threading
import time
import traceback
from contextlib import contextmanager
from typing import (
    Any,
    Callable,
    Optional,
    Type,
    TypeVar,
)

from src.constants.threshold_constants import TimingConstants
from src.exceptions import AutoBotError, InternalError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def log_error(
    error: Exception, context: Optional[str] = None, include_traceback: bool = True
) -> None:
    """
    Log an error with appropriate context and detail level.

    Args:
        error: The exception to log
        context: Additional context about where the error occurred
        include_traceback: Whether to include full traceback
    """
    error_type = type(error).__name__
    error_msg = str(error)

    log_msg = f"{error_type}: {error_msg}"
    if context:
        log_msg = f"[{context}] {log_msg}"

    if isinstance(error, AutoBotError):
        # Log our custom errors at appropriate levels
        if hasattr(error, "details") and error.details:
            log_msg += f" | Details: {error.details}"
        logger.error(log_msg, exc_info=include_traceback)
    else:
        # Log unexpected errors at critical level
        logger.critical("Unexpected %s", log_msg, exc_info=True)


def with_error_handling(
    default_return: Any = None,
    context: Optional[str] = None,
    reraise: bool = False,
    error_types: Optional[tuple] = None,
):
    """
    Decorator for consistent error handling.

    Args:
        default_return: Value to return on error
        context: Context string for logging
        reraise: Whether to re-raise the exception after handling
        error_types: Tuple of specific exception types to handle
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        """Inner decorator that wraps function with error handling."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            """Sync wrapper that catches and handles exceptions."""
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if error_types and not isinstance(e, error_types):
                    raise

                log_error(e, context or f"{func.__module__}.{func.__name__}")

                if reraise:
                    raise
                return default_return

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            """Async wrapper that catches and handles exceptions."""
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                if error_types and not isinstance(e, error_types):
                    raise

                log_error(e, context or f"{func.__module__}.{func.__name__}")

                if reraise:
                    raise
                return default_return

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# (Issue #315 - extracted) Helper function for retry logging and delay
def _handle_retry_attempt(
    exception: Exception,
    attempt: int,
    max_attempts: int,
    func_name: str,
    on_retry: Optional[Callable[[Exception, int], None]],
) -> None:
    """Handle logging and callback for retry attempt"""
    if on_retry:
        on_retry(exception, attempt + 1)
    logger.warning(
        f"Retry {attempt + 1}/{max_attempts} for "
        f"{func_name} after {type(exception).__name__}: {exception}"
    )


# (Issue #315 - extracted) Helper function for max retry logging
def _log_max_retries_exceeded(max_attempts: int, func_name: str) -> None:
    """Log when max retries are exceeded"""
    logger.error("Max retries (%s) exceeded for %s", max_attempts, func_name)


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
    on_retry: Optional[Callable[[Exception, int], None]] = None,
):
    """
    Decorator for retrying functions with exponential backoff.

    Args:
        max_attempts: Maximum number of retry attempts
        delay: Initial delay between retries in seconds
        backoff: Multiplier for delay after each retry
        exceptions: Tuple of exceptions to catch and retry
        on_retry: Optional callback called on each retry with (exception, attempt)
    """

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        """Inner decorator that wraps function with retry logic."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            """Sync wrapper that retries function on specified exceptions."""
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    # (Issue #315 - refactored) Use guard clause to reduce nesting
                    if attempt >= max_attempts - 1:
                        _log_max_retries_exceeded(max_attempts, func.__name__)
                        continue

                    _handle_retry_attempt(e, attempt, max_attempts, func.__name__, on_retry)
                    time.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            """Async wrapper that retries function on specified exceptions."""
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    # (Issue #315 - refactored) Use guard clause to reduce nesting
                    if attempt >= max_attempts - 1:
                        _log_max_retries_exceeded(max_attempts, func.__name__)
                        continue

                    _handle_retry_attempt(e, attempt, max_attempts, func.__name__, on_retry)
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


class CircuitBreaker:
    """
    Circuit breaker pattern for handling external service failures.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = TimingConstants.STANDARD_TIMEOUT,
        expected_exception: Type[Exception] = Exception,
    ):
        """Initialize circuit breaker with failure threshold and recovery settings."""
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self._state = "closed"  # closed, open, half-open
        self._lock = threading.Lock()  # Lock for thread-safe state access

    @property
    def state(self) -> str:
        """Get current circuit breaker state, auto-transitioning to half-open after timeout."""
        # (Issue #315 - refactored) Use guard clauses to reduce nesting
        if self._state != "open":
            return self._state

        if not self.last_failure_time:
            return self._state

        if time.time() - self.last_failure_time >= self.recovery_timeout:
            self._state = "half-open"

        return self._state

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """Decorate a function with circuit breaker protection."""

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            """Sync wrapper that enforces circuit breaker state before execution."""
            if self.state == "open":
                raise InternalError(f"Circuit breaker is open for {func.__name__}")

            try:
                result = func(*args, **kwargs)
                if self.state == "half-open":
                    with self._lock:
                        self._state = "closed"
                        self.failure_count = 0
                    logger.info("Circuit breaker closed for %s", func.__name__)
                return result
            except self.expected_exception:
                self._handle_failure(func.__name__)
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            """Async wrapper that enforces circuit breaker state before execution."""
            if self.state == "open":
                raise InternalError(f"Circuit breaker is open for {func.__name__}")

            try:
                result = await func(*args, **kwargs)
                if self.state == "half-open":
                    with self._lock:
                        self._state = "closed"
                        self.failure_count = 0
                    logger.info("Circuit breaker closed for %s", func.__name__)
                return result
            except self.expected_exception:
                self._handle_failure(func.__name__)
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    def _handle_failure(self, func_name: str):
        """Handle a failure by incrementing counter and potentially opening circuit (thread-safe)"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.failure_count >= self.failure_threshold:
                self._state = "open"
                logger.error(
                    f"Circuit breaker opened for {func_name} after "
                    f"{self.failure_count} failures"
                )


@contextmanager
def error_context(operation: str, reraise: bool = True):
    """
    Context manager for consistent error handling in code blocks.

    Usage:
        with error_context("database operation"):
            perform_database_operation()
    """
    try:
        yield
    except Exception as e:
        log_error(e, context=operation)
        if reraise:
            raise


# (Issue #315 - extracted) Helper function to build AutoBotError response
def _build_autobot_error_response(error: AutoBotError) -> dict:
    """Build response dictionary for AutoBotError"""
    response = {"error": error.safe_message, "error_type": type(error).__name__}
    # Include specific fields for certain error types
    if hasattr(error, "field") and error.field:
        response["field"] = error.field
    return response


def safe_api_error(error: Exception, request_id: Optional[str] = None) -> dict:
    """
    Convert an exception to a safe API error response.

    Args:
        error: The exception to convert
        request_id: Optional request ID for tracking

    Returns:
        Dictionary safe for API response
    """
    # (Issue #315 - refactored) Extract AutoBotError handling to reduce nesting
    if isinstance(error, AutoBotError):
        response = _build_autobot_error_response(error)
    else:
        # Never expose internal error details
        response = {
            "error": "An internal error occurred",
            "error_type": "InternalError",
        }

    if request_id:
        response["request_id"] = request_id

    return response


def format_traceback(exc: Exception, limit: int = 10) -> str:
    """
    Format exception traceback for logging.

    Args:
        exc: The exception
        limit: Maximum number of stack frames to include

    Returns:
        Formatted traceback string
    """
    tb_lines = traceback.format_exception(
        type(exc), exc, exc.__traceback__, limit=limit
    )
    return "".join(tb_lines)


# Example usage patterns
"""
# Using the error handling decorator
@with_error_handling(default_return=[], context="user data fetch")
def get_user_data(user_id: str) -> list:
    # This will log errors and return [] on failure
    return fetch_from_database(user_id)

# Using retry decorator
@retry(max_attempts=3, delay=1.0, exceptions=(ConnectionError, TimeoutError))
async def call_external_api():
    # This will retry up to 3 times with exponential backoff
    return await make_api_request()

# Using circuit breaker
@CircuitBreaker(failure_threshold=5, recovery_timeout=TimingConstants.STANDARD_TIMEOUT)
def unstable_service_call():
    # After 5 failures, circuit opens for 60 seconds
    return external_service.call()

# Using error context
with error_context("processing user request"):
    process_request()
    # Any exceptions will be logged with context
"""
