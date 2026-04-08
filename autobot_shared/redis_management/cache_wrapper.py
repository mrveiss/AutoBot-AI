# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
RedisCache - thin JSON-serialising wrapper around an async Redis client (#3547).

Eliminates the 336 inline json.loads / json.dumps calls that are repeated
across 80+ files whenever data is read from or written to Redis.

Usage::

    from autobot_shared.redis_management.cache_wrapper import RedisCache

    cache = RedisCache(redis_client, default_ttl=3600)

    # Store any JSON-serialisable value
    await cache.set_json("my:key", {"status": "ok"})

    # Read it back (returns None on miss or decode error)
    data = await cache.get_json("my:key")

    # Remove the key
    await cache.delete("my:key")
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class RedisCache:
    """Thin wrapper around an async Redis client that handles JSON serialization.

    All methods swallow Redis and JSON errors, log a warning, and return a
    safe fallback so callers never need to repeat try/except boilerplate for
    non-critical cache operations.

    Args:
        client:      An async Redis client (e.g. from ``get_redis_client(async_client=True)``).
        default_ttl: Default expiry in seconds applied to :meth:`set_json` when
                     the caller does not supply an explicit *ttl*.  Pass ``None``
                     to store without expiry.
    """

    def __init__(self, client: Any, default_ttl: Optional[int] = None) -> None:
        self._client = client
        self._default_ttl = default_ttl

    async def get_json(self, key: str, default: Any = None) -> Any:
        """Fetch *key* from Redis and JSON-decode the value.

        Args:
            key:     Redis key to look up.
            default: Value returned on cache miss or decode error (default: ``None``).

        Returns:
            Deserialised Python object, or *default* if the key is absent or
            the stored value cannot be decoded.
        """
        try:
            raw = await self._client.get(key)
            return json.loads(raw) if raw is not None else default
        except json.JSONDecodeError as exc:
            logger.warning("Cache get JSON decode failed for %s: %s", key, exc)
            return default
        except Exception as exc:
            logger.warning("Cache get failed for %s: %s", key, exc)
            return default

    async def set_json(
        self, key: str, data: Any, ttl: Optional[int] = None
    ) -> bool:
        """JSON-encode *data* and store it at *key* in Redis.

        Args:
            key:  Redis key to write.
            data: Any JSON-serialisable Python object.
            ttl:  Expiry in seconds.  Overrides *default_ttl* when supplied.
                  Pass ``0`` to store without expiry (overrides *default_ttl*).

        Returns:
            ``True`` on success, ``False`` if the operation failed.
        """
        try:
            ex = ttl if ttl is not None else self._default_ttl
            payload = json.dumps(data, ensure_ascii=False)
            if ex:
                await self._client.set(key, payload, ex=ex)
            else:
                await self._client.set(key, payload)
            return True
        except Exception as exc:
            logger.warning("Cache set failed for %s: %s", key, exc)
            return False

    async def delete(self, key: str) -> None:
        """Remove *key* from Redis.

        Failures are logged as warnings and silently ignored so callers do not
        need to handle them when a delete is best-effort.

        Args:
            key: Redis key to remove.
        """
        try:
            await self._client.delete(key)
        except Exception as exc:
            logger.warning("Cache delete failed for %s: %s", key, exc)
