# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Rate Limit Handler - Intelligent rate limit handling with exponential backoff.

Handles cloud API rate limits with automatic retry, exponential backoff,
and jitter to prevent thundering herd problems.

Issue #717: Efficient Inference Design implementation.
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStrategy(Enum):
    """Retry backoff strategies."""

    EXPONENTIAL = "exponential"  # 2^attempt seconds
    LINEAR = "linear"  # attempt * base seconds
    FIXED = "fixed"  # Fixed delay


class RateLimitError(Exception):
    """Raised when rate limit is exceeded."""

    def __init__(
        self,
        message: str,
        retry_after: float = None,
        provider: str = None,
    ):
        """
        Initialize rate limit error.

        Args:
            message: Error message
            retry_after: Suggested retry delay in seconds
            provider: Provider that returned the rate limit
        """
        super().__init__(message)
        self.retry_after = retry_after
        self.provider = provider


@dataclass
class RateLimitConfig:
    """Configuration for rate limit handling."""

    max_retries: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Maximum delay cap
    jitter_factor: float = 0.5  # Random jitter (0-1)
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL

    # Rate limit detection
    rate_limit_status_codes: tuple = (429, 503)
    rate_limit_headers: tuple = ("retry-after", "x-ratelimit-reset")


@dataclass
class RetryMetrics:
    """Metrics for retry operations."""

    total_requests: int = 0
    successful_requests: int = 0
    retried_requests: int = 0
    failed_requests: int = 0
    total_retry_attempts: int = 0
    total_wait_time_seconds: float = 0.0
    last_rate_limit_at: Optional[float] = None
    rate_limits_hit: int = 0


class RateLimitHandler:
    """
    Handle cloud API rate limits with exponential backoff.

    Provides automatic retry with configurable backoff strategies,
    jitter for thundering herd prevention, and comprehensive metrics.

    Typical usage:
        handler = RateLimitHandler()
        result = await handler.execute_with_retry(api_call)
    """

    def __init__(self, config: RateLimitConfig = None):
        """
        Initialize rate limit handler.

        Args:
            config: Rate limit configuration
        """
        self.config = config or RateLimitConfig()
        self._metrics: Dict[str, RetryMetrics] = {}
        self._lock = asyncio.Lock()

        logger.info(
            "RateLimitHandler initialized: max_retries=%d, strategy=%s",
            self.config.max_retries,
            self.config.strategy.value,
        )

    def _get_metrics(self, provider: str) -> RetryMetrics:
        """Get or create metrics for a provider."""
        if provider not in self._metrics:
            self._metrics[provider] = RetryMetrics()
        return self._metrics[provider]

    def _calculate_delay(
        self,
        attempt: int,
        retry_after: float = None,
    ) -> float:
        """
        Calculate delay before next retry.

        Args:
            attempt: Current attempt number (0-indexed)
            retry_after: Server-suggested retry delay

        Returns:
            Delay in seconds
        """
        # Respect server's retry-after if provided
        if retry_after is not None and retry_after > 0:
            base_delay = retry_after
        else:
            if self.config.strategy == RetryStrategy.EXPONENTIAL:
                base_delay = self.config.base_delay * (2**attempt)
            elif self.config.strategy == RetryStrategy.LINEAR:
                base_delay = self.config.base_delay * (attempt + 1)
            else:  # FIXED
                base_delay = self.config.base_delay

        # Apply cap
        base_delay = min(base_delay, self.config.max_delay)

        # Add jitter to prevent thundering herd
        jitter = base_delay * self.config.jitter_factor * random.random()

        return base_delay + jitter

    def _is_rate_limit_error(self, error: Exception) -> tuple:
        """
        Check if error is a rate limit error.

        Args:
            error: The exception to check

        Returns:
            Tuple of (is_rate_limit, retry_after)
        """
        # Check for our RateLimitError
        if isinstance(error, RateLimitError):
            return True, error.retry_after

        # Check for httpx response errors
        if hasattr(error, "response"):
            response = error.response
            if hasattr(response, "status_code"):
                if response.status_code in self.config.rate_limit_status_codes:
                    # Try to extract retry-after header
                    retry_after = None
                    for header in self.config.rate_limit_headers:
                        value = response.headers.get(header)
                        if value:
                            try:
                                retry_after = float(value)
                                break
                            except ValueError:
                                pass
                    return True, retry_after

        return False, None

    async def execute_with_retry(
        self,
        api_call: Callable[[], Coroutine[Any, Any, T]],
        provider: str = "default",
        max_retries: int = None,
    ) -> T:
        """
        Execute an API call with automatic retry on rate limit.

        Issue #620: Refactored to use helper functions.

        Args:
            api_call: Async function to call
            provider: Provider name for metrics
            max_retries: Override max retries (uses config default if None)

        Returns:
            Result of the API call

        Raises:
            RateLimitError: If all retries exhausted
            Exception: Other non-rate-limit errors
        """
        max_attempts = (max_retries or self.config.max_retries) + 1
        metrics = self._get_metrics(provider)
        await self._record_request_start(metrics)
        last_error = None

        for attempt in range(max_attempts):
            try:
                result = await api_call()
                await self._record_success(metrics, attempt)
                return result
            except Exception as e:
                last_error = await self._handle_attempt_error(
                    e, metrics, provider, attempt, max_attempts
                )
                if last_error is None:
                    raise  # Non-rate-limit error or exhausted retries

        raise last_error or RuntimeError("Unexpected retry loop exit")

    async def _record_request_start(self, metrics: "RetryMetrics") -> None:
        """Record request start. Issue #620."""
        async with self._lock:
            metrics.total_requests += 1

    async def _record_success(self, metrics: "RetryMetrics", attempt: int) -> None:
        """Record successful request. Issue #620."""
        async with self._lock:
            metrics.successful_requests += 1
            if attempt > 0:
                metrics.retried_requests += 1

    async def _record_rate_limit_hit(self, metrics: "RetryMetrics") -> None:
        """Record a rate limit hit in metrics. Issue #620."""
        async with self._lock:
            metrics.rate_limits_hit += 1
            metrics.last_rate_limit_at = time.time()

    async def _wait_and_retry(
        self,
        metrics: "RetryMetrics",
        provider: str,
        attempt: int,
        max_attempts: int,
        retry_after: Optional[float],
    ) -> None:
        """Wait with backoff before retry. Issue #620."""
        delay = self._calculate_delay(attempt, retry_after)
        async with self._lock:
            metrics.total_retry_attempts += 1
            metrics.total_wait_time_seconds += delay
        logger.warning(
            "Rate limit for %s, retry %d/%d in %.2fs",
            provider,
            attempt + 1,
            max_attempts - 1,
            delay,
        )
        await asyncio.sleep(delay)

    async def _handle_attempt_error(
        self,
        error: Exception,
        metrics: "RetryMetrics",
        provider: str,
        attempt: int,
        max_attempts: int,
    ) -> Optional[Exception]:
        """Handle error during attempt. Issue #620."""
        is_rate_limit, retry_after = self._is_rate_limit_error(error)

        if not is_rate_limit:
            async with self._lock:
                metrics.failed_requests += 1
            return None

        await self._record_rate_limit_hit(metrics)

        if attempt < max_attempts - 1:
            await self._wait_and_retry(
                metrics, provider, attempt, max_attempts, retry_after
            )
            return error

        async with self._lock:
            metrics.failed_requests += 1
        raise RateLimitError(
            f"Rate limit exceeded for {provider} after {max_attempts} attempts",
            retry_after=retry_after,
            provider=provider,
        ) from error

    def get_metrics(self, provider: str = None) -> Dict[str, Any]:
        """
        Get retry metrics.

        Args:
            provider: Specific provider or None for all

        Returns:
            Dict of metrics
        """
        if provider:
            metrics = self._metrics.get(provider)
            if not metrics:
                return {}

            return {
                "provider": provider,
                "total_requests": metrics.total_requests,
                "successful_requests": metrics.successful_requests,
                "retried_requests": metrics.retried_requests,
                "failed_requests": metrics.failed_requests,
                "total_retry_attempts": metrics.total_retry_attempts,
                "total_wait_time_seconds": round(metrics.total_wait_time_seconds, 2),
                "rate_limits_hit": metrics.rate_limits_hit,
                "success_rate": (
                    metrics.successful_requests / max(metrics.total_requests, 1)
                ),
                "last_rate_limit_at": metrics.last_rate_limit_at,
            }

        return {name: self.get_metrics(name) for name in self._metrics.keys()}

    def reset_metrics(self, provider: str = None) -> None:
        """Reset metrics for a provider or all providers."""
        if provider:
            if provider in self._metrics:
                self._metrics[provider] = RetryMetrics()
        else:
            self._metrics.clear()


# Convenience decorator for rate-limited functions
def with_retry(
    provider: str = "default",
    max_retries: int = 3,
    handler: RateLimitHandler = None,
):
    """
    Decorator to add retry logic to async functions.

    Args:
        provider: Provider name for metrics
        max_retries: Maximum retry attempts
        handler: RateLimitHandler instance (creates default if None)
    """
    _handler = handler or RateLimitHandler()

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]]
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await _handler.execute_with_retry(
                lambda: func(*args, **kwargs),
                provider=provider,
                max_retries=max_retries,
            )

        return wrapper

    return decorator


__all__ = [
    "RateLimitHandler",
    "RateLimitConfig",
    "RateLimitError",
    "RetryStrategy",
    "RetryMetrics",
    "with_retry",
]
