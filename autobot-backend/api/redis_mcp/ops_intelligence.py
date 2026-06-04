# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Ops Intelligence tool handlers for Redis MCP Bridge (6 tools).

Issue #2511: server_info, dbsize, memory_stats, stream_health, client_list, slowlog.
Agents can chain these tools for composite diagnostics.
"""

from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import decode_redis_value as _decode
from type_defs.common import Metadata

logger = get_logger(__name__)


async def _get_client(database: str = "main"):
    """Get an async Redis client for ops queries."""
    return await get_async_redis_client(database=database)


async def handle_redis_server_info(section: str | None = None, database: str = "main") -> Metadata:
    """Get Redis server stats."""
    client = await _get_client(database)
    if section:
        info = await client.info(section)
    else:
        info = await client.info()
    # info() returns a dict — stringify nested values for JSON
    cleaned = _stringify_info(info)
    return {"status": "success", "info": cleaned}


async def handle_redis_dbsize(database: str = "main") -> Metadata:
    """Get key count in the current database."""
    client = await _get_client(database)
    size = await client.dbsize()
    return {"status": "success", "database": database, "key_count": size}


async def handle_redis_memory_stats(database: str = "main") -> Metadata:
    """Get detailed memory analysis."""
    client = await _get_client(database)
    info = await client.info("memory")
    return {
        "status": "success",
        "used_memory_human": info.get("used_memory_human", "unknown"),
        "used_memory_peak_human": info.get("used_memory_peak_human", "unknown"),
        "used_memory_rss_human": info.get("used_memory_rss_human", "unknown"),
        "mem_fragmentation_ratio": info.get("mem_fragmentation_ratio"),
        "mem_allocator": info.get("mem_allocator", "unknown"),
        "total_system_memory_human": info.get("total_system_memory_human", "unknown"),
    }


async def handle_redis_stream_health(key: str, database: str = "main") -> Metadata:
    """Check stream health: length, groups, pending, last ID."""
    client = await _get_client(database)
    try:
        info = await client.xinfo_stream(key)
    except Exception as e:
        if "no such key" in str(e).lower():
            return {
                "status": "error",
                "message": f"Stream '{key}' does not exist",
                "code": "STREAM_NOT_FOUND",
            }
        raise

    result: Dict[str, Any] = {
        "status": "success",
        "key": key,
        "length": info.get("length", 0),
        "first_entry": _format_stream_entry(info.get("first-entry")),
        "last_entry": _format_stream_entry(info.get("last-entry")),
    }

    # Consumer group info
    try:
        groups = await client.xinfo_groups(key)
        result["groups"] = [
            {
                "name": _decode(g.get("name")),
                "consumers": g.get("consumers", 0),
                "pending": g.get("pending", 0),
                "last_delivered_id": _decode(g.get("last-delivered-id")),
            }
            for g in groups
        ]
    except Exception:
        result["groups"] = []

    return result


async def handle_redis_client_list(database: str = "main") -> Metadata:
    """List connected Redis clients (admin only)."""
    client = await _get_client(database)
    clients_raw = await client.client_list()
    # Limit to first 50 clients to avoid huge responses
    clients = clients_raw[:50]
    summary = [
        {
            "id": c.get("id"),
            "addr": c.get("addr"),
            "name": c.get("name", ""),
            "age": c.get("age"),
            "idle": c.get("idle"),
            "db": c.get("db"),
            "cmd": c.get("cmd"),
        }
        for c in clients
    ]
    return {
        "status": "success",
        "clients": summary,
        "total": len(clients_raw),
        "shown": len(summary),
    }


async def handle_redis_slowlog(count: int = 10, database: str = "main") -> Metadata:
    """Get recent slow queries (admin only)."""
    client = await _get_client(database)
    entries = await client.slowlog_get(count)
    formatted: List[Dict[str, Any]] = []
    for entry in entries:
        formatted.append(
            {
                "id": entry.get("id"),
                "timestamp": entry.get("start_time"),
                "duration_us": entry.get("duration"),
                "command": _decode(entry.get("command", b"")),
                "client_addr": _decode(entry.get("client_address", b"")),
            }
        )
    return {
        "status": "success",
        "entries": formatted,
        "count": len(formatted),
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _stringify_info(info: dict) -> dict:
    """Ensure all values in a Redis INFO dict are JSON-serializable."""
    result = {}
    for k, v in info.items():
        if isinstance(v, dict):
            result[k] = _stringify_info(v)
        elif isinstance(v, bytes):
            result[k] = v.decode("utf-8")
        else:
            result[k] = v
    return result


def _format_stream_entry(entry) -> Dict[str, Any] | None:
    """Format a stream entry tuple (id, fields) into a dict."""
    if not entry:
        return None
    entry_id, fields = entry
    decoded_id = _decode(entry_id)
    decoded_fields = {_decode(k): _decode(v) for k, v in fields.items()} if isinstance(fields, dict) else {}
    return {"id": decoded_id, "fields": decoded_fields}
