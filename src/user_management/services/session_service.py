# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Service

Manages user sessions and JWT token invalidation via Redis blacklist.
Issue #635.
"""

import hashlib
import logging
import uuid

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


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

    async def add_token_to_blacklist(
        self, user_id: uuid.UUID, token: str, ttl: int = 86400
    ) -> None:
        """
        Add token to blacklist.

        Args:
            user_id: User whose token to blacklist
            token: JWT token to invalidate
            ttl: Time to live in seconds (default 24 hours)
        """
        redis_client = get_redis_client(async_client=True, database="main")
        key = f"session:blacklist:{user_id}"
        token_hash = self.hash_token(token)

        await redis_client.sadd(key, token_hash)
        await redis_client.expire(key, ttl)

        logger.info("Added token to blacklist for user %s", user_id)

    async def is_token_blacklisted(self, user_id: uuid.UUID, token: str) -> bool:
        """
        Check if token is blacklisted.

        Args:
            user_id: User whose token to check
            token: JWT token to verify

        Returns:
            True if token is blacklisted, False otherwise
        """
        redis_client = get_redis_client(async_client=True, database="main")
        key = f"session:blacklist:{user_id}"
        token_hash = self.hash_token(token)

        return await redis_client.sismember(key, token_hash)
