# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory ownership reassignment — Issue #11065.

When a user account is deleted the caller may redirect ownership of all the
user's memory records to a new owner so nothing is left orphaned (and therefore
un-forgettable after the #10989 IDOR fix made forget deny-by-default).

Public surface
--------------
    reassign_user_memory(old_user_id, new_owner_id) -> dict[str, int]

Returns a per-store count of records whose ownership was rewritten.  Errors
from individual stores are caught, logged, and counted as 0 — partial
reassignment must not abort account deletion.

Store coverage
--------------
  verbatim   — ChromaDB ``autobot_verbatim``; metadata ``user_id``
  trajectory — ChromaDB ``trajectories``; metadata ``user_id``
  working    — Redis database="knowledge" ``autobot:session:*:memory:*``; JSON ``user_id``
  graph      — Redis database="main" ``memory:entity:*``; JSON ``metadata.user_id`` / ``metadata.owner_id``

The retrieval-learner (rl) store uses Redis keys namespaced by user_id
(``rag:retrieval_patterns:{user_id}:*``).  Renaming them would require
delete-and-re-insert because Redis RENAME preserves the old key's TTL but
can race with concurrent reads.  The rl store is omitted here; its records
are scoped by key and become inaccessible once the user is gone — they will
expire naturally (short-lived hash entries) and do not block anyone else's
forget operations.
"""

import json
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from memory.working_memory import is_working_memory_key

logger = get_logger(__name__)

# Module-level lazy references — mirrors memory.transparency so tests can
# pre-assign any one of these without triggering the full import stack.
get_verbatim_store = None  # type: ignore[assignment]
get_trajectory_store = None  # type: ignore[assignment]
get_redis_client = None  # type: ignore[assignment]


def _bootstrap() -> None:
    """Lazily import heavy dependencies; mirrors memory.transparency._bootstrap."""
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


def _decode(v: Any) -> str:
    return v.decode("utf-8") if isinstance(v, bytes) else str(v)


async def _redis_scan(redis: Any, match: str) -> List[str]:
    """Non-blocking SCAN helper — mirrors memory.transparency._redis_scan."""
    keys: List[str] = []
    cursor = 0
    while True:
        try:
            cursor, batch = await redis.scan(cursor, match=match, count=200)
        except Exception as exc:
            logger.warning("ownership_reassign: redis scan error: %s", exc)
            break
        for k in batch:
            keys.append(_decode(k))
        if cursor == 0:
            break
    return keys


# ---------------------------------------------------------------------------
# Per-store reassign helpers
# ---------------------------------------------------------------------------


async def _reassign_chroma_store(store_name: str, get_store_fn: Any, field: str, old_id: str, new_id: str) -> int:
    """Rewrite *field* in ChromaDB metadata from *old_id* to *new_id*.

    Returns the count of records updated.
    """
    store = await get_store_fn()
    collection = await store._get_collection()

    raw = await collection.get(
        where={field: {"$eq": old_id}},
        include=["metadatas"],
    )
    ids: List[str] = raw.get("ids") or []
    metas: List[Dict] = raw.get("metadatas") or []

    if not ids:
        return 0

    # Build updated metadatas list: copy each dict, rewrite the target field.
    new_metas: List[Dict] = []
    for meta in metas:
        updated = dict(meta) if isinstance(meta, dict) else {}
        updated[field] = new_id
        new_metas.append(updated)

    await collection.update(ids=ids, metadatas=new_metas)
    logger.info(
        "ownership_reassign: %s — reassigned %d record(s) (field=%s) %s→%s",
        store_name,
        len(ids),
        field,
        old_id,
        new_id,
    )
    return len(ids)


async def _reassign_verbatim(old_id: str, new_id: str) -> int:
    """Reassign verbatim store records: metadata ``user_id``."""
    return await _reassign_chroma_store("verbatim", get_verbatim_store, "user_id", old_id, new_id)


async def _reassign_trajectory(old_id: str, new_id: str) -> int:
    """Reassign trajectory store records: metadata ``user_id``."""
    return await _reassign_chroma_store("trajectory", get_trajectory_store, "user_id", old_id, new_id)


async def _reassign_working_memory(old_id: str, new_id: str) -> int:
    """Reassign Redis working-memory JSON payloads whose ``user_id`` == *old_id*."""
    redis = await get_redis_client(async_client=True, database="knowledge")
    keys = await _redis_scan(redis, "autobot:session:*:memory:*")

    count = 0
    for key in keys:
        # Allowlist the key shape before any Redis op.
        if not is_working_memory_key(key):
            continue
        try:
            raw = await redis.get(key)
            if not raw:
                continue
            value = json.loads(raw)
            if not isinstance(value, dict) or value.get("user_id") != old_id:
                continue
            value["user_id"] = new_id
            await redis.set(key, json.dumps(value, ensure_ascii=False))
            count += 1
        except Exception as exc:
            logger.warning("ownership_reassign: working_memory key %s error: %s", key, exc)

    if count:
        logger.info("ownership_reassign: working_memory — reassigned %d key(s) %s→%s", count, old_id, new_id)
    return count


async def _reassign_graph_entities(old_id: str, new_id: str) -> int:
    """Reassign Redis graph entities whose metadata ``user_id`` or ``owner_id`` == *old_id*."""
    redis = await get_redis_client(async_client=True, database="main")
    keys = await _redis_scan(redis, "memory:entity:*")

    count = 0
    for entity_key in keys:
        try:
            raw = await redis.json().get(entity_key)
            if not raw:
                continue
            meta: Dict = raw.get("metadata") or {}
            changed = False
            if meta.get("user_id") == old_id:
                meta["user_id"] = new_id
                changed = True
            if meta.get("owner_id") == old_id:
                meta["owner_id"] = new_id
                changed = True
            if not changed:
                continue
            # Write back the updated metadata subtree only.
            await redis.json().set(entity_key, "$.metadata", meta)
            count += 1
        except Exception as exc:
            logger.warning("ownership_reassign: graph entity %s error: %s", entity_key, exc)

    if count:
        logger.info("ownership_reassign: graph — reassigned %d entity(ies) %s→%s", count, old_id, new_id)
    return count


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


async def reassign_user_memory(old_user_id: str, new_owner_id: str) -> Dict[str, int]:
    """Rewrite ownership from *old_user_id* to *new_owner_id* across all memory stores.

    Each store is guarded independently: an error in one store records 0 for
    that store and processing continues (partial reassignment must not crash
    account deletion).

    Args:
        old_user_id:  The user whose records are being rehomed.
        new_owner_id: The user who will take ownership of those records.

    Returns:
        A dict mapping store name to the number of records reassigned, e.g.::

            {"verbatim": 3, "trajectory": 0, "working_memory": 1, "graph": 2}
    """
    counts: Dict[str, int] = {
        "verbatim": 0,
        "trajectory": 0,
        "working_memory": 0,
        "graph": 0,
    }

    if not old_user_id or not old_user_id.strip():
        logger.warning("ownership_reassign: old_user_id is blank — no-op")
        return counts
    if not new_owner_id or not new_owner_id.strip():
        logger.warning("ownership_reassign: new_owner_id is blank — no-op")
        return counts
    if old_user_id == new_owner_id:
        logger.warning("ownership_reassign: old_user_id == new_owner_id (%s) — no-op", old_user_id)
        return counts

    _bootstrap()

    for store_name, coro_fn in [
        ("verbatim", lambda: _reassign_verbatim(old_user_id, new_owner_id)),
        ("trajectory", lambda: _reassign_trajectory(old_user_id, new_owner_id)),
        ("working_memory", lambda: _reassign_working_memory(old_user_id, new_owner_id)),
        ("graph", lambda: _reassign_graph_entities(old_user_id, new_owner_id)),
    ]:
        try:
            counts[store_name] = await coro_fn()
        except Exception as exc:
            logger.warning("ownership_reassign: store=%s raised unexpectedly: %s", store_name, exc)
            counts[store_name] = 0

    logger.info(
        "ownership_reassign: complete old=%s new=%s counts=%s",
        old_user_id,
        new_owner_id,
        counts,
    )
    return counts


__all__ = ["reassign_user_memory"]
