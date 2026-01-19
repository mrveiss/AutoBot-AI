#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Retry mechanism with exponential backoff for AutoBot
Handles transient failures in network requests, database operations, and external service calls
"""

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, Optional

from src.constants.threshold_constants import (
    RetryConfig as ThresholdRetryConfig,
    TimingConstants,
)

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategy types"""

    EXPONENTIAL_BACKOFF = "exponential_backof"
    LINEAR_BACKOFF = "linear_backof"
    FIXED_DELAY = "fixed_delay"
    JITTERED_BACKOFF = "jittered_backof"


@dataclass
class RetryConfig:
    """Configuration for retry mechanism (Issue #376 - use named constants)"""

    max_attempts: int = ThresholdRetryConfig.DEFAULT_RETRIES
    base_delay: float = TimingConstants.STANDARD_DELAY  # seconds
    max_delay: float = ThresholdRetryConfig.BACKOFF_MAX_DELAY  # seconds
    backoff_multiplier: float = ThresholdRetryConfig.BACKOFF_BASE
    jitter: bool = True
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF

    # Exceptions that should trigger a retry
    retryable_exceptions: tuple = (
        ConnectionError,
        TimeoutError,
        OSError,
        # Add database-specific exceptions
        Exception,  # Temporary - should be more specific
    )

    # Exceptions that should never be retried
    non_retryable_exceptions: tuple = (
        KeyboardInterrupt,
        SystemExit,
        MemoryError,
        SyntaxError,
        TypeError,
        ValueError,  # Usually indicates bad input, not transient failure
    )


class RetryExhaustedError(Exception):
    """Raised when all retry attempts have been exhausted"""

    def __init__(self, attempts: int, last_exception: Exception):
        """Initialize with number of attempts and the last exception raised."""
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"Retry exhausted after {attempts} attempts. "
            f"Last error: {type(last_exception).__name__}: {last_exception}"
        )


class RetryMechanism:
    """Retry mechanism with various backoff strategies"""

    def __init__(self, config: Optional[RetryConfig] = None):
        """Initialize retry mechanism with optional configuration."""
        self.config = config or RetryConfig()
        self._stats_lock = threading.Lock()
        self.stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_operations": 0,
            "operations_by_type": {},
        }

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for the given attempt number"""
        if self.config.strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.config.base_delay * (
                self.config.backoff_multiplier ** (attempt - 1)
            )
        elif self.config.strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.config.base_delay * attempt
        elif self.config.strategy == RetryStrategy.FIXED_DELAY:
            delay = self.config.base_delay
        elif self.config.strategy == RetryStrategy.JITTERED_BACKOFF:
            delay = self.config.base_delay * (
                self.config.backoff_multiplier ** (attempt - 1)
            )
            # Add random jitter ±20%
            jitter_factor = 1.0 + (random.random() - 0.5) * 0.4
            delay *= jitter_factor
        else:
            delay = self.config.base_delay

        # Apply jitter if enabled and not using jittered backoff
        if (
            self.config.jitter
            and self.config.strategy != RetryStrategy.JITTERED_BACKOFF
        ):
            jitter_factor = 1.0 + (random.random() - 0.5) * 0.2
            delay *= jitter_factor

        # Ensure delay doesn't exceed maximum
        return min(delay, self.config.max_delay)

    def is_retryable_exception(self, exception: Exception) -> bool:
        """Check if an exception should trigger a retry"""
        # Non-retryable exceptions take precedence
        if isinstance(exception, self.config.non_retryable_exceptions):
            return False

        # Check if it's a retryable exception
        return isinstance(exception, self.config.retryable_exceptions)

    def _update_stats_attempt(self):
        """Thread-safe increment of total attempts."""
        with self._stats_lock:
            self.stats["total_attempts"] += 1

    def _update_stats_success(self, operation_name: str, attempt: int):
        """Thread-safe update of success stats."""
        with self._stats_lock:
            if attempt > 1:
                self.stats["successful_retries"] += 1

            if operation_name not in self.stats["operations_by_type"]:
                self.stats["operations_by_type"][operation_name] = {
                    "total": 0,
                    "succeeded": 0,
                    "retries_needed": 0,
                }

            self.stats["operations_by_type"][operation_name]["total"] += 1
            self.stats["operations_by_type"][operation_name]["succeeded"] += 1
            if attempt > 1:
                self.stats["operations_by_type"][operation_name]["retries_needed"] += 1

    def _update_stats_failure(self, operation_name: str):
        """Thread-safe update of failure stats."""
        with self._stats_lock:
            self.stats["failed_operations"] += 1

            if operation_name not in self.stats["operations_by_type"]:
                self.stats["operations_by_type"][operation_name] = {
                    "total": 0,
                    "succeeded": 0,
                    "retries_needed": 0,
                }

            self.stats["operations_by_type"][operation_name]["total"] += 1

    async def execute_async(
        self, func: Callable, *args, operation_name: str = None, **kwargs
    ) -> Any:
        """Execute an async function with retry mechanism (thread-safe)"""
        operation_name = operation_name or func.__name__
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            self._update_stats_attempt()

            try:
                logger.debug(
                    f"Executing {operation_name}, attempt {attempt}/{self.config.max_attempts}"
                )

                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)

                # Success!
                if attempt > 1:
                    logger.info("%s succeeded on attempt %s", operation_name, attempt)

                # Update operation stats (thread-safe)
                self._update_stats_success(operation_name, attempt)

                return result

            except Exception as e:
                last_exception = e

                logger.debug(
                    f"{operation_name} failed on attempt {attempt}: {type(e).__name__}: {e}"
                )

                # Check if we should retry this exception
                if not self.is_retryable_exception(e):
                    logger.warning(
                        f"{operation_name} failed with non-retryable exception: {type(e).__name__}"
                    )
                    raise e

                # If this was the last attempt, don't delay
                if attempt == self.config.max_attempts:
                    break

                # Calculate delay and wait
                delay = self.calculate_delay(attempt)
                logger.debug("Retrying %s in %.2f seconds...", operation_name, delay)
                await asyncio.sleep(delay)

        # All attempts exhausted - update stats (thread-safe)
        self._update_stats_failure(operation_name)

        logger.error(
            f"{operation_name} failed after {self.config.max_attempts} attempts"
        )
        raise RetryExhaustedError(self.config.max_attempts, last_exception)

    def execute_sync(
        self, func: Callable, *args, operation_name: str = None, **kwargs
    ) -> Any:
        """Execute a synchronous function with retry mechanism (thread-safe)"""
        operation_name = operation_name or func.__name__
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            self._update_stats_attempt()

            try:
                logger.debug(
                    f"Executing {operation_name}, attempt {attempt}/{self.config.max_attempts}"
                )

                result = func(*args, **kwargs)

                # Success!
                if attempt > 1:
                    logger.info("%s succeeded on attempt %s", operation_name, attempt)

                # Update operation stats (thread-safe)
                self._update_stats_success(operation_name, attempt)

                return result

            except Exception as e:
                last_exception = e

                logger.debug(
                    f"{operation_name} failed on attempt {attempt}: {type(e).__name__}: {e}"
                )

                # Check if we should retry this exception
                if not self.is_retryable_exception(e):
                    logger.warning(
                        f"{operation_name} failed with non-retryable exception: {type(e).__name__}"
                    )
                    raise e

                # If this was the last attempt, don't delay
                if attempt == self.config.max_attempts:
                    break

                # Calculate delay and wait
                delay = self.calculate_delay(attempt)
                logger.debug("Retrying %s in %.2f seconds...", operation_name, delay)
                time.sleep(delay)

        # All attempts exhausted - update stats (thread-safe)
        self._update_stats_failure(operation_name)

        logger.error(
            f"{operation_name} failed after {self.config.max_attempts} attempts"
        )
        raise RetryExhaustedError(self.config.max_attempts, last_exception)

    def get_stats(self) -> Dict[str, Any]:
        """Get retry mechanism statistics (thread-safe)"""
        with self._stats_lock:
            stats_copy = dict(self.stats)
            stats_copy["operations_by_type"] = dict(self.stats["operations_by_type"])
            total = stats_copy["total_attempts"]
            failed = stats_copy["failed_operations"]

        return {
            **stats_copy,
            "success_rate": ((total - failed) / max(1, total)) * 100,
        }

    def reset_stats(self):
        """Reset retry statistics (thread-safe)"""
        with self._stats_lock:
            self.stats = {
                "total_attempts": 0,
                "successful_retries": 0,
                "failed_operations": 0,
                "operations_by_type": {},
            }


# Global retry mechanism instance
default_retry_mechanism = RetryMechanism()


def retry_async(
    max_attempts: int = ThresholdRetryConfig.DEFAULT_RETRIES,
    base_delay: float = TimingConstants.STANDARD_DELAY,
    max_delay: float = ThresholdRetryConfig.BACKOFF_MAX_DELAY,
    backoff_multiplier: float = ThresholdRetryConfig.BACKOFF_BASE,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
    retryable_exceptions: tuple = None,
    operation_name: str = None,
):
    """
    Decorator for async functions with retry mechanism

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        backoff_multiplier: Multiplier for exponential backoff
        strategy: Retry strategy to use
        retryable_exceptions: Tuple of exceptions that should trigger retry
        operation_name: Name for logging and stats (defaults to function name)
    """

    def decorator(func):
        """Inner decorator that wraps function with async retry logic."""

        @wraps(func)
        async def wrapper(*args, **kwargs):
            """Async wrapper that executes function with retry mechanism."""
            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff_multiplier=backoff_multiplier,
                strategy=strategy,
            )

            if retryable_exceptions:
                config.retryable_exceptions = retryable_exceptions

            retry_mechanism = RetryMechanism(config)

            return await retry_mechanism.execute_async(
                func, *args, operation_name=operation_name or func.__name__, **kwargs
            )

        return wrapper

    return decorator


def retry_sync(
    max_attempts: int = ThresholdRetryConfig.DEFAULT_RETRIES,
    base_delay: float = TimingConstants.STANDARD_DELAY,
    max_delay: float = ThresholdRetryConfig.BACKOFF_MAX_DELAY,
    backoff_multiplier: float = ThresholdRetryConfig.BACKOFF_BASE,
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
    retryable_exceptions: tuple = None,
    operation_name: str = None,
):
    """
    Decorator for synchronous functions with retry mechanism

    Args:
        max_attempts: Maximum number of retry attempts
        base_delay: Base delay in seconds
        max_delay: Maximum delay in seconds
        backoff_multiplier: Multiplier for exponential backoff
        strategy: Retry strategy to use
        retryable_exceptions: Tuple of exceptions that should trigger retry
        operation_name: Name for logging and stats (defaults to function name)
    """

    def decorator(func):
        """Inner decorator that wraps function with sync retry logic."""

        @wraps(func)
        def wrapper(*args, **kwargs):
            """Sync wrapper that executes function with retry mechanism."""
            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                backoff_multiplier=backoff_multiplier,
                strategy=strategy,
            )

            if retryable_exceptions:
                config.retryable_exceptions = retryable_exceptions

            retry_mechanism = RetryMechanism(config)

            return retry_mechanism.execute_sync(
                func, *args, operation_name=operation_name or func.__name__, **kwargs
            )

        return wrapper

    return decorator


# Convenience functions for common use cases
async def retry_database_operation(func: Callable, *args, **kwargs) -> Any:
    """Retry database operations with database-specific configuration"""
    import sqlite3

    # Database operations use faster retries with shorter delays
    config = RetryConfig(
        max_attempts=ThresholdRetryConfig.DEFAULT_RETRIES,
        base_delay=TimingConstants.SHORT_DELAY,
        max_delay=TimingConstants.MEDIUM_DELAY,
        strategy=RetryStrategy.JITTERED_BACKOFF,
        retryable_exceptions=(
            sqlite3.OperationalError,
            sqlite3.DatabaseError,
            ConnectionError,
            TimeoutError,
        ),
    )

    retry_mechanism = RetryMechanism(config)
    return await retry_mechanism.execute_async(func, *args, **kwargs)


async def retry_network_operation(func: Callable, *args, **kwargs) -> Any:
    """Retry network operations with network-specific configuration"""
    import aiohttp

    # Network operations use moderate delays, capped to prevent long waits
    config = RetryConfig(
        max_attempts=ThresholdRetryConfig.DEFAULT_RETRIES,
        base_delay=TimingConstants.SHORT_DELAY,
        max_delay=TimingConstants.LONG_DELAY,  # 10s max - reduced from 30s for responsiveness
        strategy=RetryStrategy.EXPONENTIAL_BACKOFF,
        retryable_exceptions=(
            aiohttp.ClientError,
            aiohttp.ServerTimeoutError,
            ConnectionError,
            TimeoutError,
            OSError,
        ),
    )

    retry_mechanism = RetryMechanism(config)
    return await retry_mechanism.execute_async(func, *args, **kwargs)


async def retry_file_operation(func: Callable, *args, **kwargs) -> Any:
    """Retry file operations with file-specific configuration"""
    # File operations use very short delays - usually file locks are brief
    config = RetryConfig(
        max_attempts=ThresholdRetryConfig.DEFAULT_RETRIES,
        base_delay=TimingConstants.MICRO_DELAY,
        max_delay=TimingConstants.STANDARD_DELAY * 2,  # 2s max for file ops
        strategy=RetryStrategy.LINEAR_BACKOFF,
        retryable_exceptions=(
            OSError,
            IOError,
            PermissionError,  # Might be temporary
        ),
        non_retryable_exceptions=(
            FileNotFoundError,  # File doesn't exist, retry won't help
            IsADirectoryError,
        ),
    )

    retry_mechanism = RetryMechanism(config)
    return await retry_mechanism.execute_async(func, *args, **kwargs)


if __name__ == "__main__":
    # Example usage and testing
    async def example_usage():
        """Example usage of the retry mechanism"""

        # Example 1: Using decorator
        @retry_async(max_attempts=3, base_delay=0.5)
        async def flaky_network_call():
            """Example flaky network call that may fail randomly."""
            import random

            if random.random() < 0.7:  # 70% chance of failure
                raise ConnectionError("Network error")
            return "Success!"

        try:
            result = await flaky_network_call()
            logger.info("Network call result: {result}")
        except RetryExhaustedError as e:
            logger.info("Network call failed: {e}")

        # Example 2: Using retry mechanism directly
        retry_mechanism = RetryMechanism(
            RetryConfig(max_attempts=3, strategy=RetryStrategy.JITTERED_BACKOFF)
        )

        async def another_flaky_operation():
            """Example operation that may timeout randomly."""
            import random

            if random.random() < 0.5:
                raise TimeoutError("Operation timed out")
            return "Operation completed"

        try:
            result = await retry_mechanism.execute_async(
                another_flaky_operation, operation_name="flaky_operation"
            )
            logger.info("Operation result: {result}")
        except RetryExhaustedError as e:
            logger.info("Operation failed: {e}")

        # Print statistics
        logger.info("Retry statistics:", retry_mechanism.get_stats())

    # Run example
    asyncio.run(example_usage())
