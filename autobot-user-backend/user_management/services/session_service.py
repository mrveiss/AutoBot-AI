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
from typing import Optional

from autobot_shared.redis_client import get_redis_client

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

    async def invalidate_user_sessions(
        self, user_id: uuid.UUID, except_token: Optional[str] = None
    ) -> int:
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
        redis_client = get_redis_client(async_client=True, database="main")
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
        await redis_client.expire(key, 86400)  # 24 hours

        logger.info("Invalidated %d sessions for user %s", count, user_id)
        return count
