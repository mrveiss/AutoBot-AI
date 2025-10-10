"""
Singleton HTTP Client Manager
Provides efficient aiohttp client session management to prevent resource exhaustion
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import ClientSession, ClientTimeout, TCPConnector
from src.constants.network_constants import NetworkConstants

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

        # Create connector with connection pooling
        self._connector = TCPConnector(
            limit=100,  # Total connection pool size
            limit_per_host=30,  # Per-host connection limit
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

        logger.info("Created new aiohttp ClientSession with connection pooling")

    async def request(self, method: str, url: str, **kwargs) -> aiohttp.ClientResponse:
        """
        Make an HTTP request using the shared session.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Target URL
            **kwargs: Additional arguments for aiohttp request

        Returns:
            ClientResponse: The response object
        """
        session = await self.get_session()

        try:
            self._request_count += 1
            response = await session.request(method, url, **kwargs)
            return response
        except Exception as e:
            self._error_count += 1
            logger.error(f"HTTP request failed: {e}")
            raise

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
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
            "error_rate": (
                self._error_count / self._request_count
                if self._request_count > 0
                else 0
            ),
            "session_active": bool(self._session and not self._session.closed),
            "connector_stats": (
                self._connector._connector_stats() if self._connector else {}
            ),
        }

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Global singleton instance
_http_client: Optional[HTTPClientManager] = None


def get_http_client() -> HTTPClientManager:
    """
    Get the global HTTP client manager instance.

    Returns:
        HTTPClientManager: The singleton HTTP client
    """
    global _http_client
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
        print(f"Received data: {data}")
    except aiohttp.ClientError as e:
        logger.error(f"Request failed: {e}")

    # POST request with JSON
    try:
        response_data = await http_client.post_json(
            "https://api.example.com/submit", json_data={"key": "value"}
        )
        print(f"Response: {response_data}")
    except aiohttp.ClientError as e:
        logger.error(f"Request failed: {e}")

    # Manual request with custom options
    try:
        async with await http_client.get(
            "https://api.example.com/stream", timeout=aiohttp.ClientTimeout(total=60)
        ) as response:
            async for chunk in response.content.iter_chunked(1024):
                # Process streaming data
                pass
    except Exception as e:
        logger.error(f"Streaming failed: {e}")

    # Get statistics
    stats = http_client.get_stats()
    logger.info(f"HTTP client stats: {stats}")


# Decorator for automatic session management
def with_http_client(func):
    """Decorator to inject HTTP client into async functions."""

    async def wrapper(*args, **kwargs):
        http_client = get_http_client()
        return await func(*args, http_client=http_client, **kwargs)

    return wrapper
