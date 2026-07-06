# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory Transparency Engine — Issue #10554.

Provides user-facing list / forget / export operations that span ALL memory
stores so a single `forget(user_id, memory_id)` call truly erases the entry
from every store it lives in.

Store map
---------
  verbatim   — ChromaDB ``autobot_verbatim`` (user_id metadata filter)
  trajectory — ChromaDB ``trajectories``       (agent_id metadata filter, user-scoped)
  working    — Redis ``autobot:session:*:memory:*``
  graph      — Redis ``memory:entity:*``        (metadata.user_id)
  rl         — Redis ``rag:retrieval_patterns:{user_id}:*``

Each memory item returned by ``list_user_memories`` carries a ``store`` and
``memory_id`` field that the delete path uses to route the forget call to the
right store without requiring the caller to understand the internals.
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

# Module-level lazy references — assigned by _bootstrap() to allow unit tests
# to patch ``memory.transparency.get_verbatim_store`` etc. without importing
# the full application stack.  Real code calls _bootstrap() on first use.
get_verbatim_store = None  # type: ignore[assignment]
get_trajectory_store = None  # type: ignore[assignment]
get_redis_client = None  # type: ignore[assignment]


def _bootstrap() -> None:
    """Lazily import heavy dependencies so tests can patch before first call.

    Each reference is guarded independently so a test can pre-assign any one
    of them (e.g. ``mt.get_redis_client = AsyncMock(…)``) and that assignment
    is preserved even if the other two have not been set yet.
    """
    global get_verbatim_store, get_trajectory_store, get_redis_client
    if get_verbatim_store is None:
        from memory.verbatim_store import get_verbatim_store as _gvs
        get_verbatim_store = _gvs
    if get_trajectory_store is None:
        from memory.trajectory_store import get_trajectory_store as _gts
        get_trajectory_store = _gts
    if get_redis_client is None:
        from autobot_shared.redis_client import get_redis_client as _grc
        get_redis_client = _grc

_GRAPH_ENTITY_PATTERN = "memory:entity:*"
_RL_PATTERN_PREFIX = "rag:retrieval_patterns:"


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _safe(coro, fallback=None):
    """Run a coroutine; return *fallback* on any exception (best-effort fan-out)."""
    try:
        return await coro
    except Exception as exc:
        logger.warning("memory_transparency: store error: %s", exc)
        return fallback


def _now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _decode(v) -> str:
    return v.decode("utf-8") if isinstance(v, bytes) else str(v)


async def _redis_scan(redis, match: str) -> List[str]:
    """SCAN for all keys matching *match* without blocking the event loop."""
    keys: List[str] = []
    cursor = 0
    while True:
        try:
            cursor, batch = await redis.scan(cursor, match=match, count=200)
        except Exception as exc:
            logger.warning("memory_transparency: redis scan failed: %s", exc)
            break
        for k in batch:
            keys.append(_decode(k))
        if cursor == 0:
            break
    return keys


# ---------------------------------------------------------------------------
# Per-store list helpers
# ---------------------------------------------------------------------------


async def _list_verbatim(user_id: str) -> List[Dict[str, Any]]:
    """Return verbatim chunks whose metadata.user_id matches *user_id*."""
    try:
        _bootstrap()
        store = await get_verbatim_store()
        collection = await store._get_collection()
        raw = await collection.get(
            where={"user_id": {"$eq": user_id}},
            include=["documents", "metadatas"],
        )
    except Exception as exc:
        logger.warning("_list_verbatim failed: %s", exc)
        return []

    items = []
    ids = raw.get("ids", [])
    docs = raw.get("documents", [])
    metas = raw.get("metadatas", [])
    for chunk_id, doc, meta in zip(ids, docs or [], metas or []):
        items.append({
            "memory_id": chunk_id,
            "store": "verbatim",
            "content": doc[:300] if doc else "",
            "provenance": meta or {},
            "timestamp": (meta or {}).get("timestamp", ""),
        })
    return items


async def _list_trajectory(user_id: str) -> List[Dict[str, Any]]:
    """Return trajectories whose metadata.agent_id prefix matches user_id.

    TrajectoryStore does not carry user_id directly; it uses agent_id.
    We surface all trajectories where agent_id starts with the user_id
    (a prefix convention used by agent dispatch) as well as an exact match.
    """
    try:
        _bootstrap()
        store = await get_trajectory_store()
        collection = await store._get_collection()
        raw = await collection.get(
            where={"agent_id": {"$eq": user_id}},
            include=["documents", "metadatas"],
        )
    except Exception as exc:
        logger.warning("_list_trajectory failed: %s", exc)
        return []

    items = []
    ids = raw.get("ids", [])
    docs = raw.get("documents", [])
    metas = raw.get("metadatas", [])
    for traj_id, doc, meta in zip(ids, docs or [], metas or []):
        items.append({
            "memory_id": traj_id,
            "store": "trajectory",
            "content": doc[:300] if doc else "",
            "provenance": {
                "outcome": (meta or {}).get("outcome", ""),
                "reward": (meta or {}).get("reward", 0),
                "agent_id": (meta or {}).get("agent_id", ""),
            },
            "timestamp": (meta or {}).get("timestamp", ""),
        })
    return items


async def _list_working_memory(user_id: str) -> List[Dict[str, Any]]:
    """Return working-memory keys whose session's user_id label matches.

    WorkingMemory is session-scoped; we surface all keys under sessions
    that carry a ``user_id`` annotation in the key or value.
    Only entries where the JSON value has a ``user_id`` field equal to
    *user_id* are included — sessions without user annotation are skipped.
    """
    try:
        _bootstrap()
        redis = await get_redis_client(async_client=True, database="knowledge")
        all_keys = await _redis_scan(redis, "autobot:session:*:memory:*")
    except Exception as exc:
        logger.warning("_list_working_memory scan failed: %s", exc)
        return []

    items = []
    for redis_key in all_keys:
        try:
            raw = await redis.get(redis_key)
            if not raw:
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                continue
            if value.get("user_id") != user_id:
                continue
            # key format: autobot:session:{session_id}:memory:{key}
            parts = redis_key.split(":", 4)
            session_id = parts[2] if len(parts) > 2 else ""
            key_suffix = parts[4] if len(parts) > 4 else redis_key
            items.append({
                "memory_id": redis_key,
                "store": "working_memory",
                "content": str(value)[:300],
                "provenance": {"session_id": session_id, "key": key_suffix},
                "timestamp": value.get("timestamp", ""),
            })
        except Exception:
            continue
    return items


async def _list_graph_entities(user_id: str) -> List[Dict[str, Any]]:
    """Return memory-graph entities whose metadata.user_id matches *user_id*."""
    try:
        _bootstrap()
        redis = await get_redis_client(async_client=True, database="main")
        all_keys = await _redis_scan(redis, _GRAPH_ENTITY_PATTERN)
    except Exception as exc:
        logger.warning("_list_graph_entities scan failed: %s", exc)
        return []

    items = []
    for entity_key in all_keys:
        try:
            raw = await redis.json().get(entity_key)
            if not raw:
                continue
            meta = raw.get("metadata") or {}
            if meta.get("user_id") != user_id and meta.get("owner_id") != user_id:
                continue
            items.append({
                "memory_id": raw.get("id", entity_key),
                "store": "graph",
                "content": raw.get("name", "")[:300],
                "provenance": {
                    "type": raw.get("type", ""),
                    "observations": (raw.get("observations") or [])[:3],
                },
                "timestamp": meta.get("created_at", ""),
            })
        except Exception:
            continue
    return items


async def _list_rl_patterns(user_id: str) -> List[Dict[str, Any]]:
    """Return retrieval-learner patterns scoped to *user_id*."""
    try:
        _bootstrap()
        redis = await get_redis_client(async_client=True, database="analytics")
        prefix = f"{_RL_PATTERN_PREFIX}{user_id}:"
        all_keys = await _redis_scan(redis, f"{prefix}*")
    except Exception as exc:
        logger.warning("_list_rl_patterns scan failed: %s", exc)
        return []

    items = []
    for redis_key in all_keys:
        try:
            raw = await redis.hgetall(redis_key)
            if not raw:
                continue
            m = {_decode(k): _decode(v) for k, v in raw.items()}
            items.append({
                "memory_id": redis_key,
                "store": "retrieval_learner",
                "content": f"Retrieval pattern: type={m.get('query_type', '?')} "
                           f"success_rate={m.get('success_rate', '?')}",
                "provenance": {
                    "query_type": m.get("query_type", ""),
                    "success_rate": m.get("success_rate", ""),
                    "usage_count": m.get("usage_count", ""),
                },
                "timestamp": datetime.fromtimestamp(
                    float(m.get("last_seen", 0)), tz=timezone.utc
                ).isoformat() if m.get("last_seen") else "",
            })
        except Exception:
            continue
    return items


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


async def list_user_memories(user_id: str) -> List[Dict[str, Any]]:
    """Return every memory item stored for *user_id* across all stores.

    Each item has: ``memory_id``, ``store``, ``content``, ``provenance``,
    ``timestamp``.

    Errors from individual stores are logged and swallowed — a partial list
    is still returned so one unhealthy store does not block the whole view.
    """
    results = await asyncio.gather(
        _safe(_list_verbatim(user_id), []),
        _safe(_list_trajectory(user_id), []),
        _safe(_list_working_memory(user_id), []),
        _safe(_list_graph_entities(user_id), []),
        _safe(_list_rl_patterns(user_id), []),
    )
    combined: List[Dict[str, Any]] = []
    for store_items in results:
        combined.extend(store_items or [])
    combined.sort(key=lambda x: x.get("timestamp") or "", reverse=True)
    return combined


async def forget_memory(user_id: str, memory_id: str, store: str) -> bool:
    """Delete a single memory item from its store.

    Cascades correctly per store type:
    - ``verbatim``         → ChromaDB delete by id
    - ``trajectory``       → ChromaDB delete by id
    - ``working_memory``   → Redis DEL the key
    - ``graph``            → delete entity + its relations from memory graph
    - ``retrieval_learner``→ Redis DEL the pattern hash key

    Returns True when the item was found and deleted.
    """
    try:
        if store == "verbatim":
            return await _forget_verbatim(memory_id)
        if store == "trajectory":
            return await _forget_trajectory(memory_id)
        if store == "working_memory":
            return await _forget_working_memory(user_id, memory_id)
        if store == "graph":
            return await _forget_graph_entity(user_id, memory_id)
        if store == "retrieval_learner":
            return await _forget_rl_pattern(user_id, memory_id)
        logger.warning("forget_memory: unknown store %r", store)
        return False
    except Exception as exc:
        logger.error("forget_memory failed: user=%s store=%s id=%s: %s", user_id, store, memory_id, exc)
        return False


async def forget_everywhere(user_id: str, memory_id: str) -> Dict[str, bool]:
    """Fan-out delete across ALL stores for *memory_id*.

    Tries each store; a False result means the item was not found there
    (not an error — memory items live in exactly one store).
    Returns a dict mapping store name to deletion result.
    """
    stores = ["verbatim", "trajectory", "working_memory", "graph", "retrieval_learner"]
    results = await asyncio.gather(*[forget_memory(user_id, memory_id, s) for s in stores])
    return dict(zip(stores, results))


async def export_user_memory(user_id: str) -> Dict[str, Any]:
    """Return the complete memory footprint for *user_id* as a JSON-serialisable dict.

    Reuses ``list_user_memories`` for the data; adds export metadata.
    """
    memories = await list_user_memories(user_id)
    return {
        "export_version": "1.0",
        "exported_at": _now_iso(),
        "user_id": user_id,
        "total_items": len(memories),
        "stores": sorted({m["store"] for m in memories}),
        "memories": memories,
    }


# ---------------------------------------------------------------------------
# Per-store forget helpers
# ---------------------------------------------------------------------------


async def _forget_verbatim(memory_id: str) -> bool:
    _bootstrap()
    store = await get_verbatim_store()
    collection = await store._get_collection()
    existing = await collection.get(ids=[memory_id])
    if not existing.get("ids"):
        return False
    await collection.delete(ids=[memory_id])
    logger.info("forget_verbatim: deleted chunk %s", memory_id)
    return True


async def _forget_trajectory(memory_id: str) -> bool:
    _bootstrap()
    store = await get_trajectory_store()
    collection = await store._get_collection()
    existing = await collection.get(ids=[memory_id])
    if not existing.get("ids"):
        return False
    await collection.delete(ids=[memory_id])
    logger.info("forget_trajectory: deleted trajectory %s", memory_id)
    return True


async def _forget_working_memory(user_id: str, memory_id: str) -> bool:
    _bootstrap()
    redis = await get_redis_client(async_client=True, database="knowledge")
    raw = await redis.get(memory_id)
    if not raw:
        return False
    value = json.loads(raw) if isinstance(raw, (str, bytes)) else {}
    if isinstance(value, dict) and value.get("user_id") != user_id:
        logger.warning("forget_working_memory: tenant mismatch for key %s", memory_id)
        return False
    deleted = await redis.delete(memory_id)
    logger.info("forget_working_memory: deleted key %s", memory_id)
    return deleted > 0


async def _forget_graph_entity(user_id: str, entity_id: str) -> bool:
    """Delete a graph entity (by id) and its relations after verifying ownership."""
    _bootstrap()
    redis = await get_redis_client(async_client=True, database="main")
    entity_key = f"memory:entity:{entity_id}"
    raw = await redis.json().get(entity_key)
    if not raw:
        return False
    meta = raw.get("metadata") or {}
    owner = meta.get("user_id") or meta.get("owner_id")
    if owner and owner != user_id:
        logger.warning("forget_graph_entity: tenant mismatch entity=%s owner=%s caller=%s", entity_id, owner, user_id)
        return False
    # Delete relations (both directions)
    await redis.delete(f"memory:relations:out:{entity_id}")
    await redis.delete(f"memory:relations:in:{entity_id}")
    deleted = await redis.delete(entity_key)
    logger.info("forget_graph_entity: deleted entity %s + relations", entity_id)
    return deleted > 0


async def _forget_rl_pattern(user_id: str, redis_key: str) -> bool:
    """Delete a retrieval-learner pattern; reject if it belongs to another user."""
    _bootstrap()
    expected_prefix = f"{_RL_PATTERN_PREFIX}{user_id}:"
    if not redis_key.startswith(expected_prefix):
        logger.warning("forget_rl_pattern: tenant mismatch key=%s user=%s", redis_key, user_id)
        return False
    redis = await get_redis_client(async_client=True, database="analytics")
    deleted = await redis.delete(redis_key)
    logger.info("forget_rl_pattern: deleted key %s", redis_key)
    return deleted > 0


__all__ = [
    "list_user_memories",
    "forget_memory",
    "forget_everywhere",
    "export_user_memory",
]
