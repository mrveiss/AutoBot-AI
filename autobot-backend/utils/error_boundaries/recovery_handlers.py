# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Error Recovery Handlers Module

Issue #381: Extracted from error_boundaries.py god class refactoring.
Contains abstract base class and concrete recovery handler implementations.
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict

from backend.constants.threshold_constants import RetryConfig

from .types import ErrorContext

logger = logging.getLogger(__name__)


class ErrorRecoveryHandler(ABC):
    """Abstract base class for error recovery handlers"""

    @abstractmethod
    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        """
        Check if this handler can handle the given error.

        Args:
            error: Exception to check
            context: Error context

        Returns:
            True if handler can handle this error
        """

    @abstractmethod
    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        """
        Handle the error and return a recovery value or re-raise.

        Args:
            error: Exception to handle
            context: Error context

        Returns:
            Recovery value or raises exception
        """


class RetryRecoveryHandler(ErrorRecoveryHandler):
    """Recovery handler that implements retry logic"""

    def __init__(
        self,
        max_retries: int = RetryConfig.DEFAULT_RETRIES,
        backoff_factor: float = 1.5,
        retry_exceptions: tuple = (Exception,),
    ):
        """
        Initialize retry recovery handler.

        Args:
            max_retries: Maximum number of retry attempts (default: 3)
            backoff_factor: Backoff multiplier for delays (default: 1.5)
            retry_exceptions: Tuple of exception types to retry (default: Exception)
        """
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.retry_exceptions = retry_exceptions
        self._retry_counts: Dict[str, int] = {}

    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        """
        Check if error is in retryable exceptions list.

        Args:
            error: Exception to check
            context: Error context

        Returns:
            True if error type is retryable
        """
        return isinstance(error, self.retry_exceptions)

    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        """
        Handle error with retry logic.

        Args:
            error: Exception to handle
            context: Error context

        Raises:
            Exception if max retries exceeded or after delay for retry
        """
        retry_key = f"{context.component}.{context.function}"
        current_retries = self._retry_counts.get(retry_key, 0)

        if current_retries >= self.max_retries:
            logger.error(
                "Max retries (%d) exceeded for %s", self.max_retries, retry_key
            )
            raise error

        # Calculate backoff delay
        delay = self.backoff_factor**current_retries
        logger.warning(
            "Retrying %s in %.2fs (attempt %d/%d)",
            retry_key,
            delay,
            current_retries + 1,
            self.max_retries,
        )

        await asyncio.sleep(delay)
        self._retry_counts[retry_key] = current_retries + 1

        # Re-raise to trigger retry
        raise error


class FallbackRecoveryHandler(ErrorRecoveryHandler):
    """Recovery handler that provides fallback values"""

    def __init__(self, fallback_values: Dict[str, Any]):
        """
        Initialize fallback recovery handler.

        Args:
            fallback_values: Dictionary mapping function keys to fallback values
        """
        self.fallback_values = fallback_values

    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        """
        Check if fallback value exists for this function.

        Args:
            error: Exception to check
            context: Error context

        Returns:
            True if fallback value is configured for this function
        """
        fallback_key = f"{context.component}.{context.function}"
        return fallback_key in self.fallback_values

    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        """
        Return configured fallback value.

        Args:
            error: Exception that occurred
            context: Error context

        Returns:
            Configured fallback value for this function
        """
        fallback_key = f"{context.component}.{context.function}"
        fallback_value = self.fallback_values[fallback_key]

        logger.warning("Using fallback value for %s: %s", fallback_key, fallback_value)
        return fallback_value


class GracefulDegradationHandler(ErrorRecoveryHandler):
    """Handler for graceful service degradation"""

    def __init__(self, degraded_functions: Dict[str, Callable]):
        """
        Initialize graceful degradation handler.

        Args:
            degraded_functions: Dictionary mapping function keys to degraded implementations
        """
        self.degraded_functions = degraded_functions

    def can_handle(self, error: Exception, context: ErrorContext) -> bool:
        """
        Check if degraded function exists.

        Args:
            error: Exception to check
            context: Error context

        Returns:
            True if degraded function is configured for this function
        """
        degraded_key = f"{context.component}.{context.function}"
        return degraded_key in self.degraded_functions

    async def handle(self, error: Exception, context: ErrorContext) -> Any:
        """
        Call degraded version of function.

        Args:
            error: Exception that occurred
            context: Error context with original arguments

        Returns:
            Result from degraded function implementation
        """
        degraded_key = f"{context.component}.{context.function}"
        degraded_func = self.degraded_functions[degraded_key]

        logger.warning("Graceful degradation for %s", degraded_key)

        # Call degraded function with original arguments
        if asyncio.iscoroutinefunction(degraded_func):
            return await degraded_func(*context.args, **context.kwargs)
        else:
            return degraded_func(*context.args, **context.kwargs)
