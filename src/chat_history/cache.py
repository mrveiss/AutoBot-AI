# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Chat History Cache Mixin - Redis caching operations.

Provides caching functionality for chat sessions:
- Async session caching in Redis
- Cache key management
- TTL handling
"""

import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class CacheMixin:
    """
    Mixin providing Redis caching operations for chat sessions.

    Requires base class to have:
    - self.redis_client: Redis client or None
    """

    async def _async_cache_session(self, cache_key: str, chat_data: Dict[str, Any]):
        """
        Cache session data in Redis asynchronously.

        Args:
            cache_key: Redis key for the session
            chat_data: Session data to cache
        """
        try:
            # Redis sync client expects sync operations
            self.redis_client.setex(
                cache_key, 3600, json.dumps(chat_data, ensure_ascii=False)  # 1 hour TTL
            )
        except Exception as e:
            logger.error(f"Failed to cache session data: {e}")
