# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal history service for persistent command history in Redis.
"""

import time
from typing import List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

logger = get_logger(__name__)


class TerminalHistoryService(AsyncRedisClientMixin):
    """Manages persistent command history in Redis."""

    _redis_database = "main"

    def __init__(self, max_entries: int = 10000) -> None:
        """Initialize history service.

        Args:
            max_entries: Maximum commands to store per user
        """
        self.max_entries = max_entries

    async def add_command(self, user_id: str, command: str) -> None:
        """Add command to history with current timestamp.

        Args:
            user_id: User identifier
            command: Command string to store
        """
        if not command.strip():
            return

        if not user_id or not user_id.strip():
            logger.warning("Invalid user_id provided to add_command")
            return

        key = f"terminal:history:{user_id}"
        timestamp = time.time()

        try:
            redis = await self._get_redis()
            if not redis:
                logger.error("Redis unavailable; cannot add command to history")
                return
            await redis.zadd(key, {command: timestamp})

            count = await redis.zcard(key)
            if count > self.max_entries:
                await redis.zremrangebyrank(key, 0, count - self.max_entries - 1)
        except Exception as e:
            logger.error("Failed to add command to history: %s", e)

    async def get_history(self, user_id: str, limit: int = 100, offset: int = 0) -> List[str]:
        """Get recent commands (most recent first).

        Args:
            user_id: User identifier
            limit: Maximum commands to return
            offset: Number of commands to skip

        Returns:
            List of command strings
        """
        if not user_id or not user_id.strip():
            logger.warning("Invalid user_id provided to get_history")
            return []

        key = f"terminal:history:{user_id}"
        try:
            redis = await self._get_redis()
            if not redis:
                return []
            return await redis.zrevrange(key, offset, offset + limit - 1)
        except Exception as e:
            logger.error("Failed to get history: %s", e)
            return []

    async def search_history(self, user_id: str, query: str, limit: int = 50) -> List[str]:
        """Search history for commands containing query.

        Args:
            user_id: User identifier
            query: Search string
            limit: Maximum results

        Returns:
            Matching commands
        """
        if not user_id or not user_id.strip():
            logger.warning("Invalid user_id provided to search_history")
            return []

        try:
            all_commands = await self.get_history(user_id, limit=self.max_entries)
            matches = [cmd for cmd in all_commands if query in cmd]
            return matches[:limit]
        except Exception as e:
            logger.error("Failed to search history: %s", e)
            return []

    async def clear_history(self, user_id: str) -> None:
        """Clear all history for user.

        Args:
            user_id: User identifier
        """
        if not user_id or not user_id.strip():
            logger.warning("Invalid user_id provided to clear_history")
            return

        key = f"terminal:history:{user_id}"
        try:
            redis = await self._get_redis()
            if not redis:
                return
            await redis.delete(key)
        except Exception as e:
            logger.error("Failed to clear history: %s", e)
