# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-session token counters and the compaction failure marker (moved out of ``context_overflow``, #17802).

``context_overflow.py`` is over the file-size ceiling and may not grow; the tracker is self-contained, so it
lives here and ``context_overflow`` re-exports it by name.
"""

from typing import Dict, List

from autobot_shared.env_utils import env_int
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import decode_redis_value

logger = get_logger(__name__)

# Redis key prefixes
_TOKEN_TRACKER_KEY_PREFIX = "chat:tokens:"  # nosec B105  # Redis key prefix, not a password
_SUMMARY_MARKER_KEY_PREFIX = "chat:summary_marker:"

# How long to skip compaction after it fails, so a rate-limited provider costs
# one attempt per window instead of one per turn (#14065 review).
_SUMMARY_FAILURE_BACKOFF_SECONDS = env_int("AUTOBOT_SUMMARY_FAILURE_BACKOFF_SECONDS", 300)


class SessionTokenTracker:
    """Tracks cumulative token usage for chat sessions.

    Accumulates token counts from LLMResponse usage fields and persists
    to Redis so long-running conversations can track their context fill.

    Usage::

        tracker = SessionTokenTracker()
        await tracker.add_message_tokens(session_id, prompt_tokens=100, completion_tokens=50)
        usage = await tracker.get_session_usage(session_id)
        # {'total_tokens': 150, 'message_count': 1}
    """

    def __init__(self, ttl_seconds: int = 86400):
        """Initialize token tracker.

        Args:
            ttl_seconds: TTL for Redis keys (default 24h).
        """
        self.ttl_seconds = ttl_seconds
        self.redis = None

    async def _ensure_redis(self):
        """Lazy init Redis client."""
        if self.redis is None:
            self.redis = await get_async_redis_client()
        if self.redis is None:
            logger.warning("SessionTokenTracker: Redis unavailable, token tracking disabled")
        return self.redis

    async def add_message_tokens(
        self,
        session_id: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
    ) -> None:
        """Add token usage from a new message to session cumulative total.

        Args:
            session_id: Chat session identifier.
            prompt_tokens: Input token count.
            completion_tokens: Generated token count.
        """
        redis = await self._ensure_redis()
        if not redis:
            return

        key = f"{_TOKEN_TRACKER_KEY_PREFIX}{session_id}"
        total_tokens = prompt_tokens + completion_tokens

        try:
            # Atomic increment and expiry
            pipe = redis.pipeline()
            pipe.hincrby(key, "total_tokens", total_tokens)
            pipe.hincrby(key, "prompt_tokens", prompt_tokens)
            pipe.hincrby(key, "completion_tokens", completion_tokens)
            pipe.hincrby(key, "message_count", 1)
            # #17802: the prompt is the WHOLE history each turn and the reply joins it, so the context now held is
            # this turn's size, written (not added) -- the hincrby fields above stay as cumulative spend.
            pipe.hset(key, "active_tokens", total_tokens)
            pipe.expire(key, self.ttl_seconds)
            await pipe.execute()
        except Exception as e:
            logger.error("Failed to track tokens for session %s: %s", session_id, e)

    async def seed_session(self, session_id: str, token_counts: List[int]) -> None:
        """Start a just-reset session from the sizes of the messages it kept: their sum is the context held (#17802)."""
        redis = await self._ensure_redis()
        if not redis:
            return
        key = f"{_TOKEN_TRACKER_KEY_PREFIX}{session_id}"
        held = sum(token_counts)
        try:
            pipe = redis.pipeline()
            pipe.hincrby(key, "total_tokens", held)
            pipe.hincrby(key, "prompt_tokens", held)
            pipe.hincrby(key, "message_count", len(token_counts))
            pipe.hset(key, "active_tokens", held)
            pipe.expire(key, self.ttl_seconds)
            await pipe.execute()
        except Exception as e:
            logger.error("Failed to seed tokens for session %s: %s", session_id, e)

    async def get_session_usage(self, session_id: str) -> Dict[str, int]:
        """Get token usage for a session: cumulative spend, and ``active_tokens`` (the context held now).

        Args:
            session_id: Chat session identifier.

        Returns:
            Dict with total_tokens, prompt_tokens, completion_tokens, message_count, active_tokens.
            Returns zeros if no data exists.
        """
        redis = await self._ensure_redis()
        if not redis:
            return {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "message_count": 0,
                "active_tokens": 0,
            }

        key = f"{_TOKEN_TRACKER_KEY_PREFIX}{session_id}"
        try:
            data = await redis.hgetall(key)
            if not data:
                return {
                    "total_tokens": 0,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "message_count": 0,
                }

            # add_message_tokens hincrby's str field names and the shared client is
            # decode_responses=True, so hgetall yields str keys. Probing with bytes
            # literals always missed and every counter read back 0 (#13274).
            total = int(decode_redis_value(data.get("total_tokens")) or 0)
            active = decode_redis_value(data.get("active_tokens"))
            return {
                # A counter written before active_tokens existed has no such field: its spend is the best it has.
                "active_tokens": total if active is None else int(active),
                "total_tokens": total,
                "prompt_tokens": int(decode_redis_value(data.get("prompt_tokens")) or 0),
                "completion_tokens": int(decode_redis_value(data.get("completion_tokens")) or 0),
                "message_count": int(decode_redis_value(data.get("message_count")) or 0),
            }
        except Exception as e:
            logger.error("Failed to get session usage for %s: %s", session_id, e)
            return {
                "total_tokens": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "message_count": 0,
                "active_tokens": 0,
            }

    async def reset_session(self, session_id: str) -> None:
        """Reset token tracking for a session (after summarization).

        Args:
            session_id: Chat session identifier.
        """
        redis = await self._ensure_redis()
        if not redis:
            return

        key = f"{_TOKEN_TRACKER_KEY_PREFIX}{session_id}"
        try:
            await redis.delete(key)
        except Exception as e:
            logger.error("Failed to reset session %s: %s", session_id, e)

    async def mark_summarization_failed(self, session_id: str) -> None:
        """Back off compaction for this session after a failure (#14065 review).

        Without this, a failing provider wedges the session permanently.
        Compaction is awaited *inline* on the chat request path, under the
        ``chat_timeout`` budget (``api/chat.py``), and the token tracker is
        correctly left un-reset on failure — so fill never drops and every
        subsequent turn spends the same time failing the same way, timing out a
        turn whose answer was already generated and stored.

        The marker bounds that to one attempt per backoff window. It is
        deliberately best-effort: with Redis down the marker cannot be written,
        and retrying every turn is the safer of the two failures.
        """
        redis = await self._ensure_redis()
        if not redis:
            return

        try:
            await redis.setex(f"{_SUMMARY_MARKER_KEY_PREFIX}{session_id}", _SUMMARY_FAILURE_BACKOFF_SECONDS, "failed")
        except Exception as e:
            logger.error("Failed to mark summarization failure for session %s: %s", session_id, e)

    async def summarization_recently_failed(self, session_id: str) -> bool:
        """True while the backoff window from a previous failure is still open."""
        redis = await self._ensure_redis()
        if not redis:
            return False

        try:
            return bool(await redis.exists(f"{_SUMMARY_MARKER_KEY_PREFIX}{session_id}"))
        except Exception as e:
            logger.error("Failed to read summarization marker for session %s: %s", session_id, e)
            return False


__all__ = ["SessionTokenTracker"]
