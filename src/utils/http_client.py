# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Singleton HTTP Client Manager
Provides efficient aiohttp client session management to prevent resource exhaustion
"""

import asyncio
import logging
import time
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector

from src.constants.threshold_constants import TimingConstants

logger = logging.getLogger(__name__)


class HTTPClientManager:
    """
    Singleton aiohttp ClientSession manager for efficient HTTP requests.
    Prevents creating new ClientSession for each request which causes resource exhaustion.
    """

    _instance: Optional["HTTPClientManager"] = None
    _session: Optional[ClientSession] = None
    _lock = asyncio.Lock()

    def __new__(cls):
        """Create or return singleton HTTPClientManager instance."""
        if cls._instance is None:
            cls._instance = super(HTTPClientManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the HTTP client manager."""
        if not hasattr(self, "_initialized"):
            self._initialized = True
            self._session = None
            self._connector = None
            self._closed = False
            self._request_count = 0
            self._error_count = 0
            self._counter_lock = asyncio.Lock()  # Lock for thread-safe counter access

            # Dynamic pool sizing configuration
            self._pool_min = 20  # Minimum pool size
            self._pool_max = 200  # Maximum pool size
            self._current_pool_size = 100  # Start at default
            self._pool_adjustment_interval = (
                TimingConstants.STANDARD_TIMEOUT
            )  # Adjust every 60s
            self._last_adjustment_time = 0
            self._active_requests = 0  # Track concurrent requests
            self._pending_pool_recreation = (
                False  # Issue #352: Track deferred recreation
            )

    async def get_session(self) -> ClientSession:
        """
        Get or create the singleton aiohttp ClientSession.

        Returns:
            ClientSession: The shared aiohttp session
        """
        if self._closed:
            raise RuntimeError("HTTPClientManager has been closed")

        if self._session is None or self._session.closed:
            async with self._lock:
                # Double-check after acquiring lock
                if self._session is None or self._session.closed:
                    await self._create_session()

        return self._session

    async def _create_session(self):
        """Create a new aiohttp ClientSession with optimized settings."""
        # Close existing session if any
        if self._session and not self._session.closed:
            await self._session.close()

        # Create connector with dynamic connection pooling
        self._connector = TCPConnector(
            limit=self._current_pool_size,  # Dynamic pool size
            limit_per_host=min(30, self._current_pool_size // 3),  # 1/3 of total pool
            ttl_dns_cache=300,  # DNS cache timeout
            enable_cleanup_closed=True,
        )

        # Create session with timeout and connector
        timeout = ClientTimeout(
            total=30,  # Total timeout
            connect=5,  # Connection timeout
            sock_read=10,  # Socket read timeout
        )

        self._session = ClientSession(
            connector=self._connector,
            timeout=timeout,
            headers={"User-Agent": "AutoBot/1.0"},
        )

        logger.info(
            f"Created new aiohttp ClientSession with pool size: {self._current_pool_size}"
        )

    def _calculate_new_pool_size(
        self, utilization: float, error_rate: float
    ) -> tuple[int, bool]:
        """
        Calculate new pool size based on utilization and error metrics.

        Args:
            utilization: Current pool utilization ratio
            error_rate: Current error rate ratio

        Returns:
            Tuple of (new_pool_size, was_adjusted). Issue #620.
        """
        old_size = self._current_pool_size
        new_size = old_size
        adjusted = False

        # Increase pool if under pressure
        if (utilization > 0.7 or error_rate > 0.05) and old_size < self._pool_max:
            new_size = min(int(old_size * 1.25), self._pool_max)
            adjusted = True
            logger.info(
                f"Increased connection pool: {old_size} → {new_size} "
                f"(utilization: {utilization:.1%}, error_rate: {error_rate:.1%})"
            )

        # Decrease pool if over-provisioned
        elif utilization < 0.2 and error_rate < 0.01 and old_size > self._pool_min:
            new_size = max(int(old_size * 0.85), self._pool_min)
            adjusted = True
            logger.info(
                f"Decreased connection pool: {old_size} → {new_size} "
                f"(utilization: {utilization:.1%})"
            )

        return new_size, adjusted

    async def _handle_pool_recreation(self) -> None:
        """
        Handle session recreation after pool size change.

        Issue #352: Fixed race condition - don't recreate while requests in flight.
        Issue #620.
        """
        if self._active_requests > 0:
            self._pending_pool_recreation = True
            logger.info(
                f"Pool size changed to {self._current_pool_size} but "
                f"deferring session recreation ({self._active_requests} active requests)"
            )
        else:
            self._pending_pool_recreation = False
            logger.info("Recreating session with new pool size")
            await self._create_session()

    async def _adjust_pool_size(self):
        """
        Dynamically adjust connection pool size based on usage patterns.

        Increases pool size if utilization > 70% or error rate > 5%.
        Decreases pool size if utilization < 20% and error rate < 1%.
        """
        current_time = time.time()

        # Only adjust at specified intervals
        if current_time - self._last_adjustment_time < self._pool_adjustment_interval:
            return

        async with self._counter_lock:
            # Calculate utilization metrics
            utilization = (
                self._active_requests / self._current_pool_size
                if self._current_pool_size > 0
                else 0
            )
            error_rate = (
                self._error_count / self._request_count
                if self._request_count > 0
                else 0
            )

            # Issue #620: Use helper for pool size calculation
            new_size, adjusted = self._calculate_new_pool_size(utilization, error_rate)
            self._current_pool_size = new_size
            self._last_adjustment_time = current_time

            # Issue #620: Use helper for session recreation
            if adjusted and self._session and not self._session.closed:
                await self._handle_pool_recreation()

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Make an HTTP request using the shared session.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            **kwargs: Additional arguments for aiohttp request

        Returns:
            ClientResponse: The response object

        Note: For streaming responses, caller should use increment_active()/decrement_active()
        to prevent pool recreation during streaming.
        """
        # Check if pool adjustment needed (non-blocking)
        asyncio.create_task(self._adjust_pool_size())

        session = await self.get_session()

        # Track active requests for utilization calculation
        async with self._counter_lock:
            self._request_count += 1
            self._active_requests += 1

        try:
            response = await session.request(method, url, **kwargs)
            return response
        except Exception as e:
            async with self._counter_lock:
                self._error_count += 1
                # Also decrement active on error since we're not returning response
                self._active_requests = max(0, self._active_requests - 1)
            logger.error("HTTP request failed: %s", e)
            raise

    async def decrement_active(self):
        """
        Decrement active request counter and potentially trigger deferred pool recreation.

        Issue #680: Call this when a streaming response is fully consumed, not when the
        initial request completes. This prevents pool recreation from closing streaming
        connections mid-stream.

        Usage:
            response = await http_client.post(url, ...)
            try:
                async with response:
                    # stream the response
            finally:
                await http_client.decrement_active()
        """
        should_recreate = False
        async with self._counter_lock:
            self._active_requests = max(0, self._active_requests - 1)
            # Issue #352: Check if we should apply deferred pool recreation
            if (
                self._active_requests == 0
                and self._pending_pool_recreation
                and self._session
                and not self._session.closed
            ):
                self._pending_pool_recreation = False
                should_recreate = True

        # Issue #352: Apply deferred recreation outside of lock to avoid deadlock
        if should_recreate:
            logger.info(
                "Applying deferred session recreation "
                f"(new pool size: {self._current_pool_size})"
            )
            await self._create_session()

    async def get(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Convenience method for GET requests."""
        return await self.request("GET", url, **kwargs)

    async def post(self, url: str, **kwargs) -> aiohttp.ClientResponse:
        """Convenience method for POST requests."""
        return await self.request("POST", url, **kwargs)

    async def get_json(self, url: str, **kwargs) -> Dict[str, Any]:
        """
        Make a GET request and return JSON response.

        Args:
            url: Target URL
            **kwargs: Additional arguments for request

        Returns:
            Dict containing the JSON response
        """
        async with await self.get(url, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def post_json(
        self, url: str, json_data: Dict[str, Any], **kwargs
    ) -> Dict[str, Any]:
        """
        Make a POST request with JSON data and return JSON response.

        Args:
            url: Target URL
            json_data: Data to send as JSON
            **kwargs: Additional arguments for request

        Returns:
            Dict containing the JSON response
        """
        async with await self.post(url, json=json_data, **kwargs) as response:
            response.raise_for_status()
            return await response.json()

    async def close(self):
        """Close the HTTP client session and cleanup resources."""
        async with self._lock:
            if self._session and not self._session.closed:
                await self._session.close()
                logger.info(
                    f"Closed HTTP client session. "
                    f"Total requests: {self._request_count}, "
                    f"Errors: {self._error_count}"
                )

            self._session = None
            self._connector = None
            self._closed = True

    def get_stats(self) -> Dict[str, Any]:
        """Get client usage statistics."""
        utilization = (
            self._active_requests / self._current_pool_size
            if self._current_pool_size > 0
            else 0
        )

        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "active_requests": self._active_requests,
            "error_rate": (
                self._error_count / self._request_count
                if self._request_count > 0
                else 0
            ),
            "session_active": bool(self._session and not self._session.closed),
            "pool_size": {
                "current": self._current_pool_size,
                "min": self._pool_min,
                "max": self._pool_max,
                "utilization": utilization,
            },
        }

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global singleton instance (thread-safe)
import threading

_http_client: Optional[HTTPClientManager] = None
_http_client_lock = threading.Lock()


def get_http_client() -> HTTPClientManager:
    """
    Get the global HTTP client manager instance (thread-safe).

    Returns:
        HTTPClientManager: The singleton HTTP client
    """
    global _http_client
    if _http_client is None:
        with _http_client_lock:
            # Double-check after acquiring lock
            if _http_client is None:
                _http_client = HTTPClientManager()
    return _http_client


async def close_http_client():
    """Close the global HTTP client and cleanup resources."""
    global _http_client
    if _http_client:
        await _http_client.close()
        _http_client = None


# Example usage patterns for migration
async def example_usage():
    """Example of how to use the HTTP client manager."""

    # Get the singleton client
    http_client = get_http_client()

    # Simple GET request
    try:
        data = await http_client.get_json("https://api.example.com/data")
        logger.info("Received data: %s", data)
    except aiohttp.ClientError as e:
        logger.error("Request failed: %s", e)

    # POST request with JSON
    try:
        response_data = await http_client.post_json(
            "https://api.example.com/submit", json_data={"key": "value"}
        )
        logger.info("Response: %s", response_data)
    except aiohttp.ClientError as e:
        logger.error("Request failed: %s", e)

    # Manual request with custom options
    try:
        async with await http_client.get(
            "https://api.example.com/stream", timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            async for chunk in response.content.iter_chunked(1024):
                # Process streaming data
                pass
    except Exception as e:
        logger.error("Streaming failed: %s", e)

    # Get statistics
    stats = http_client.get_stats()
    logger.info("HTTP client stats: %s", stats)


# Decorator for automatic session management
def with_http_client(func):
    """Decorator to inject HTTP client into async functions."""

    async def wrapper(*args, **kwargs):
        """Async wrapper that injects HTTP client into decorated function."""
        http_client = get_http_client()
        return await func(*args, http_client=http_client, **kwargs)

    return wrapper
