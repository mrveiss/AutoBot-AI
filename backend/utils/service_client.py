# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service HTTP Client with Automatic Request Signing
Provides authenticated HTTP client for service-to-service communication

Usage:
    from src.constants.network_constants import ServiceURLs

    client = ServiceHTTPClient(service_id="main-backend", service_key="...")
    response = await client.get(f"{ServiceURLs.AI_STACK_SERVICE}/api/inference")
    response = await client.post(f"{ServiceURLs.NPU_WORKER_SERVICE}/api/process", json={...})
"""

import asyncio
import time
from typing import Dict

import aiohttp
import structlog

from backend.security.service_auth import ServiceAuthManager
from src.utils.http_client import get_http_client

logger = structlog.get_logger()


class ServiceHTTPClient:
    """
    HTTP client for service-to-service calls with automatic authentication.

    Automatically signs all requests with HMAC-SHA256 signatures and includes
    required authentication headers.
    """

    def __init__(self, service_id: str, service_key: str, timeout: float = 30.0):
        """
        Initialize authenticated HTTP client.

        Args:
            service_id: This service's identifier (e.g., 'main-backend')
            service_key: This service's secret key (256-bit hex)
            timeout: Request timeout in seconds (default: 30.0)
        """
        self.service_id = service_id
        self.service_key = service_key
        self.timeout = timeout

        # Use HTTPClient singleton
        self.http_client = get_http_client()

        logger.info(
            "Service HTTP client initialized", service_id=service_id, timeout=timeout
        )

    def _sign_request(self, method: str, url: str) -> Dict[str, str]:
        """
        Generate authentication headers for request.

        Args:
            method: HTTP method (GET, POST, etc.)
            url: Full URL of the request

        Returns:
            Dict of authentication headers
        """
        timestamp = int(time.time())

        # Create auth manager for signing (no Redis needed for signing)
        auth_manager = ServiceAuthManager(redis_client=None)

        # Extract path from URL for signature
        from urllib.parse import urlparse

        parsed_url = urlparse(url)
        path = parsed_url.path

        # Generate HMAC signature
        signature = auth_manager.generate_signature(
            self.service_id, self.service_key, method, path, timestamp
        )

        return {
            "X-Service-ID": self.service_id,
            "X-Service-Signature": signature,
            "X-Service-Timestamp": str(timestamp),
        }

    async def get(self, url: str, **kwargs):
        """
        Perform authenticated GET request.

        Args:
            url: Request URL
            **kwargs: Additional arguments passed to aiohttp.get()

        Returns:
            HTTP response object (async context manager)

        Raises:
            aiohttp.ClientError: On connection or protocol errors
            asyncio.TimeoutError: When request times out
        """
        headers = self._sign_request("GET", url)

        # Merge auth headers with any user-provided headers
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers

        # Set timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=self.timeout)

        logger.debug("Service GET request", service_id=self.service_id, url=url)

        try:
            return await self.http_client.get(url, **kwargs)
        except aiohttp.ClientError as e:
            logger.error(
                "Service GET request failed",
                service_id=self.service_id,
                url=url,
                error=str(e),
            )
            raise
        except asyncio.TimeoutError:
            logger.error(
                "Service GET request timed out",
                service_id=self.service_id,
                url=url,
                timeout=self.timeout,
            )
            raise

    async def post(self, url: str, **kwargs):
        """
        Perform authenticated POST request.

        Args:
            url: Request URL
            **kwargs: Additional arguments passed to aiohttp.post()

        Returns:
            HTTP response object (async context manager)

        Raises:
            aiohttp.ClientError: On connection or protocol errors
            asyncio.TimeoutError: When request times out
        """
        headers = self._sign_request("POST", url)

        # Merge auth headers with any user-provided headers
        if "headers" in kwargs:
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers

        # Set timeout
        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=self.timeout)

        logger.debug("Service POST request", service_id=self.service_id, url=url)

        try:
            return await self.http_client.post(url, **kwargs)
        except aiohttp.ClientError as e:
            logger.error(
                "Service POST request failed",
                service_id=self.service_id,
                url=url,
                error=str(e),
            )
            raise
        except asyncio.TimeoutError:
            logger.error(
                "Service POST request timed out",
                service_id=self.service_id,
                url=url,
                timeout=self.timeout,
            )
            raise

    async def put(self, url: str, **kwargs):
        """
        Perform authenticated PUT request.

        Args:
            url: Request URL
            **kwargs: Additional arguments passed to aiohttp.put()

        Returns:
            HTTP response object (async context manager)

        Raises:
            aiohttp.ClientError: On connection or protocol errors
            asyncio.TimeoutError: When request times out
        """
        headers = self._sign_request("PUT", url)

        if "headers" in kwargs:
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers

        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=self.timeout)

        logger.debug("Service PUT request", service_id=self.service_id, url=url)

        try:
            return await self.http_client.put(url, **kwargs)
        except aiohttp.ClientError as e:
            logger.error(
                "Service PUT request failed",
                service_id=self.service_id,
                url=url,
                error=str(e),
            )
            raise
        except asyncio.TimeoutError:
            logger.error(
                "Service PUT request timed out",
                service_id=self.service_id,
                url=url,
                timeout=self.timeout,
            )
            raise

    async def delete(self, url: str, **kwargs):
        """
        Perform authenticated DELETE request.

        Args:
            url: Request URL
            **kwargs: Additional arguments passed to aiohttp.delete()

        Returns:
            HTTP response object (async context manager)

        Raises:
            aiohttp.ClientError: On connection or protocol errors
            asyncio.TimeoutError: When request times out
        """
        headers = self._sign_request("DELETE", url)

        if "headers" in kwargs:
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers

        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=self.timeout)

        logger.debug("Service DELETE request", service_id=self.service_id, url=url)

        try:
            return await self.http_client.delete(url, **kwargs)
        except aiohttp.ClientError as e:
            logger.error(
                "Service DELETE request failed",
                service_id=self.service_id,
                url=url,
                error=str(e),
            )
            raise
        except asyncio.TimeoutError:
            logger.error(
                "Service DELETE request timed out",
                service_id=self.service_id,
                url=url,
                timeout=self.timeout,
            )
            raise

    async def patch(self, url: str, **kwargs):
        """
        Perform authenticated PATCH request.

        Args:
            url: Request URL
            **kwargs: Additional arguments passed to aiohttp.patch()

        Returns:
            HTTP response object (async context manager)

        Raises:
            aiohttp.ClientError: On connection or protocol errors
            asyncio.TimeoutError: When request times out
        """
        headers = self._sign_request("PATCH", url)

        if "headers" in kwargs:
            headers.update(kwargs["headers"])
        kwargs["headers"] = headers

        if "timeout" not in kwargs:
            kwargs["timeout"] = aiohttp.ClientTimeout(total=self.timeout)

        logger.debug("Service PATCH request", service_id=self.service_id, url=url)

        try:
            return await self.http_client.patch(url, **kwargs)
        except aiohttp.ClientError as e:
            logger.error(
                "Service PATCH request failed",
                service_id=self.service_id,
                url=url,
                error=str(e),
            )
            raise
        except asyncio.TimeoutError:
            logger.error(
                "Service PATCH request timed out",
                service_id=self.service_id,
                url=url,
                timeout=self.timeout,
            )
            raise

    async def close(self):
        """Close the HTTP client and cleanup resources."""
        # HTTPClient singleton doesn't need to be closed per instance
        logger.info("Service HTTP client closed", service_id=self.service_id)

    async def __aenter__(self):
        """Async context manager entry."""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()


# Helper function to load credentials from environment
def load_service_credentials_from_env() -> tuple[str, str]:
    """
    Load service credentials from environment variables or file.

    Returns:
        Tuple of (service_id, service_key)

    Raises:
        ValueError: If credentials not found
    """
    import os
    from pathlib import Path

    # Try SERVICE_ID from environment
    service_id = os.getenv("SERVICE_ID")
    if not service_id:
        raise ValueError("SERVICE_ID not set in environment")

    # Try SERVICE_KEY directly from environment
    service_key = os.getenv("SERVICE_KEY")
    if service_key:
        return service_id, service_key

    # Try loading from SERVICE_KEY_FILE
    key_file_path = os.getenv("SERVICE_KEY_FILE")
    if not key_file_path:
        raise ValueError("Neither SERVICE_KEY nor SERVICE_KEY_FILE set in environment")

    key_file = Path(key_file_path)
    if not key_file.exists():
        raise ValueError(f"Service key file not found: {key_file_path}")

    # Parse .env file to extract SERVICE_KEY
    with open(key_file, "r") as f:
        for line in f:
            line = line.strip()
            if line.startswith("SERVICE_KEY="):
                service_key = line.split("=", 1)[1].strip()
                return service_id, service_key

    raise ValueError(f"SERVICE_KEY not found in {key_file_path}")


# Convenience function for creating authenticated client from environment
def create_service_client_from_env() -> ServiceHTTPClient:
    """
    Create authenticated service client using environment configuration.

    Reads SERVICE_ID and SERVICE_KEY (or SERVICE_KEY_FILE) from environment.

    Returns:
        Configured ServiceHTTPClient instance

    Raises:
        ValueError: If credentials not found in environment

    Example:
        from src.constants.network_constants import ServiceURLs

        # Set environment variables
        os.environ["SERVICE_ID"] = "main-backend"
        os.environ["SERVICE_KEY_FILE"] = str(PATH.USER_HOME / ".autobot/service-keys/main-backend.env")

        # Create client
        client = create_service_client_from_env()
        response = await client.get(f"{ServiceURLs.AI_STACK_SERVICE}/api/inference")
    """
    import os

    service_id, service_key = load_service_credentials_from_env()

    logger.info(
        "Creating service client from environment",
        service_id=service_id,
        key_file=os.getenv("SERVICE_KEY_FILE"),
    )

    return ServiceHTTPClient(service_id=service_id, service_key=service_key)


# Convenience function for creating authenticated clients
async def create_service_client(
    service_id: str, redis_manager=None
) -> ServiceHTTPClient:
    """
    Create authenticated service client by loading key from Redis.

    Args:
        service_id: Service identifier
        redis_manager: AsyncRedisManager instance (optional)

    Returns:
        Configured ServiceHTTPClient instance

    Raises:
        ValueError: If service key not found
        redis.RedisError: On Redis connection or operation failure
    """
    try:
        if redis_manager is None:
            from src.utils.redis_client import get_redis_client as get_redis_manager

            redis_manager = await get_redis_manager()

        redis = await redis_manager.main()

        # Get service key from Redis
        service_key = await redis.get(f"service:key:{service_id}")
        if not service_key:
            raise ValueError(f"Service key not found for: {service_id}")

        return ServiceHTTPClient(service_id=service_id, service_key=service_key)
    except ValueError:
        # Re-raise ValueError as-is (service key not found)
        raise
    except Exception as e:
        logger.error(
            "Failed to create service client",
            service_id=service_id,
            error=str(e),
        )
        raise RuntimeError(f"Failed to create service client for {service_id}: {e}")
