# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Owner-scoped session list/read over the VerbatimStore (#11137).

A *session* is the set of verbatim chunks sharing ``metadata.session_id``. Every read here puts
``metadata.user_id == owner`` in the ChromaDB ``where`` itself (never a post-filter), so another
owner's session is indistinguishable from a missing one. There is deliberately no unscoped
variant: ``owner_id`` is a required plain string, and chunks stored without a ``user_id`` are
invisible to these reads (the same rule the memory graph applies to un-owned entities, #18825).
"""

from __future__ import annotations

from typing import Any, Dict, List

from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: Most chunks one session read returns, and the most a listing scans (env-tunable).
SESSION_READ_MAX_CHUNKS: int = env_int_clamped("AUTOBOT_MEMORY_SESSION_READ_MAX_CHUNKS", 500, min_v=1, max_v=100_000)
SESSION_LIST_MAX_SCAN: int = env_int_clamped("AUTOBOT_MEMORY_SESSION_LIST_MAX_SCAN", 5000, min_v=1, max_v=1_000_000)
SESSION_LIST_DEFAULT_LIMIT: int = env_int_clamped("AUTOBOT_MEMORY_SESSION_LIST_LIMIT", 50, min_v=1, max_v=10_000)


def _owner_where(owner_id: str, session_id: str | None = None) -> Dict[str, Any]:
    """The ChromaDB filter: the owner's chunks, optionally of one session."""
    if not isinstance(owner_id, str) or not owner_id:
        raise ValueError("owner_id must be a non-empty string")
    owner = {"user_id": {"$eq": owner_id}}
    if session_id is None:
        return owner
    return {"$and": [owner, {"session_id": {"$eq": session_id}}]}


def _summarise(metas: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Group chunk metadata into per-session summaries, newest session first."""
    sessions: Dict[str, Dict[str, Any]] = {}
    for meta in metas:
        sid = (meta or {}).get("session_id")
        if not sid:
            continue
        stamp = meta.get("timestamp", "")
        entry = sessions.setdefault(sid, {"session_id": sid, "chunks": 0, "first_at": stamp, "last_at": stamp})
        entry["chunks"] += 1
        entry["first_at"] = min(entry["first_at"], stamp) if stamp else entry["first_at"]
        entry["last_at"] = max(entry["last_at"], stamp)
    return sorted(sessions.values(), key=lambda s: s["last_at"], reverse=True)


async def list_sessions(store: Any, owner_id: str, limit: int = SESSION_LIST_DEFAULT_LIMIT) -> List[Dict[str, Any]]:
    """The owner's sessions (id, chunk count, first/last timestamp), newest first."""
    collection = await store._get_collection()
    raw = await collection.get(where=_owner_where(owner_id), include=["metadatas"], limit=SESSION_LIST_MAX_SCAN)
    return _summarise(raw.get("metadatas") or [])[: max(1, limit)]


def _turn_order(chunk: Dict[str, Any]) -> tuple:
    meta = chunk["metadata"]
    return (meta.get("turn", 0), meta.get("timestamp", ""), chunk["id"])


async def read_session(store: Any, owner_id: str, session_id: str) -> List[Dict[str, Any]]:
    """The owner's chunks of ``session_id`` in turn order; empty when the session is not theirs."""
    collection = await store._get_collection()
    raw = await collection.get(
        where=_owner_where(owner_id, session_id),
        include=["documents", "metadatas"],
        limit=SESSION_READ_MAX_CHUNKS,
    )
    rows = zip(raw.get("ids") or [], raw.get("documents") or [], raw.get("metadatas") or [])
    chunks = [{"id": i, "text": d, "metadata": m or {}} for i, d, m in rows]
    return sorted(chunks, key=_turn_order)
