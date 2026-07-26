# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_COLLECTION_NAME = "autobot_verbatim"
_DEFAULT_LIMIT = 10
_DEFAULT_RETENTION_DAYS: int = 90  # override via memory.verbatim.retention_days config

# B1 (#12555): optional MemPalace-style symbolic "drawer" index. An inverted
# term -> chunk_id index in Redis lets an entity/keyword query resolve candidate
# chunks in one lookup and rank them lexically, skipping the ANN embed+search on
# the hot path. Default OFF — merged flag-on only if the micro-benchmark shows a
# latency win with no recall regression (see benchmarks/verbatim_symbolic_benchmark.py).
_SYMBOLIC_INDEX_ENABLED: bool = os.environ.get("AUTOBOT_VERBATIM_SYMBOLIC_INDEX", "0").lower() in (
    "1",
    "true",
    "yes",
)
_SYM_TERM_KEY = "autobot:vsym:term:{term}"  # set of chunk_ids containing the term
_SYM_CHUNK_KEY = "autobot:vsym:chunk:{chunk_id}"  # reverse: set of terms (for cleanup)
_SYM_MAX_TERMS_PER_CHUNK = 32  # cap so a huge turn can't bloat the index
_SYM_RECENCY_WEIGHT = 0.2  # blend recency into the lexical rank (mirrors search)
# A broad term (e.g. a common word) can union to thousands of chunks. Rather than
# fetch them all from ChromaDB, treat an over-broad match as "not an entity query"
# and fall back to semantic search.
_SYM_MAX_CANDIDATES = 200

# Minimal stopword set — mirrors query_processor._extract_keywords intent without
# coupling to that private module. Salient-term extraction, not full NLP.
_SYM_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "was",
        "were",
        "you",
        "your",
        "our",
        "their",
        "with",
        "that",
        "this",
        "have",
        "has",
        "had",
        "not",
        "but",
        "can",
        "will",
        "would",
        "should",
        "could",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "how",
        "did",
        "does",
        "about",
        "from",
        "into",
        "out",
        "get",
        "got",
        "let",
        "its",
        "it's",
        "they",
        "them",
        "then",
        "than",
    }
)


def _extract_terms(text: str) -> set:
    """Salient alphanumeric terms (len>2, non-stopword) for the symbolic index."""
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in tokens if len(t) > 2 and t not in _SYM_STOPWORDS}


# Recency-weighted re-ranking (GH#11163). Verbatim recall blends semantic
# similarity with an exponential recency decay so recent turns surface over
# equally-similar stale ones. Tunable per deployment; weight 0.0 disables the
# blend entirely (pure semantic order — prior behaviour).
_RECENCY_WEIGHT: float = float(os.environ.get("AUTOBOT_VERBATIM_RECENCY_WEIGHT", "0.2"))
_RECENCY_HALFLIFE_SECONDS: float = float(
    os.environ.get("AUTOBOT_VERBATIM_RECENCY_HALFLIFE_SECONDS", str(7 * 24 * 3600))
)


def _recency_factor(timestamp_iso: str | None, now: datetime) -> float | None:
    """Exponential-decay recency score in ``[0, 1]`` from an ISO timestamp.

    ``1.0`` for a just-now turn, halving every ``_RECENCY_HALFLIFE_SECONDS``.
    Returns ``None`` when the timestamp is missing or unparseable so the caller
    falls back to the pure semantic score for that chunk.
    """
    if not timestamp_iso:
        return None
    try:
        ts = datetime.fromisoformat(timestamp_iso)
    except (ValueError, TypeError):
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age = (now - ts).total_seconds()
    if age <= 0:
        return 1.0
    return 0.5 ** (age / _RECENCY_HALFLIFE_SECONDS)


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
        if _SYMBOLIC_INDEX_ENABLED:
            await self._index_symbolic(chunk_id, text)
        logger.debug("VerbatimStore.append: stored chunk %s", chunk_id)
        return chunk_id

    # ------------------------------------------------------------------
    # B1 (#12555): symbolic drawer index (opt-in, default off)
    # ------------------------------------------------------------------

    async def _index_symbolic(self, chunk_id: str, text: str) -> None:
        """Add ``chunk_id`` to the inverted term index. Best-effort, never raises.

        Writes ``term -> {chunk_id}`` sets plus a reverse ``chunk_id -> {terms}``
        set so ``delete_session`` can clean up without re-tokenising.
        """
        try:
            terms = list(_extract_terms(text))[:_SYM_MAX_TERMS_PER_CHUNK]
            if not terms:
                return
            from autobot_shared.redis_client import get_redis_client

            redis = await get_redis_client(database="knowledge")
            pipe = redis.pipeline()
            for term in terms:
                pipe.sadd(_SYM_TERM_KEY.format(term=term), chunk_id)
            pipe.sadd(_SYM_CHUNK_KEY.format(chunk_id=chunk_id), *terms)
            await pipe.execute()
        except Exception:
            logger.debug("VerbatimStore._index_symbolic failed (non-fatal)", exc_info=True)

    async def _deindex_symbolic(self, chunk_ids: List[str]) -> None:
        """Remove chunk_ids from the inverted index (called on delete). Best-effort."""
        if not chunk_ids:
            return
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = await get_redis_client(database="knowledge")
            for chunk_id in chunk_ids:
                chunk_key = _SYM_CHUNK_KEY.format(chunk_id=chunk_id)
                raw_terms = await redis.smembers(chunk_key)
                terms = [t.decode() if isinstance(t, bytes) else t for t in raw_terms]
                if not terms:
                    continue
                pipe = redis.pipeline()
                for term in terms:
                    pipe.srem(_SYM_TERM_KEY.format(term=term), chunk_id)
                pipe.delete(chunk_key)
                await pipe.execute()
        except Exception:
            logger.debug("VerbatimStore._deindex_symbolic failed (non-fatal)", exc_info=True)

    async def search_symbolic(
        self,
        query: str,
        session_filter: str | None = None,
        limit: int = _DEFAULT_LIMIT,
    ) -> List[Dict[str, Any]] | None:
        """Entity/keyword recall via the symbolic index — no ANN embed on the path.

        Resolves candidate chunks from the inverted term index, fetches them, and
        ranks by query-term overlap blended with recency. Returns ``None`` (not
        ``[]``) when the index is disabled, the query has no salient terms, or no
        candidate matched — so the caller can fall back to semantic ``search``.
        """
        if not _SYMBOLIC_INDEX_ENABLED:
            return None
        terms = _extract_terms(query)
        if not terms:
            return None
        try:
            from autobot_shared.redis_client import get_redis_client

            redis = await get_redis_client(database="knowledge")
            raw = await redis.sunion([_SYM_TERM_KEY.format(term=t) for t in terms])
        except Exception:
            logger.debug("VerbatimStore.search_symbolic union failed (non-fatal)", exc_info=True)
            return None
        candidate_ids = [c.decode() if isinstance(c, bytes) else c for c in raw]
        if not candidate_ids:
            return None
        # Over-broad match (a common term) → not a good entity query. Fall back to
        # semantic search rather than fetch thousands of chunks from ChromaDB.
        if len(candidate_ids) > _SYM_MAX_CANDIDATES:
            logger.debug(
                "search_symbolic: %d candidates exceed cap %d — deferring to semantic",
                len(candidate_ids),
                _SYM_MAX_CANDIDATES,
            )
            return None
        return await self._rank_symbolic_candidates(candidate_ids, terms, session_filter, limit)

    async def _rank_symbolic_candidates(
        self, candidate_ids: List[str], query_terms: set, session_filter: str | None, limit: int
    ) -> List[Dict[str, Any]]:
        """Fetch candidate chunks and rank by term-overlap blended with recency."""
        collection = await self._get_collection()
        got = await collection.get(ids=candidate_ids, include=["documents", "metadatas"])
        ids = got.get("ids", []) or []
        docs = got.get("documents", []) or []
        metas = got.get("metadatas", []) or []
        now = datetime.now(tz=timezone.utc)
        ranked: List[Dict[str, Any]] = []
        for cid, doc, meta in zip(ids, docs, metas):
            meta = meta or {}
            if session_filter and meta.get("session_id") != session_filter:
                continue
            doc_terms = _extract_terms(doc)
            overlap = len(query_terms & doc_terms) / len(query_terms) if query_terms else 0.0
            # Blend recency only when present — mirrors search()'s handling of a
            # missing/unparseable timestamp (skip, don't penalise the chunk).
            recency = _recency_factor(meta.get("timestamp"), now)
            if recency is not None:
                score = (1.0 - _SYM_RECENCY_WEIGHT) * overlap + _SYM_RECENCY_WEIGHT * recency
            else:
                score = overlap
            ranked.append({"id": cid, "text": doc, "score": score, "metadata": meta})
        ranked.sort(key=lambda c: c["score"], reverse=True)
        return ranked[:limit]

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

        now = datetime.now(tz=timezone.utc)
        chunks = []
        for chunk_id, doc, meta, dist in zip(ids, docs, metas, distances):
            semantic = 1.0 - dist
            score = semantic
            # GH#11163: blend recency so newer turns beat equally-similar stale
            # ones. Skipped when disabled (weight 0) or the timestamp is absent.
            if _RECENCY_WEIGHT > 0.0:
                recency = _recency_factor((meta or {}).get("timestamp"), now)
                if recency is not None:
                    score = (1.0 - _RECENCY_WEIGHT) * semantic + _RECENCY_WEIGHT * recency
            chunks.append(
                {
                    "id": chunk_id,
                    "text": doc,
                    "score": score,
                    "metadata": meta,
                }
            )
        # ChromaDB returns distance order; the recency blend can reorder, so
        # re-rank by the final score (stable no-op when weight is 0).
        chunks.sort(key=lambda c: c["score"], reverse=True)
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
        existing_ids = existing.get("ids", [])
        count = len(existing_ids)

        if count > 0:
            await collection.delete(where=where)
            if _SYMBOLIC_INDEX_ENABLED:
                await self._deindex_symbolic(existing_ids)
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
