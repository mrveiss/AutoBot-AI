# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Rate Limiting Middleware

Prevents brute force password change attempts.
Issue #635.
"""

import logging
import uuid

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class RateLimitExceeded(Exception):
    """Raised when rate limit is exceeded."""


class PasswordChangeRateLimiter:
    """Rate limits password change attempts per user."""

    MAX_ATTEMPTS = 3  # Strict security
    WINDOW_SECONDS = 1800  # 30 minutes

    async def check_rate_limit(self, user_id: uuid.UUID) -> tuple[bool, int]:
        """
        Check if user has exceeded rate limit.

        Args:
            user_id: User ID to check

        Returns:
            (is_allowed, attempts_remaining)

        Raises:
            RateLimitExceeded: If limit exceeded
        """
        redis_client = get_redis_client(async_client=True, database="main")
        key = f"password_change_attempts:{user_id}"

        attempts = await redis_client.get(key)
        current = int(attempts) if attempts else 0

        if current >= self.MAX_ATTEMPTS:
            ttl = await redis_client.ttl(key)
            raise RateLimitExceeded(
                f"Too many attempts. Try again in {ttl // 60} minutes."
            )

        return True, self.MAX_ATTEMPTS - current
