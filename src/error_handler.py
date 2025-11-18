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
import time
import traceback
from contextlib import contextmanager
from typing import Any, Callable, Optional, Type, TypeVar

from src.constants.network_constants import NetworkConstants
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
        logger.critical(f"Unexpected {log_msg}", exc_info=True)


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
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
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
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        if on_retry:
                            on_retry(e, attempt + 1)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_attempts} for "
                            f"{func.__name__} after {type(e).__name__}: {e}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Max retries ({max_attempts}) exceeded for "
                            f"{func.__name__}"
                        )

            raise last_exception

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        if on_retry:
                            on_retry(e, attempt + 1)
                        logger.warning(
                            f"Retry {attempt + 1}/{max_attempts} for "
                            f"{func.__name__} after {type(e).__name__}: {e}"
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
                    else:
                        logger.error(
                            f"Max retries ({max_attempts}) exceeded for "
                            f"{func.__name__}"
                        )

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
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self._state = "closed"  # closed, open, half-open

    @property
    def state(self) -> str:
        if self._state == "open":
            if (
                self.last_failure_time
                and time.time() - self.last_failure_time >= self.recovery_timeout
            ):
                self._state = "half-open"
        return self._state

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            if self.state == "open":
                raise InternalError(f"Circuit breaker is open for {func.__name__}")

            try:
                result = func(*args, **kwargs)
                if self.state == "half-open":
                    self._state = "closed"
                    self.failure_count = 0
                    logger.info(f"Circuit breaker closed for {func.__name__}")
                return result
            except self.expected_exception:
                self._handle_failure(func.__name__)
                raise

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            if self.state == "open":
                raise InternalError(f"Circuit breaker is open for {func.__name__}")

            try:
                result = await func(*args, **kwargs)
                if self.state == "half-open":
                    self._state = "closed"
                    self.failure_count = 0
                    logger.info(f"Circuit breaker closed for {func.__name__}")
                return result
            except self.expected_exception:
                self._handle_failure(func.__name__)
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    def _handle_failure(self, func_name: str):
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


def safe_api_error(error: Exception, request_id: Optional[str] = None) -> dict:
    """
    Convert an exception to a safe API error response.

    Args:
        error: The exception to convert
        request_id: Optional request ID for tracking

    Returns:
        Dictionary safe for API response
    """
    if isinstance(error, AutoBotError):
        response = {"error": error.safe_message, "error_type": type(error).__name__}
        # Include specific fields for certain error types
        if hasattr(error, "field") and error.field:
            response["field"] = error.field
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
@CircuitBreaker(failure_threshold=5, recovery_timeout=60)
def unstable_service_call():
    # After 5 failures, circuit opens for 60 seconds
    return external_service.call()

# Using error context
with error_context("processing user request"):
    process_request()
    # Any exceptions will be logged with context
"""
