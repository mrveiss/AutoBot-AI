# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Memory ownership reassignment — Issue #11065 / #11423.

When a user account is deleted the caller may redirect ownership of all the
user's memory records to a new owner so nothing is left orphaned (and therefore
un-forgettable after the #10989 IDOR fix made forget deny-by-default).

Public surface
--------------
    reassign_user_memory(old_user_id, new_owner_id) -> dict[str, int]

Returns a per-store count of records whose ownership was rewritten.  Errors
from individual stores are caught, logged, and counted as 0 — partial
reassignment must not abort account deletion.  The one exception is a failed
KB access-control epoch bump (``AclEpochBumpError``): KB records were rewritten
but the per-principal RAG caches still serve the old ownership, so it propagates.

Store coverage
--------------
  verbatim   — ChromaDB ``autobot_verbatim``; metadata ``user_id``
  trajectory — ChromaDB ``trajectories``; metadata ``user_id``
  working    — Redis database="knowledge" ``autobot:session:*:memory:*``; JSON ``user_id``
  graph      — Redis database="main" ``memory:entity:*``; JSON ``metadata.user_id`` / ``metadata.owner_id``
  kb_facts   — ChromaDB ``autobot_memory`` (KnowledgeBase singleton); metadata ``owner_id`` + ``user_id``
               Redis database="knowledge" ``user:kb:facts:{owner_id}`` (canonical) and
               ``user:facts:{owner_id}`` (legacy fallback path in facts.py)

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
from knowledge.acl_epoch import ACL_EPOCH_DATABASE, AclEpochBumpError, bump_acl_epoch_async
from memory._redis_util import redis_scan as _redis_scan
from memory.working_memory import is_working_memory_key

logger = get_logger(__name__)

# Module-level lazy references — same pattern as memory.transparency so tests
# can pre-assign any one of these without triggering the full import stack.
# NOTE: not shared with memory.transparency._bootstrap — this module also
# lazy-imports get_knowledge_base_fn (kb_facts store), which transparency
# does not use, so the two bootstraps import different symbol sets (#12694).
get_verbatim_store = None  # type: ignore[assignment]
get_trajectory_store = None  # type: ignore[assignment]
get_async_redis_client = None  # type: ignore[assignment]
get_knowledge_base_fn = None  # type: ignore[assignment]


def _bootstrap() -> None:
    """Lazily import heavy dependencies (same pattern as memory.transparency._bootstrap;
    see module-level NOTE above for why it is not shared)."""
    global get_verbatim_store, get_trajectory_store, get_async_redis_client, get_knowledge_base_fn
    if get_verbatim_store is None:
        from memory.verbatim_store import get_verbatim_store as _gvs

        get_verbatim_store = _gvs
    if get_trajectory_store is None:
        from memory.trajectory_store import get_trajectory_store as _gts

        get_trajectory_store = _gts
    if get_async_redis_client is None:
        from autobot_shared.redis_client import get_async_redis_client as _grc

        get_async_redis_client = _grc
    if get_knowledge_base_fn is None:
        from knowledge._composed import get_knowledge_base as _gkb

        get_knowledge_base_fn = _gkb


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
    redis = await get_async_redis_client(database="knowledge")
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
    redis = await get_async_redis_client(database="main")
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


async def _reassign_kb_facts_chroma(collection: Any, field: str, old_id: str, new_id: str) -> int:
    """Rewrite *field* in the KB ChromaDB collection from *old_id* to *new_id*.

    Returns count of records updated.  Shared by the ``owner_id`` and
    ``user_id`` passes inside ``_reassign_kb_facts``.
    """
    raw = await collection.get(
        where={field: {"$eq": old_id}},
        include=["metadatas"],
    )
    ids: List[str] = raw.get("ids") or []
    metas: List[Dict] = raw.get("metadatas") or []

    if not ids:
        return 0

    new_metas: List[Dict] = []
    for meta in metas:
        updated = dict(meta) if isinstance(meta, dict) else {}
        updated[field] = new_id
        new_metas.append(updated)

    await collection.update(ids=ids, metadatas=new_metas)
    logger.info(
        "ownership_reassign: kb_facts — reassigned %d record(s) (field=%s) %s→%s",
        len(ids),
        field,
        old_id,
        new_id,
    )
    return len(ids)


async def _move_redis_facts_index(redis: Any, old_key: str, new_key: str) -> None:
    """Move all members from *old_key* SET to *new_key* SET and delete *old_key*.

    Uses SUNIONSTORE so existing members in *new_key* are preserved (idempotent).
    """
    # SUNIONSTORE destination source [source ...] — merges into destination.
    await redis.sunionstore(new_key, old_key, new_key)
    await redis.delete(old_key)


async def _bump_kb_acl_epoch() -> None:
    """Orphan the per-principal RAG caches after a KB ownership rewrite (#16664).

    Raises ``AclEpochBumpError`` -- never logged and dropped: the caches would keep serving
    results filtered by the old ownership.
    """
    try:
        client = await get_async_redis_client(database=ACL_EPOCH_DATABASE)
    except Exception as exc:
        raise AclEpochBumpError(f"KB access-control epoch not bumped: {exc}") from exc
    await bump_acl_epoch_async(client)


async def _reassign_kb_facts(old_id: str, new_id: str) -> int:
    """Reassign KB facts ChromaDB collection metadata and Redis ownership indexes.

    ChromaDB: rewrites ``owner_id`` and ``user_id`` metadata fields (both may
    carry ownership depending on the write path — see ``facts.py:560``).

    Redis (database="knowledge"):
      - ``user:kb:facts:{old_id}`` → ``user:kb:facts:{new_id}`` (canonical,
        written by ``KnowledgeOwnership._set_owner_indexes``)
      - ``user:facts:{old_id}`` → ``user:facts:{new_id}`` (legacy fallback,
        written by ``facts.py:572`` when ownership manager is absent)

    Returns the total count of ChromaDB records reassigned across both fields.
    If the KB is unavailable this returns 0. Once any record was rewritten the ACL
    epoch is bumped, and a failed bump raises ``AclEpochBumpError``.
    """
    total = 0

    # --- ChromaDB ---
    try:
        kb = await get_knowledge_base_fn()
        collection = kb._async_chroma_collection
        if collection is None:
            logger.warning("ownership_reassign: kb_facts — _async_chroma_collection is None; skipping ChromaDB pass")
        else:
            # Reassign owner_id field (canonical ownership field)
            total += await _reassign_kb_facts_chroma(collection, "owner_id", old_id, new_id)
            # Reassign user_id field (fallback ownership field — both may coexist)
            total += await _reassign_kb_facts_chroma(collection, "user_id", old_id, new_id)
    except Exception as exc:
        logger.warning("ownership_reassign: kb_facts ChromaDB pass error: %s", exc)

    # --- Redis ownership indexes ---
    try:
        redis = await get_async_redis_client(database="knowledge")
        # Canonical index written by KnowledgeOwnership._set_owner_indexes
        await _move_redis_facts_index(redis, f"user:kb:facts:{old_id}", f"user:kb:facts:{new_id}")
        # Legacy fallback index written by facts.py when ownership_manager is absent
        await _move_redis_facts_index(redis, f"user:facts:{old_id}", f"user:facts:{new_id}")
    except Exception as exc:
        logger.warning("ownership_reassign: kb_facts Redis index pass error: %s", exc)

    if total:
        await _bump_kb_acl_epoch()  # after every write: a cached result keyed on the old epoch is stale
        logger.info(
            "ownership_reassign: kb_facts — total %d ChromaDB record(s) reassigned %s→%s", total, old_id, new_id
        )
    return total


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

            {"verbatim": 3, "trajectory": 0, "working_memory": 1, "graph": 2, "kb_facts": 4}

    Raises:
        AclEpochBumpError: KB facts were rewritten but the ACL epoch bump failed; a hard
            delete aborts on it (``_reassign_before_delete`` is fail-closed).
    """
    counts: Dict[str, int] = {
        "verbatim": 0,
        "trajectory": 0,
        "working_memory": 0,
        "graph": 0,
        "kb_facts": 0,
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
        ("kb_facts", lambda: _reassign_kb_facts(old_user_id, new_owner_id)),
    ]:
        try:
            counts[store_name] = await coro_fn()
        except AclEpochBumpError:
            raise  # records were rewritten but the RAG caches were not invalidated: report failure
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
