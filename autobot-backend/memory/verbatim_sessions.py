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

from typing import Any, Dict, List, Tuple

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
    """Group chunk metadata into per-session summaries, newest session first.

    An empty timestamp never becomes ``first_at``/``last_at`` while a real one exists.
    """
    sessions: Dict[str, Dict[str, Any]] = {}
    for meta in metas:
        sid = (meta or {}).get("session_id")
        if not sid:
            continue
        entry = sessions.setdefault(sid, {"session_id": sid, "chunks": 0, "first_at": "", "last_at": ""})
        entry["chunks"] += 1
        stamp = str(meta.get("timestamp") or "")
        if stamp:
            entry["first_at"] = min(entry["first_at"] or stamp, stamp)
            entry["last_at"] = max(entry["last_at"], stamp)
    return sorted(sessions.values(), key=lambda s: s["last_at"], reverse=True)


async def list_sessions(
    store: Any, owner_id: str, limit: int = SESSION_LIST_DEFAULT_LIMIT
) -> Tuple[List[Dict[str, Any]], bool]:
    """The owner's sessions, newest first, and whether the view is partial.

    Partial means the scan hit ``SESSION_LIST_MAX_SCAN`` chunks or more sessions exist than ``limit``.
    """
    collection = await store._get_collection()
    raw = await collection.get(where=_owner_where(owner_id), include=["metadatas"], limit=SESSION_LIST_MAX_SCAN + 1)
    metas = raw.get("metadatas") or []
    scan_truncated = len(metas) > SESSION_LIST_MAX_SCAN
    sessions = _summarise(metas[:SESSION_LIST_MAX_SCAN])
    cap = max(1, limit)
    return sessions[:cap], scan_truncated or len(sessions) > cap


def _turn_order(chunk: Dict[str, Any]) -> tuple:
    """Sort key tolerant of a missing or non-int ``turn`` (those sort last)."""
    meta = chunk["metadata"]
    turn = meta.get("turn")
    numbered = isinstance(turn, int) and not isinstance(turn, bool)
    return (not numbered, turn if numbered else 0, str(meta.get("timestamp", "")), str(chunk["id"]))


async def read_session(store: Any, owner_id: str, session_id: str) -> Tuple[List[Dict[str, Any]], bool]:
    """The owner's chunks of ``session_id`` in turn order, and whether the chunk cap cut it short."""
    collection = await store._get_collection()
    raw = await collection.get(
        where=_owner_where(owner_id, session_id),
        include=["documents", "metadatas"],
        limit=SESSION_READ_MAX_CHUNKS + 1,
    )
    rows = list(zip(raw.get("ids") or [], raw.get("documents") or [], raw.get("metadatas") or []))
    chunks = [{"id": i, "text": d, "metadata": m or {}} for i, d, m in rows[:SESSION_READ_MAX_CHUNKS]]
    return sorted(chunks, key=_turn_order), len(rows) > SESSION_READ_MAX_CHUNKS
