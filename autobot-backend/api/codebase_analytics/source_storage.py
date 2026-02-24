# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis storage layer for the code source registry (#1133).

Uses the analytics Redis database (DB 11) with keys:
  code_source:{id}       — JSON-serialised CodeSource
  code_sources:index     — Set of all source IDs
"""

import logging
from typing import List, Optional

from .source_models import CodeSource, SourceAccess

logger = logging.getLogger(__name__)

_SOURCES_KEY_PREFIX = "code_source:"
_SOURCES_INDEX_KEY = "code_sources:index"


async def _get_redis():
    """Return an async Redis client for the analytics database."""
    from autobot_shared.redis_client import get_redis_client

    return await get_redis_client(database="analytics", async_client=True)


async def save_source(source: CodeSource) -> bool:
    """Persist a CodeSource to Redis.

    Stores JSON at code_source:{id} and adds the ID to the index set.
    Returns True on success, False if Redis is unavailable.
    """
    redis = await _get_redis()
    if redis is None:
        logger.error("Redis unavailable; cannot save source %s", source.id)
        return False
    key = f"{_SOURCES_KEY_PREFIX}{source.id}"
    await redis.set(key, source.model_dump_json())
    await redis.sadd(_SOURCES_INDEX_KEY, source.id)
    return True


# update_source is an alias — re-saving overwrites the existing record
update_source = save_source


async def get_source(source_id: str) -> Optional[CodeSource]:
    """Retrieve a CodeSource by ID. Returns None if not found."""
    redis = await _get_redis()
    if redis is None:
        return None
    key = f"{_SOURCES_KEY_PREFIX}{source_id}"
    data = await redis.get(key)
    if data is None:
        return None
    return CodeSource.model_validate_json(
        data.decode("utf-8") if isinstance(data, bytes) else data
    )


def _is_visible(source: CodeSource, owner_id: Optional[str]) -> bool:
    """Return True if the source should appear in the list for owner_id."""
    if owner_id is None:
        return True
    if source.owner_id == owner_id:
        return True
    if source.access == SourceAccess.PUBLIC:
        return True
    if source.access == SourceAccess.SHARED and owner_id in source.shared_with:
        return True
    return False


async def list_sources(owner_id: Optional[str] = None) -> List[CodeSource]:
    """Return all accessible code sources, optionally scoped to owner_id."""
    redis = await _get_redis()
    if redis is None:
        return []
    raw_ids = await redis.smembers(_SOURCES_INDEX_KEY)
    sources: List[CodeSource] = []
    for raw in raw_ids:
        sid = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        source = await get_source(sid)
        if source is not None and _is_visible(source, owner_id):
            sources.append(source)
    return sources


async def delete_source(source_id: str) -> bool:
    """Delete a CodeSource from Redis.

    Removes the key and clears the source from the index set.
    Returns True on success, False if Redis is unavailable.
    """
    redis = await _get_redis()
    if redis is None:
        return False
    key = f"{_SOURCES_KEY_PREFIX}{source_id}"
    await redis.delete(key)
    await redis.srem(_SOURCES_INDEX_KEY, source_id)
    return True
