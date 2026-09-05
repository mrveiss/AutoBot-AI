# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
    """Rate limits password change attempts per target user, and per calling
    actor when the actor differs from the target.

    Issue #15743: a target-only key constrains repeated attempts against one
    victim, but not a caller walking many different target ids (the admin-
    reset path, since self-service always has actor == target). Both are
    enforced when an ``actor_id`` is supplied.
    """

    MAX_ATTEMPTS = 3  # Strict security
    WINDOW_SECONDS = 1800  # 30 minutes

    def _keys(self, user_id: uuid.UUID, actor_id: uuid.UUID | None) -> list[str]:
        """Redis keys to enforce for this attempt (#15743)."""
        keys = [f"password_change_attempts:{user_id}"]
        if actor_id is not None and actor_id != user_id:
            keys.append(f"password_change_attempts:by-caller:{actor_id}")
        return keys

    async def check_rate_limit(
        self,
        user_id: uuid.UUID,
        actor_id: uuid.UUID | None = None,
    ) -> tuple[bool, int]:
        """
        Check if the target or the calling actor has exceeded the limit.

        Args:
            user_id: Target user id being changed
            actor_id: Caller's own id, if known (#15743)

        Returns:
            (is_allowed, attempts_remaining)

        Raises:
            RateLimitExceeded: If either key is at or over the limit
        """
        redis_client = await get_async_redis_client(database="main")
        remaining = self.MAX_ATTEMPTS
        for key in self._keys(user_id, actor_id):
            attempts = await redis_client.get(key)
            current = int(attempts) if attempts else 0
            if current >= self.MAX_ATTEMPTS:
                ttl = await redis_client.ttl(key)
                raise RateLimitExceeded(f"Too many attempts. Try again in {ttl // 60} minutes.")
            remaining = min(remaining, self.MAX_ATTEMPTS - current)

        return True, remaining

    async def record_attempt(
        self,
        user_id: uuid.UUID,
        success: bool,
        actor_id: uuid.UUID | None = None,
    ) -> None:
        """
        Record a password change attempt against every enforced key.

        Args:
            user_id: Target user id being changed
            success: Whether the attempt succeeded
            actor_id: Caller's own id, if known (#15743)
        """
        redis_client = await get_async_redis_client(database="main")
        for key in self._keys(user_id, actor_id):
            if success:
                await redis_client.delete(key)
            else:
                await redis_client.incr(key)
                await redis_client.expire(key, self.WINDOW_SECONDS)

        if success:
            logger.info("Cleared rate limit for user %s", user_id)
        else:
            logger.warning("Failed password change attempt for user %s", user_id)
