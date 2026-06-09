# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Chat History Cache Mixin - Redis caching operations.

Provides caching functionality for chat sessions:
- Async session caching in Redis
- Cache key management
- TTL handling
"""

import json
from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from chat_history.file_io import run_in_chat_io_executor
from constants.ttl_constants import TTL_24_HOURS

logger = get_logger(__name__)


# #6743: chat:session:* cache TTL.
#
# Previously hard-coded to 3600 (1h) which silently dropped active conversations
# from Redis after an hour. Combined with the disk-fallback bug (#6744), that
# meant message data was permanently lost when the user left a tab open across
# lunch.
#
# Default raised to 24h to match the sibling chat:conversation:* TTL
# (chat_workflow/conversation.py uses self.conversation_history_ttl, also 24h
# by default). Override via env var when tuning memory pressure.
def _resolve_chat_session_cache_ttl() -> int:
    """Return TTL seconds for chat:session:* Redis keys."""
    raw = config.misc.chat_session_cache_ttl
    if raw is None:
        return TTL_24_HOURS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_CHAT_SESSION_CACHE_TTL=%r is not an integer; " "falling back to %ds (24h)",
            raw,
            TTL_24_HOURS,
        )
        return TTL_24_HOURS
    if value <= 0:
        logger.warning(
            "AUTOBOT_CHAT_SESSION_CACHE_TTL=%d must be positive; " "falling back to %ds (24h)",
            value,
            TTL_24_HOURS,
        )
        return TTL_24_HOURS
    return value


_CHAT_SESSION_CACHE_TTL = _resolve_chat_session_cache_ttl()


# #7570: chat:recent sorted set max-entries cap.
#
# The sorted set had no TTL and would grow without bound as sessions accumulated.
# We trim to the N most-recent entries immediately after each ZADD using
# ZREMRANGEBYRANK so the set never exceeds this limit.
#
# 1000 is well above any realistic concurrent-session count; lower it under
# memory pressure via AUTOBOT_CHAT_RECENT_MAX_ENTRIES.
_CHAT_RECENT_MAX_ENTRIES_DEFAULT = 1000


def _resolve_chat_recent_max_entries() -> int:
    """Return max members for the chat:recent sorted set."""
    raw = config.misc.chat_recent_max_entries
    if raw is None:
        return _CHAT_RECENT_MAX_ENTRIES_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "AUTOBOT_CHAT_RECENT_MAX_ENTRIES=%r is not an integer; " "falling back to %d",
            raw,
            _CHAT_RECENT_MAX_ENTRIES_DEFAULT,
        )
        return _CHAT_RECENT_MAX_ENTRIES_DEFAULT
    if value <= 0:
        logger.warning(
            "AUTOBOT_CHAT_RECENT_MAX_ENTRIES=%d must be positive; " "falling back to %d",
            value,
            _CHAT_RECENT_MAX_ENTRIES_DEFAULT,
        )
        return _CHAT_RECENT_MAX_ENTRIES_DEFAULT
    return value


_CHAT_RECENT_MAX_ENTRIES = _resolve_chat_recent_max_entries()


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
            # Issue #361 - avoid blocking
            # Issue #718 - Use dedicated executor to avoid blocking on saturated pool
            # #6743 - TTL configurable via AUTOBOT_CHAT_SESSION_CACHE_TTL
            await run_in_chat_io_executor(
                self.redis_client.setex,
                cache_key,
                _CHAT_SESSION_CACHE_TTL,
                json.dumps(chat_data, ensure_ascii=False),
            )
        except Exception as e:
            logger.error("Failed to cache session data: %s", e)
