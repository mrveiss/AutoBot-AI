# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Data Access tool handlers for Redis MCP Bridge (15 tools).

Issue #2511: get/set, hash, list, sorted set, stream, scan, type, ttl, delete.
All handlers use autobot_shared.redis_client — no direct redis.Redis().
"""

import logging
from typing import Any, Dict, List, Optional

from autobot_shared.redis_client import get_redis_client
from type_defs.common import Metadata

logger = logging.getLogger(__name__)

# Maximum keys returned by scan to prevent unbounded responses
_SCAN_MAX_KEYS = 100


def _decode(value):
    """Decode bytes to UTF-8 string, pass through other types."""
    return value.decode("utf-8") if isinstance(value, bytes) else value


async def _get_client(database: str = "main"):
    """Get an async Redis client for the given database."""
    return await get_redis_client(async_client=True, database=database)


# ---------------------------------------------------------------------------
# String operations
# ---------------------------------------------------------------------------


async def handle_redis_get(key: str, database: str = "main") -> Metadata:
    """Get a string value by key."""
    client = await _get_client(database)
    value = await client.get(key)
    return {
        "status": "success",
        "key": key,
        "value": value.decode("utf-8") if isinstance(value, bytes) else value,
        "exists": value is not None,
    }


async def handle_redis_set(
    key: str,
    value: str,
    ttl: Optional[int] = None,
    database: str = "main",
) -> Metadata:
    """Set a string value with optional TTL."""
    client = await _get_client(database)
    if ttl and ttl > 0:
        await client.setex(key, ttl, value)
    else:
        await client.set(key, value)
    return {"status": "success", "key": key, "ttl": ttl}


async def handle_redis_delete(keys: List[str], database: str = "main") -> Metadata:
    """Delete one or more keys."""
    client = await _get_client(database)
    deleted = await client.delete(*keys)
    return {
        "status": "success",
        "deleted_count": deleted,
        "keys": keys,
    }


# ---------------------------------------------------------------------------
# Hash operations
# ---------------------------------------------------------------------------


async def handle_redis_hget(key: str, field: str, database: str = "main") -> Metadata:
    """Get a single hash field."""
    client = await _get_client(database)
    value = await client.hget(key, field)
    return {
        "status": "success",
        "key": key,
        "field": field,
        "value": value.decode("utf-8") if isinstance(value, bytes) else value,
        "exists": value is not None,
    }


async def handle_redis_hgetall(key: str, database: str = "main") -> Metadata:
    """Get all fields and values from a hash."""
    client = await _get_client(database)
    raw = await client.hgetall(key)
    data = {
        (k.decode("utf-8") if isinstance(k, bytes) else k): (
            v.decode("utf-8") if isinstance(v, bytes) else v
        )
        for k, v in raw.items()
    }
    return {
        "status": "success",
        "key": key,
        "fields": data,
        "field_count": len(data),
    }


async def handle_redis_hset(
    key: str, mapping: Dict[str, Any], database: str = "main"
) -> Metadata:
    """Set one or more hash fields."""
    client = await _get_client(database)
    # Convert all values to strings for Redis
    str_mapping = {k: str(v) for k, v in mapping.items()}
    added = await client.hset(key, mapping=str_mapping)
    return {
        "status": "success",
        "key": key,
        "fields_added": added,
    }


# ---------------------------------------------------------------------------
# List operations
# ---------------------------------------------------------------------------


async def handle_redis_lrange(
    key: str, start: int = 0, stop: int = -1, database: str = "main"
) -> Metadata:
    """Get a range of list elements."""
    client = await _get_client(database)
    raw = await client.lrange(key, start, stop)
    items = [v.decode("utf-8") if isinstance(v, bytes) else v for v in raw]
    return {
        "status": "success",
        "key": key,
        "items": items,
        "count": len(items),
    }


async def handle_redis_lpush(
    key: str, values: List[str], database: str = "main"
) -> Metadata:
    """Push values to the left of a list."""
    client = await _get_client(database)
    length = await client.lpush(key, *values)
    return {"status": "success", "key": key, "list_length": length}


async def handle_redis_rpush(
    key: str, values: List[str], database: str = "main"
) -> Metadata:
    """Push values to the right of a list."""
    client = await _get_client(database)
    length = await client.rpush(key, *values)
    return {"status": "success", "key": key, "list_length": length}


# ---------------------------------------------------------------------------
# Sorted set operations
# ---------------------------------------------------------------------------


async def handle_redis_zrange(
    key: str,
    start: int = 0,
    stop: int = -1,
    withscores: bool = False,
    database: str = "main",
) -> Metadata:
    """Get a range from a sorted set."""
    client = await _get_client(database)
    raw = await client.zrange(key, start, stop, withscores=withscores)
    if withscores:
        items = [
            {
                "member": m.decode("utf-8") if isinstance(m, bytes) else m,
                "score": s,
            }
            for m, s in raw
        ]
    else:
        items = [v.decode("utf-8") if isinstance(v, bytes) else v for v in raw]
    return {
        "status": "success",
        "key": key,
        "items": items,
        "count": len(items),
    }


# ---------------------------------------------------------------------------
# Stream operations
# ---------------------------------------------------------------------------


async def handle_redis_xrange(
    key: str,
    start: str = "-",
    end: str = "+",
    count: Optional[int] = None,
    database: str = "main",
) -> Metadata:
    """Read stream entries."""
    client = await _get_client(database)
    kwargs: Dict[str, Any] = {}
    if count is not None:
        kwargs["count"] = count
    raw = await client.xrange(key, min=start, max=end, **kwargs)
    entries = [
        {"id": _decode(eid), "fields": {_decode(k): _decode(v) for k, v in f.items()}}
        for eid, f in raw
    ]
    return {
        "status": "success",
        "key": key,
        "entries": entries,
        "count": len(entries),
    }


async def handle_redis_xadd(
    key: str,
    fields: Dict[str, str],
    maxlen: Optional[int] = None,
    database: str = "main",
) -> Metadata:
    """Add an entry to a stream."""
    client = await _get_client(database)
    kwargs: Dict[str, Any] = {}
    if maxlen is not None:
        kwargs["maxlen"] = maxlen
        kwargs["approximate"] = True
    entry_id = await client.xadd(key, fields, **kwargs)
    decoded_id = entry_id.decode("utf-8") if isinstance(entry_id, bytes) else entry_id
    return {"status": "success", "key": key, "entry_id": decoded_id}


# ---------------------------------------------------------------------------
# Key inspection operations
# ---------------------------------------------------------------------------


async def handle_redis_scan_keys(
    pattern: str = "*",
    count: int = 100,
    database: str = "main",
) -> Metadata:
    """Scan keys matching a pattern (bounded to _SCAN_MAX_KEYS)."""
    client = await _get_client(database)
    keys: List[str] = []
    cursor = 0
    scan_count = min(count, _SCAN_MAX_KEYS)
    while True:
        cursor, batch = await client.scan(
            cursor=cursor, match=pattern, count=scan_count
        )
        for k in batch:
            keys.append(k.decode("utf-8") if isinstance(k, bytes) else k)
            if len(keys) >= _SCAN_MAX_KEYS:
                break
        if cursor == 0 or len(keys) >= _SCAN_MAX_KEYS:
            break
    return {
        "status": "success",
        "pattern": pattern,
        "keys": keys,
        "count": len(keys),
        "truncated": len(keys) >= _SCAN_MAX_KEYS,
    }


async def handle_redis_type(key: str, database: str = "main") -> Metadata:
    """Get the data type of a key."""
    client = await _get_client(database)
    key_type = await client.type(key)
    decoded = key_type.decode("utf-8") if isinstance(key_type, bytes) else key_type
    return {"status": "success", "key": key, "type": decoded}


async def handle_redis_ttl(key: str, database: str = "main") -> Metadata:
    """Get the TTL of a key."""
    client = await _get_client(database)
    ttl_val = await client.ttl(key)
    return {
        "status": "success",
        "key": key,
        "ttl": ttl_val,
        "has_expiry": ttl_val >= 0,
    }
