# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
WorkingMemoryService — Redis-backed session-scoped short-term memory.

Each entry is stored under the key pattern:
    autobot:session:{session_id}:memory:{key}

Values are JSON-serialised and expire automatically after TTL seconds.
Uses the 'knowledge' Redis database (DATABASE_MAPPING["knowledge"]).
"""

import json
import logging
from typing import Any, List, Optional

from autobot_shared.redis_client import get_redis_client

from constants.ttl_constants import TTL_WORKING_MEMORY_DEFAULT

logger = logging.getLogger(__name__)

_KEY_PREFIX = "autobot:session:{session_id}:memory:{key}"
_SESSION_PATTERN = "autobot:session:{session_id}:memory:*"


def _make_key(session_id: str, key: str) -> str:
    return _KEY_PREFIX.format(session_id=session_id, key=key)


class WorkingMemoryService:
    """Session-scoped working memory backed by Redis with TTL support."""

    def __init__(self) -> None:
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            self._redis = await get_redis_client(async_client=True, database="knowledge")
        return self._redis

    async def store(
        self,
        session_id: str,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> None:
        """Serialise *value* to JSON and store it with an expiry.

        Args:
            session_id: Unique session identifier.
            key: Entry key within the session namespace.
            value: JSON-serialisable value to store.
            ttl: TTL in seconds; defaults to TTL_WORKING_MEMORY_DEFAULT.
        """
        try:
            expire = ttl if ttl is not None else TTL_WORKING_MEMORY_DEFAULT
            redis = await self._get_redis()
            redis_key = _make_key(session_id, key)
            payload = json.dumps(value, ensure_ascii=False)
            await redis.set(redis_key, payload, ex=expire)
            logger.debug("working_memory.store session=%s key=%s ttl=%s", session_id, key, expire)
        except Exception as exc:
            logger.warning("working_memory.store failed: %s", exc)
            raise

    async def get(self, session_id: str, key: str) -> Optional[Any]:
        """Retrieve and deserialise a stored value.

        Returns:
            Deserialised value, or *None* if the key is missing or expired.
        """
        try:
            redis = await self._get_redis()
            raw = await redis.get(_make_key(session_id, key))
            if raw is None:
                return None
            return json.loads(raw)
        except Exception as exc:
            logger.warning("working_memory.get failed: %s", exc)
            raise

    async def list(self, session_id: str) -> List[str]:
        """Return all live entry *keys* (suffix only) for *session_id*.

        Uses SCAN to avoid blocking the Redis event loop.
        """
        try:
            redis = await self._get_redis()
            pattern = _SESSION_PATTERN.format(session_id=session_id)
            prefix_len = len(f"autobot:session:{session_id}:memory:")
            keys: List[str] = []
            async for raw_key in redis.scan_iter(match=pattern):
                decoded = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
                keys.append(decoded[prefix_len:])
            return keys
        except Exception as exc:
            logger.warning("working_memory.list failed: %s", exc)
            raise

    async def clear(self, session_id: str) -> int:
        """Delete all working-memory entries for *session_id*.

        Returns:
            Number of keys deleted.
        """
        try:
            redis = await self._get_redis()
            pattern = _SESSION_PATTERN.format(session_id=session_id)
            keys = [k async for k in redis.scan_iter(match=pattern)]
            if not keys:
                return 0
            deleted = await redis.delete(*keys)
            logger.debug("working_memory.clear session=%s deleted=%s", session_id, deleted)
            return deleted
        except Exception as exc:
            logger.warning("working_memory.clear failed: %s", exc)
            raise


__all__ = ["WorkingMemoryService"]
