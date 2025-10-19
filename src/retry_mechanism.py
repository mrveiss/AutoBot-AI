#!/usr/bin/env python3
"""
Retry mechanism with exponential backoff for AutoBot
Handles transient failures in network requests, database operations, and external service calls
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type, Union

from src.constants.network_constants import NetworkConstants

logger = logging.getLogger(__name__)


class RetryStrategy(Enum):
    """Retry strategy types"""

    EXPONENTIAL_BACKOFF = "exponential_backof"
    LINEAR_BACKOFF = "linear_backof"
    FIXED_DELAY = "fixed_delay"
    JITTERED_BACKOFF = "jittered_backof"


@dataclass
class RetryConfig:
    """Configuration for retry mechanism"""

    max_attempts: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    backoff_multiplier: float = 2.0
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
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(
            f"Retry exhausted after {attempts} attempts. "
            f"Last error: {type(last_exception).__name__}: {last_exception}"
        )


class RetryMechanism:
    """Retry mechanism with various backoff strategies"""

    def __init__(self, config: Optional[RetryConfig] = None):
        self.config = config or RetryConfig()
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

    async def execute_async(
        self, func: Callable, *args, operation_name: str = None, **kwargs
    ) -> Any:
        """Execute an async function with retry mechanism"""
        operation_name = operation_name or func.__name__
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            self.stats["total_attempts"] += 1

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
                    self.stats["successful_retries"] += 1
                    logger.info(f"{operation_name} succeeded on attempt {attempt}")

                # Update operation stats
                if operation_name not in self.stats["operations_by_type"]:
                    self.stats["operations_by_type"][operation_name] = {
                        "total": 0,
                        "succeeded": 0,
                        "retries_needed": 0,
                    }

                self.stats["operations_by_type"][operation_name]["total"] += 1
                self.stats["operations_by_type"][operation_name]["succeeded"] += 1
                if attempt > 1:
                    self.stats["operations_by_type"][operation_name][
                        "retries_needed"
                    ] += 1

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
                logger.debug(f"Retrying {operation_name} in {delay:.2f} seconds...")
                await asyncio.sleep(delay)

        # All attempts exhausted
        self.stats["failed_operations"] += 1

        # Update operation stats
        if operation_name not in self.stats["operations_by_type"]:
            self.stats["operations_by_type"][operation_name] = {
                "total": 0,
                "succeeded": 0,
                "retries_needed": 0,
            }

        self.stats["operations_by_type"][operation_name]["total"] += 1

        logger.error(
            f"{operation_name} failed after {self.config.max_attempts} attempts"
        )
        raise RetryExhaustedError(self.config.max_attempts, last_exception)

    def execute_sync(
        self, func: Callable, *args, operation_name: str = None, **kwargs
    ) -> Any:
        """Execute a synchronous function with retry mechanism"""
        operation_name = operation_name or func.__name__
        last_exception = None

        for attempt in range(1, self.config.max_attempts + 1):
            self.stats["total_attempts"] += 1

            try:
                logger.debug(
                    f"Executing {operation_name}, attempt {attempt}/{self.config.max_attempts}"
                )

                result = func(*args, **kwargs)

                # Success!
                if attempt > 1:
                    self.stats["successful_retries"] += 1
                    logger.info(f"{operation_name} succeeded on attempt {attempt}")

                # Update operation stats
                if operation_name not in self.stats["operations_by_type"]:
                    self.stats["operations_by_type"][operation_name] = {
                        "total": 0,
                        "succeeded": 0,
                        "retries_needed": 0,
                    }

                self.stats["operations_by_type"][operation_name]["total"] += 1
                self.stats["operations_by_type"][operation_name]["succeeded"] += 1
                if attempt > 1:
                    self.stats["operations_by_type"][operation_name][
                        "retries_needed"
                    ] += 1

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
                logger.debug(f"Retrying {operation_name} in {delay:.2f} seconds...")
                time.sleep(delay)

        # All attempts exhausted
        self.stats["failed_operations"] += 1

        # Update operation stats
        if operation_name not in self.stats["operations_by_type"]:
            self.stats["operations_by_type"][operation_name] = {
                "total": 0,
                "succeeded": 0,
                "retries_needed": 0,
            }

        self.stats["operations_by_type"][operation_name]["total"] += 1

        logger.error(
            f"{operation_name} failed after {self.config.max_attempts} attempts"
        )
        raise RetryExhaustedError(self.config.max_attempts, last_exception)

    def get_stats(self) -> Dict[str, Any]:
        """Get retry mechanism statistics"""
        return {
            **self.stats,
            "success_rate": (
                (self.stats["total_attempts"] - self.stats["failed_operations"])
                / max(1, self.stats["total_attempts"])
            )
            * 100,
        }

    def reset_stats(self):
        """Reset retry statistics"""
        self.stats = {
            "total_attempts": 0,
            "successful_retries": 0,
            "failed_operations": 0,
            "operations_by_type": {},
        }


# Global retry mechanism instance
default_retry_mechanism = RetryMechanism()


def retry_async(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_multiplier: float = 2.0,
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
        @wraps(func)
        async def wrapper(*args, **kwargs):
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
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_multiplier: float = 2.0,
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
        @wraps(func)
        def wrapper(*args, **kwargs):
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

    config = RetryConfig(
        max_attempts=3,
        base_delay=0.5,
        max_delay=5.0,
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

    config = RetryConfig(
        max_attempts=3,  # Reduced from 5 to 3 attempts
        base_delay=0.5,  # Reduced from 1.0 to 0.5 seconds
        max_delay=8.0,  # Reduced from 30.0 to 8.0 seconds
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
    config = RetryConfig(
        max_attempts=3,
        base_delay=0.1,
        max_delay=2.0,
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
            import random

            if random.random() < 0.7:  # 70% chance of failure
                raise ConnectionError("Network error")
            return "Success!"

        try:
            result = await flaky_network_call()
            print(f"Network call result: {result}")
        except RetryExhaustedError as e:
            print(f"Network call failed: {e}")

        # Example 2: Using retry mechanism directly
        retry_mechanism = RetryMechanism(
            RetryConfig(max_attempts=3, strategy=RetryStrategy.JITTERED_BACKOFF)
        )

        async def another_flaky_operation():
            import random

            if random.random() < 0.5:
                raise TimeoutError("Operation timed out")
            return "Operation completed"

        try:
            result = await retry_mechanism.execute_async(
                another_flaky_operation, operation_name="flaky_operation"
            )
            print(f"Operation result: {result}")
        except RetryExhaustedError as e:
            print(f"Operation failed: {e}")

        # Print statistics
        print("Retry statistics:", retry_mechanism.get_stats())

    # Run example
    asyncio.run(example_usage())
