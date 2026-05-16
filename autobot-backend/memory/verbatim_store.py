# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
VerbatimStore — append-only conversational-memory lane backed by ChromaDB.

Issue #5070: Stores raw conversation chunks (user + assistant turns) in the
``autobot_verbatim`` ChromaDB collection so exact-word queries can retrieve
verbatim excerpts alongside the summarised knowledge base.

Design decisions:
- Append-only: ``append`` uses ``add`` (not ``upsert``) so duplicate-turn
  protection must live at the call site (fire-and-forget hook in manager.py).
- Hybrid search: ChromaDB ``query_texts`` path covers semantic similarity;
  the BM25 re-rank is provided by the caller (returns raw results here).
- Privacy: ``delete_session`` removes all chunks for a session (opt-out /
  retention enforcement).
- Collection is created lazily on first write so cold starts remain fast.
"""

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_COLLECTION_NAME = "autobot_verbatim"
_DEFAULT_LIMIT = 10
_DEFAULT_RETENTION_DAYS: int = 90  # override via memory.verbatim.retention_days config


class VerbatimStore:
    """Append-only verbatim conversation chunk store backed by ChromaDB.

    One instance per process is sufficient; all methods are async-safe and
    can be called concurrently.
    """

    def __init__(self) -> None:
        self._collection = None
        self._init_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_collection(self):
        """Lazily initialise and return the ChromaDB collection."""
        if self._collection is not None:
            return self._collection

        async with self._init_lock:
            if self._collection is not None:
                return self._collection

            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            self._collection = await client.get_or_create_collection(
                name=_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info("VerbatimStore: collection '%s' ready", _COLLECTION_NAME)
            return self._collection

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def append(
        self,
        session_id: str,
        turn: int,
        role: str,
        text: str,
        timestamp: datetime | None = None,
        user_id: str | None = None,
    ) -> str:
        """Store a single conversation chunk.

        Uses ChromaDB ``add`` (append-only semantics — duplicate chunk_id is a
        no-op per the BaseCollection contract, but callers must not rely on
        de-duplication).

        Args:
            session_id: Chat session identifier.
            turn: Zero-based turn counter within the session.
            role: ``"user"`` or ``"assistant"``.
            text: Raw text of the turn.
            timestamp: UTC datetime of the turn (defaults to now).
            user_id: Optional user identifier for privacy scoping.

        Returns:
            Chunk ID (``<session_id>_t<turn>_<role>``) stored in ChromaDB.
        """
        if not text or not text.strip():
            raise ValueError("text cannot be empty")
        if role not in {"user", "assistant"}:
            raise ValueError(f"role must be 'user' or 'assistant', got {role!r}")

        ts = timestamp or datetime.now(tz=timezone.utc)
        chunk_id = f"{session_id}_t{turn}_{role}_{uuid.uuid4().hex[:8]}"

        metadata: Dict[str, Any] = {
            "session_id": session_id,
            "turn": turn,
            "role": role,
            "timestamp": ts.isoformat(),
        }
        if user_id:
            metadata["user_id"] = user_id

        collection = await self._get_collection()
        await collection.add(
            ids=[chunk_id],
            documents=[text],
            metadatas=[metadata],
        )
        logger.debug("VerbatimStore.append: stored chunk %s", chunk_id)
        return chunk_id

    async def search(
        self,
        query: str,
        session_filter: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> List[Dict[str, Any]]:
        """Search verbatim chunks via ChromaDB's built-in vector + BM25 path.

        When ``session_filter`` is provided, results are restricted to that
        session.  ChromaDB ``query_texts`` triggers its internal embedding +
        ANN search; callers that need BM25 re-ranking should apply it on the
        returned list.

        Args:
            query: Free-text search query.
            session_filter: Optional session_id to scope results.
            limit: Maximum number of chunks to return.

        Returns:
            List of dicts with keys: ``id``, ``text``, ``score``, ``metadata``.
        """
        if not query or not query.strip():
            return []
        if limit <= 0:
            raise ValueError("limit must be positive")

        where: Dict[str, Any] | None = None
        if session_filter:
            where = {"session_id": {"$eq": session_filter}}

        collection = await self._get_collection()
        try:
            results = await collection.query(
                query_texts=[query],
                n_results=limit,
                where=where,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as exc:
            logger.error("VerbatimStore.search failed: %s", exc)
            return []

        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        chunks = []
        for chunk_id, doc, meta, dist in zip(ids, docs, metas, distances):
            chunks.append(
                {
                    "id": chunk_id,
                    "text": doc,
                    "score": 1.0 - dist,
                    "metadata": meta,
                }
            )
        return chunks

    async def delete_session(self, session_id: str) -> int:
        """Delete all verbatim chunks for a session (opt-out / retention).

        Args:
            session_id: Session whose chunks should be removed.

        Returns:
            Number of chunks deleted (approximate — based on pre-delete count).
        """
        if not session_id:
            raise ValueError("session_id cannot be empty")

        collection = await self._get_collection()
        where = {"session_id": {"$eq": session_id}}

        # Count before delete for the return value
        existing = await collection.get(
            where=where,
            include=["documents"],
        )
        count = len(existing.get("ids", []))

        if count > 0:
            await collection.delete(where=where)
            logger.info(
                "VerbatimStore.delete_session: removed %d chunks for session %s",
                count,
                session_id,
            )
        return count


# ---------------------------------------------------------------------------
# Module-level singleton (lazy, no constructor arguments needed)
# ---------------------------------------------------------------------------
_store: VerbatimStore | None = None
_store_lock = asyncio.Lock()


async def get_verbatim_store() -> VerbatimStore:
    """Return the process-wide VerbatimStore singleton (created on first call)."""
    global _store
    if _store is not None:
        return _store
    async with _store_lock:
        if _store is None:
            _store = VerbatimStore()
    return _store


__all__ = ["VerbatimStore", "get_verbatim_store"]
