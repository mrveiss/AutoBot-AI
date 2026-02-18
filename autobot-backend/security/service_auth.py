# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Service-to-Service Authentication Module for AutoBot
Implements API Key + HMAC-SHA256 authentication for distributed VM infrastructure

CRITICAL SECURITY: Prevents CVSS 10.0 vulnerability where any service can call any endpoint
"""

import hashlib
import hmac
import secrets
import time
from typing import Dict, Optional

import structlog
from backend.utils.catalog_http_exceptions import raise_auth_error, raise_server_error
from fastapi import HTTPException, Request

from autobot_shared.redis_client import get_redis_client

logger = structlog.get_logger()


class ServiceAuthManager:
    """Manages service-to-service authentication with HMAC-SHA256 signing."""

    def __init__(self, redis_client):
        """
        Initialize service authentication manager.

        Args:
            redis_client: AsyncRedisDatabase instance for key storage
        """
        self.redis = redis_client
        self.timestamp_window = 300  # 5 minutes - prevents replay attacks

    async def generate_service_key(self, service_id: str) -> str:
        """
        Generate 256-bit API key for a service.

        Args:
            service_id: Unique identifier for the service (e.g., 'main-backend', 'npu-worker')

        Returns:
            Hex-encoded 256-bit API key
        """
        key = secrets.token_bytes(32)  # 256 bits
        key_hex = key.hex()

        # Store in Redis with 90-day expiration
        await self.redis.set(f"service:key:{service_id}", key_hex, ex=86400 * 90)

        logger.info(
            "Generated service key for %s", service_id, extra={"service_id": service_id}
        )
        return key_hex

    async def get_service_key(self, service_id: str) -> Optional[str]:
        """
        Retrieve service key from Redis.

        Args:
            service_id: Service identifier

        Returns:
            Service key if exists, None otherwise
        """
        key = await self.redis.get(f"service:key:{service_id}")
        return key if key else None

    def generate_signature(
        self, service_id: str, service_key: str, method: str, path: str, timestamp: int
    ) -> str:
        """
        Generate HMAC-SHA256 signature for request.

        Signature format: HMAC-SHA256(service_key, "service_id:method:path:timestamp")

        Args:
            service_id: Service identifier
            service_key: Service's secret key
            method: HTTP method (GET, POST, etc.)
            path: Request path
            timestamp: Unix timestamp

        Returns:
            Hex-encoded HMAC-SHA256 signature
        """
        message = f"{service_id}:{method}:{path}:{timestamp}"
        signature = hmac.new(
            service_key.encode(), message.encode(), hashlib.sha256
        ).hexdigest()
        return signature

    def _extract_auth_headers(self, request: Request) -> tuple[str, str, str]:
        """
        Extract and validate presence of authentication headers (Issue #665: extracted helper).

        Args:
            request: FastAPI request object

        Returns:
            Tuple of (service_id, signature, timestamp_str)

        Raises:
            HTTPException: If any required header is missing
        """
        service_id = request.headers.get("X-Service-ID")
        signature = request.headers.get("X-Service-Signature")
        timestamp_str = request.headers.get("X-Service-Timestamp")

        if not all([service_id, signature, timestamp_str]):
            logger.warning(
                "Missing authentication headers",
                path=request.url.path,
                has_service_id=bool(service_id),
                has_signature=bool(signature),
                has_timestamp=bool(timestamp_str),
            )
            raise_auth_error("AUTH_0002", "Missing required headers")

        return service_id, signature, timestamp_str

    def _validate_timestamp(self, timestamp_str: str, service_id: str) -> int:
        """
        Validate timestamp format and check against replay attack window (Issue #665: extracted helper).

        Args:
            timestamp_str: Timestamp string from header
            service_id: Service identifier for logging

        Returns:
            Validated timestamp as integer

        Raises:
            HTTPException: If timestamp is invalid or outside allowed window
        """
        try:
            timestamp = int(timestamp_str)
        except ValueError:
            logger.warning("Invalid timestamp format", timestamp=timestamp_str)
            raise_auth_error("AUTH_0004", "Invalid timestamp format")

        current_time = int(time.time())
        time_diff = abs(current_time - timestamp)

        if time_diff > self.timestamp_window:
            logger.warning(
                "Timestamp outside allowed window",
                service_id=service_id,
                time_diff=time_diff,
                max_window=self.timestamp_window,
            )
            raise_auth_error(
                "AUTH_0001",
                f"Timestamp outside {self.timestamp_window}s window (diff: {time_diff}s)",
            )

        return timestamp

    async def validate_signature(self, request: Request) -> Dict:
        """
        Validate request signature and return service information.

        Issue #665: Refactored to use extracted helpers for header extraction
        and timestamp validation.

        Security checks:
        1. All required headers present
        2. Timestamp within allowed window (prevents replay attacks)
        3. Service exists in registry
        4. HMAC signature matches expected value

        Args:
            request: FastAPI request object

        Returns:
            Dict with service_id and timestamp

        Raises:
            HTTPException: 401 if authentication fails
        """
        # Step 1-2: Extract and validate headers + timestamp (Issue #665: uses helpers)
        service_id, signature, timestamp_str = self._extract_auth_headers(request)
        timestamp = self._validate_timestamp(timestamp_str, service_id)

        # Step 3: Get service key from Redis
        service_key = await self.get_service_key(service_id)
        if not service_key:
            logger.warning("Unknown service ID", service_id=service_id)
            raise_auth_error("AUTH_0004", f"Unknown service: {service_id}")

        # Step 4: Validate HMAC signature
        expected_sig = self.generate_signature(
            service_id, service_key, request.method, request.url.path, timestamp
        )

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning(
                "Invalid signature",
                service_id=service_id,
                method=request.method,
                path=request.url.path,
            )
            raise_auth_error("AUTH_0004", "Invalid signature")

        logger.info(
            "✅ Service authentication successful",
            service_id=service_id,
            method=request.method,
            path=request.url.path,
            timestamp=timestamp,
        )

        return {"service_id": service_id, "timestamp": timestamp, "authenticated": True}


async def validate_service_auth(request: Request) -> Dict:
    """
    Shared validation function used by both middleware types.

    This function is called by both logging and enforcement middleware
    to validate service authentication.

    Args:
        request: FastAPI request object

    Returns:
        Dict with service authentication information

    Raises:
        HTTPException: If authentication fails (used by enforcement middleware)
    """
    # Get Redis manager from app state or dependencies
    try:
        # Always use AsyncRedisManager for service auth (not RedisPoolManager from app state)
        pass

        # Get main Redis database for service key storage
        redis = await get_redis_client(async_client=True, database="main")

        # Create auth manager and validate
        auth_manager = ServiceAuthManager(redis)
        return await auth_manager.validate_signature(request)

    except HTTPException:
        # Re-raise HTTP exceptions (authentication failures)
        raise
    except Exception as e:
        logger.error(
            "Service auth validation error", error=str(e), path=request.url.path
        )
        raise_server_error("API_0003", f"Authentication service error: {str(e)}")
