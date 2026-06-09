# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Session Service

Manages user sessions and JWT token invalidation via Redis blacklist.
Issue #635.
"""

import hashlib
import uuid

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)


class SessionService:
    """Manages user sessions and JWT token invalidation."""

    @staticmethod
    def hash_token(token: str) -> str:
        """
        Hash JWT token using SHA256.

        Args:
            token: JWT token string

        Returns:
            Hex string of SHA256 hash
        """
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def add_token_to_blacklist(self, user_id: uuid.UUID, token: str, ttl: int = TTL_24_HOURS) -> None:
        """
        Add token to blacklist.

        Args:
            user_id: User whose token to blacklist
            token: JWT token to invalidate
            ttl: Time to live in seconds (default 24 hours)
        """
        redis_client = await get_async_redis_client(database="main")
        key = f"session:blacklist:{user_id}"
        token_hash = self.hash_token(token)

        await redis_client.sadd(key, token_hash)
        await redis_client.expire(key, ttl)

        logger.info("Added token to blacklist for user %s", user_id)  # codeql[py/clear-text-logging-sensitive-data]

    async def is_token_blacklisted(self, user_id: uuid.UUID, token: str) -> bool:
        """
        Check if token is blacklisted.

        Args:
            user_id: User whose token to check
            token: JWT token to verify

        Returns:
            True if token is blacklisted, False otherwise
        """
        redis_client = await get_async_redis_client(database="main")
        key = f"session:blacklist:{user_id}"
        token_hash = self.hash_token(token)

        return await redis_client.sismember(key, token_hash)

    async def invalidate_user_sessions(self, user_id: uuid.UUID, except_token: str | None = None) -> int:
        """
        Invalidate all sessions for a user except the current one.

        Implementation:
        - Adds token hashes to Redis blacklist set
        - Key: session:blacklist:{user_id}
        - TTL: 24 hours (matches JWT expiry)
        - Excludes except_token hash to preserve current session

        Args:
            user_id: User whose sessions to invalidate
            except_token: Token to preserve (current session)

        Returns:
            Number of sessions invalidated
        """
        redis_client = await get_async_redis_client(database="main")
        key = f"session:blacklist:{user_id}"

        # Get existing token hashes (if any)
        existing_hashes = await redis_client.smembers(key) or set()

        # Compute except_token hash if provided
        except_hash = self.hash_token(except_token) if except_token else None

        # Add all existing tokens to blacklist except current
        count = 0
        for token_hash in existing_hashes:
            if token_hash != except_hash:
                await redis_client.sadd(key, token_hash)
                count += 1

        # Set expiry
        await redis_client.expire(key, TTL_24_HOURS)  # 24 hours

        logger.info("Invalidated %d sessions for user %s", count, user_id)
        return count
