# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Terminal history service for persistent command history in Redis.
"""

import logging
import time
from typing import List

from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class TerminalHistoryService:
    """Manages persistent command history in Redis."""

    def __init__(self, max_entries: int = 10000):
        """Initialize history service.

        Args:
            max_entries: Maximum commands to store per user
        """
        self.redis = get_redis_client(database="main", async_client=True)
        self.max_entries = max_entries

    async def add_command(self, user_id: str, command: str) -> None:
        """Add command to history with current timestamp.

        Args:
            user_id: User identifier
            command: Command string to store
        """
        if not command.strip():
            return

        key = f"terminal:history:{user_id}"
        timestamp = time.time()

        await self.redis.zadd(key, {command: timestamp})

        count = await self.redis.zcard(key)
        if count > self.max_entries:
            await self.redis.zremrangebyrank(key, 0, count - self.max_entries - 1)

    async def get_history(
        self, user_id: str, limit: int = 100, offset: int = 0
    ) -> List[str]:
        """Get recent commands (most recent first).

        Args:
            user_id: User identifier
            limit: Maximum commands to return
            offset: Number of commands to skip

        Returns:
            List of command strings
        """
        key = f"terminal:history:{user_id}"
        return await self.redis.zrevrange(key, offset, offset + limit - 1)

    async def search_history(
        self, user_id: str, query: str, limit: int = 50
    ) -> List[str]:
        """Search history for commands containing query.

        Args:
            user_id: User identifier
            query: Search string
            limit: Maximum results

        Returns:
            Matching commands
        """
        all_commands = await self.get_history(user_id, limit=self.max_entries)
        matches = [cmd for cmd in all_commands if query in cmd]
        return matches[:limit]

    async def clear_history(self, user_id: str) -> None:
        """Clear all history for user.

        Args:
            user_id: User identifier
        """
        key = f"terminal:history:{user_id}"
        await self.redis.delete(key)
