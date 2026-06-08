# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Rate Limiting Middleware

Prevents brute force password change attempts.
Issue #635.

Delegates to the shared ``autobot_shared.rate_limiter.RateLimiter`` for the
core sliding-window logic (Issue #4460).
"""

import uuid

from autobot_shared.logging_manager import get_logger
from autobot_shared.rate_limiter import RateLimiter as _SharedRateLimiter
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# Shared delegate scoped to user rate-limit operations (Issue #4460).
# PasswordChangeRateLimiter uses Redis directly for its fixed-attempt counter
# semantics; the shared limiter is available for sliding-window checks
# elsewhere in the user_management middleware layer.
user_rate_limiter = _SharedRateLimiter(
    scope_prefix="user",
    default_tier="authenticated",
)


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
        redis_client = await get_async_redis_client(database="main")
        key = f"password_change_attempts:{user_id}"

        attempts = await redis_client.get(key)
        current = int(attempts) if attempts else 0

        if current >= self.MAX_ATTEMPTS:
            ttl = await redis_client.ttl(key)
            raise RateLimitExceeded(f"Too many attempts. Try again in {ttl // 60} minutes.")

        return True, self.MAX_ATTEMPTS - current

    async def record_attempt(self, user_id: uuid.UUID, success: bool) -> None:
        """
        Record password change attempt.

        Args:
            user_id: User ID
            success: Whether attempt was successful
        """
        redis_client = await get_async_redis_client(database="main")
        key = f"password_change_attempts:{user_id}"

        if success:
            # Clear attempts on success
            await redis_client.delete(key)
            logger.info("Cleared rate limit for user %s", user_id)
        else:
            # Increment failed attempts
            await redis_client.incr(key)
            await redis_client.expire(key, self.WINDOW_SECONDS)
            # codeql[py/clear-text-logging-sensitive-data]
            logger.warning("Failed password change attempt for user %s", user_id)
