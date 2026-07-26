# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Knowledge Base Facts Management Module

Contains the FactsMixin class for CRUD operations on facts including
store, retrieve, update, delete, and vectorization.
"""

import asyncio
import hashlib
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List

from autobot_shared.logging_manager import get_logger

if TYPE_CHECKING:
    import aioredis
    import redis
    from llama_index.core import VectorStoreIndex
    from llama_index.vector_stores.chroma import ChromaVectorStore

logger = get_logger(__name__)


# =============================================================================
# NPU-ACCELERATED EMBEDDING GENERATION (Issue #165)
# =============================================================================
# Cached state to avoid repeated imports and availability checks
# Note: Issue #5105 — duplicate embedding logic was removed; this module now
# delegates all embedding generation to services.npu_client which is the
# canonical NPU-first / Ollama-fallback path. The warmup helpers below are
# retained because lifespan.py calls them at startup (Issue #165).
_npu_client_cache: Any | None = None
_npu_available_cache: bool | None = None
_npu_cache_timestamp: float = 0.0

# Warmup state tracking
_npu_warmup_complete: bool = False
_npu_warmup_time_ms: float = 0.0


def _init_warmup_result() -> Dict[str, Any]:
    """Issue #665: Extracted from warmup_npu_connection to reduce function length.

    Initialize the warmup result dictionary with default values.

    Returns:
        Dict with default warmup status values
    """
    return {
        "status": "skipped",
        "npu_available": False,
        "warmup_time_ms": 0.0,
        "message": "",
    }


def _update_warmup_cache(client: Any, warmup_time: float) -> None:
    """Issue #665: Extracted from warmup_npu_connection to reduce function length."""
    global _npu_warmup_complete, _npu_warmup_time_ms
    global _npu_client_cache, _npu_available_cache, _npu_cache_timestamp
    import time

    _npu_warmup_time_ms = warmup_time
    _npu_warmup_complete = True
    _npu_client_cache = client
    _npu_available_cache = True
    _npu_cache_timestamp = time.time()


async def _build_warmup_success_result(embedding: List[float], warmup_time: float, client: Any) -> Dict[str, Any]:
    """Issue #665: Extracted from warmup_npu_connection to reduce function length."""
    result = {
        "status": "success",
        "npu_available": True,
        "warmup_time_ms": warmup_time,
        "embedding_dimensions": len(embedding),
        "message": f"NPU connection warmed up in {warmup_time:.1f}ms",
    }
    try:
        device_info = await client.get_device_info()
        if device_info:
            result.update(
                device=device_info.device_name,
                is_npu=device_info.is_npu,
                is_gpu=device_info.is_gpu,
            )
    except Exception:
        logger.debug("Suppressed exception in try block", exc_info=True)
    logger.info("NPU warmup complete: %d dimensions in %.1fms", len(embedding), warmup_time)
    return result


async def warmup_npu_connection() -> Dict[str, Any]:
    """Warm up the NPU worker connection by performing a test embedding.

    Issue #165: Called during backend startup (Phase 2) to eliminate
    first-request latency. Pre-initializes the HTTP connection pool
    and ensures the NPU worker's embedding model is ready.

    Returns:
        Dict with warmup status and timing information
    """
    import time

    start_time = time.time()
    result = _init_warmup_result()

    try:
        from services.npu_client import get_npu_client

        client = get_npu_client()
        if not await client.is_available(force_check=True):
            result.update(
                status="npu_unavailable",
                message="NPU worker not available, will use fallback",
            )
            logger.info("NPU warmup: Worker not available")
            return result

        embedding = await client.generate_embedding("NPU warmup test embedding for connection initialization")
        warmup_time = (time.time() - start_time) * 1000
        _update_warmup_cache(client, warmup_time)

        if embedding and len(embedding) > 0:
            result = await _build_warmup_success_result(embedding, warmup_time, client)
        else:
            result.update(
                status="empty_embedding",
                message="NPU returned empty embedding during warmup",
            )
            logger.warning("NPU warmup returned empty embedding")
    except Exception as e:
        result.update(
            status="error",
            warmup_time_ms=(time.time() - start_time) * 1000,
            message="NPU warmup failed",
        )
        logger.warning("NPU warmup failed: %s", e)

    return result


def get_npu_warmup_status() -> Dict[str, Any]:
    """
    Get NPU warmup status for diagnostics.

    Returns:
        Dict with warmup completion status and timing
    """
    return {
        "warmup_complete": _npu_warmup_complete,
        "warmup_time_ms": _npu_warmup_time_ms,
        "cache_valid": _npu_available_cache is not None,
        "npu_available": _npu_available_cache,
    }


async def _generate_embedding_with_npu_fallback(text: str, max_attempts: int = 1) -> List[float]:
    """Generate a single embedding via the canonical NPU-fallback path.

    Issue #5105: Thin shim — delegates to
    ``services.npu_client.generate_embedding_with_fallback`` which is the
    single source of truth for NPU-first / Ollama-fallback embedding
    generation. Prometheus counter
    ``autobot_embedding_generated_total{backend, status}`` is emitted by
    the canonical helper.

    Retained as a re-export so existing callers and unit tests that patch
    ``knowledge.facts._generate_embedding_with_npu_fallback`` keep working.

    Args:
        text: Text content to embed.
        max_attempts: Total attempts before giving up. Issue #12312: defaults to 1
            (fast-fail) so inline user-facing paths never stall behind a downed
            backend; the background reconcile path passes a higher count to retry.

    Returns:
        Embedding vector. Empty list if all backends fail (callers downstream
        in this module already tolerate empty/None embeddings via try/except).
    """
    from services.npu_client import generate_embedding_with_fallback

    embedding = await generate_embedding_with_fallback(text, max_attempts=max_attempts)
    return embedding or []


async def _generate_embeddings_batch_with_npu_fallback(
    texts: List[str],
) -> List[List[float]]:
    """Generate batch embeddings via the canonical NPU-fallback path.

    Issue #5105: Thin shim — delegates to
    ``services.npu_client.generate_embeddings_batch_with_fallback``.
    Filters ``None`` results out (canonical helper returns
    ``List[List[float] | None]`` to preserve index alignment; callers
    of this batch helper expect concrete vectors only).

    Args:
        texts: List of text contents to embed.

    Returns:
        List of embedding vectors (failed items dropped).
    """
    if not texts:
        return []

    from services.npu_client import generate_embeddings_batch_with_fallback

    raw = await generate_embeddings_batch_with_fallback(texts)
    return [vec for vec in raw if vec is not None]


def get_embedding_metrics() -> Dict[str, int]:
    """Return embedding-generation counts by backend.

    Issue #5105: Counters are now owned by ``services.npu_client`` and
    exposed via Prometheus (``autobot_embedding_generated_total``). This
    helper reads them from the registry for backwards compatibility with
    callers and tests that expect a plain dict.

    Returns:
        Dict with ``npu_count`` and ``fallback_count``. Returns zeros when
        ``prometheus_client`` is unavailable.
    """
    npu_count = 0
    fallback_count = 0
    try:
        from services import npu_client as _npu

        counter = getattr(_npu, "_embedding_generated", None)
        if counter is not None and hasattr(counter, "_metrics"):
            for label_values, child in counter._metrics.items():
                backend = label_values[0] if label_values else ""
                value = int(child._value.get())
                if backend == "npu":
                    npu_count += value
                elif backend == "ollama":
                    fallback_count += value
    except Exception:
        logger.debug("get_embedding_metrics: registry read failed", exc_info=True)
    return {"npu_count": npu_count, "fallback_count": fallback_count}


# A1 (#12552): fire-and-forget access-recording tasks are held here so the event
# loop keeps a strong reference until they finish (create_task otherwise GC-able).
_ACCESS_TASKS: "set[asyncio.Task]" = set()

# A1 (#12552): atomic usage bump. EXISTS + HINCRBY + HSET in one server-side
# round-trip so a concurrent delete_fact can never resurrect a ghost hash
# between the guard and the writes (both HINCRBY/HSET auto-create keys).
_ACCESS_BUMP_LUA = (
    "if redis.call('EXISTS', KEYS[1]) == 1 then "
    "redis.call('HINCRBY', KEYS[1], 'access_count', 1) "
    "redis.call('HSET', KEYS[1], 'last_accessed', ARGV[1]) "
    "return 1 end return 0"
)

def _env_int(name: str, default: int) -> int:
    """Parse an int env var, never raising at import — bad values fall back."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r — using default %s", name, raw, default)
        return default


def _env_float_safe(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        val = float(raw)
    except (TypeError, ValueError):
        logger.warning("Invalid %s=%r — using default %s", name, raw, default)
        return default
    return val if val == val else default  # reject NaN


# A3 (#12554): fact-lane consolidation thresholds. Conservative by design — see
# consolidate_facts for the full no-data-loss reasoning. A fact is prunable only
# if it is UNPROTECTED, low-quality, never recalled since instrumentation began
# (access_count == 0, A1 #12552), created AFTER the instrumentation epoch (so a
# 0 count is meaningful, not "predates A1"), and aged past the floor.
_FACTS_PRUNE_QUALITY_FLOOR: float = _env_float_safe("AUTOBOT_FACTS_PRUNE_QUALITY_FLOOR", 0.1)
_FACTS_PRUNE_MAX_AGE_DAYS: int = _env_int("AUTOBOT_FACTS_PRUNE_MAX_AGE_DAYS", 180)
_FACTS_PRUNE_SCAN_LIMIT: int = _env_int("AUTOBOT_FACTS_PRUNE_SCAN_LIMIT", 5000)
# Instrumentation epoch: ISO date A1 access-tracking began for THIS deployment.
# Facts created before it have unknown recall history → never pruned. UNSET =
# feature inert (no candidates) so an un-configured deploy can never mass-delete.
_FACTS_PRUNE_EPOCH: str = os.environ.get("AUTOBOT_FACTS_PRUNE_EPOCH", "").strip()
# Circuit breaker: if a single run would prune more than this many facts, refuse
# and log loudly — a healthy decay pass sheds a trickle, not thousands.
_FACTS_PRUNE_MAX_PER_RUN: int = _env_int("AUTOBOT_FACTS_PRUNE_MAX_PER_RUN", 100)


def _fact_is_protected(metadata: Dict[str, Any]) -> bool:
    """A fact that must never be auto-pruned (A3 #12554, no-data-loss invariant).

    Protected when owned (``owner_id``/``user_id``), human-verified, explicitly
    kept (``important``/``preserve``/``pinned``), or **curated/ingested** rather
    than ephemeral conversational cruft: a ``unique_key`` (e.g. man-page facts)
    or a ``source_connector_id`` (Confluence/Notion/web-crawl/... ingestion) marks
    knowledge a user deliberately brought in, which a low access_count must not
    condemn. Superset of the session-cleanup ``preserve_important`` predicate.
    """
    if metadata.get("important") or metadata.get("preserve") or metadata.get("pinned"):
        return True
    if metadata.get("owner_id") or metadata.get("user_id"):
        return True
    if metadata.get("unique_key") or metadata.get("source_connector_id"):
        return True
    return metadata.get("verification_status") == "verified"


def _parse_iso(value: Any) -> datetime | None:
    """Parse an ISO timestamp to an aware UTC datetime, or ``None`` if unusable."""
    if not value or not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    return ts.replace(tzinfo=timezone.utc) if ts.tzinfo is None else ts


def _apply_usage_fields(decoded: Dict[str, Any], metadata: Dict[str, Any]) -> None:
    """Surface authoritative usage counters from the Redis hash into metadata.

    A1 (#12552): ``access_count`` / ``last_accessed`` live as top-level hash
    fields (so ``HINCRBY`` stays atomic and the metadata JSON blob is never
    rewritten on access). They are the single source of truth; on read we copy
    them into the returned metadata dict, defaulting to 0 / "" when absent so
    every fact — old or new — exposes the keys.
    """
    try:
        metadata["access_count"] = int(decoded.get("access_count") or 0)
    except (TypeError, ValueError):
        metadata["access_count"] = 0
    metadata["last_accessed"] = decoded.get("last_accessed") or ""


def _decode_redis_hash(fact_data: Dict[bytes, bytes]) -> Dict[str, Any]:
    """Decode Redis hash bytes to strings and parse metadata (Issue #315: extracted).

    Args:
        fact_data: Raw Redis hash data with bytes keys/values

    Returns:
        Decoded dict with parsed metadata
    """
    decoded = {}
    for key, value in fact_data.items():
        k = key.decode("utf-8") if isinstance(key, bytes) else key
        v = value.decode("utf-8") if isinstance(value, bytes) else value
        decoded[k] = v

    # Parse metadata JSON if present
    if "metadata" in decoded:
        try:
            raw = decoded["metadata"]
            decoded["_parsed_metadata"] = raw if isinstance(raw, dict) else json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            decoded["_parsed_metadata"] = {}
    else:
        decoded["_parsed_metadata"] = {}

    return decoded


# ===== PROVENANCE HELPERS (Issue #1252) =====

#: Default provenance field values applied to every new fact/document.
_PROVENANCE_DEFAULTS: Dict[str, Any] = {
    "source_type": "manual_upload",
    "source_connector_id": None,
    "verification_status": "unverified",
    "verification_method": None,
    "verified_by": None,
    "verified_at": None,
    "quality_score": 0.0,
    "provenance_chain": [],
}


def _apply_provenance_defaults(metadata: Dict[str, Any]) -> None:
    """Inject provenance fields into metadata dict where not already set.

    Modifies *metadata* in place so callers that already carry partial
    provenance (e.g. librarian_assistant) retain their values.

    Issue #1252: Source Provenance Metadata.

    Args:
        metadata: Mutable metadata dict to enrich with provenance defaults.
    """
    for field, default in _PROVENANCE_DEFAULTS.items():
        if field not in metadata:
            metadata[field] = default


class FactsMixin:
    """
    Facts management mixin for knowledge base.

    Provides CRUD operations for individual facts:
    - Store new facts with vectorization
    - Retrieve facts by ID
    - Update existing facts
    - Delete facts
    - Get all facts with pagination
    - Vectorize existing unvectorized facts

    Key Features:
    - Duplicate detection via unique keys
    - Atomic counter updates (Issue #71)
    - ChromaDB vector storage
    - Metadata sanitization for ChromaDB compatibility
    """

    # Type hints for attributes from base class
    redis_client: "redis.Redis"
    _aioredis_client: "aioredis.Redis"
    vector_store: "ChromaVectorStore"
    vector_index: "VectorStoreIndex"
    initialized: bool
    embedding_model_name: str

    def _schedule_bm25_refresh(self) -> None:
        """Schedule a background BM25 corpus-stats recompute (#2033).

        Called after fact mutations so IDF values stay current.
        Uses ``asyncio.create_task`` to avoid blocking the caller.
        Callers performing bulk mutations should skip per-item calls
        and invoke this once after the batch completes (#2079).
        """
        # _get_keyword_searcher is defined on SearchMixin (same composed class)
        if not hasattr(self, "_get_keyword_searcher"):
            return
        try:
            searcher = self._get_keyword_searcher()
            asyncio.create_task(searcher.recompute_corpus_stats())
        except Exception as exc:
            logger.warning("BM25 stats refresh scheduling failed: %s", exc)

    async def _find_fact_by_unique_key(self, unique_key: str) -> Dict[str, Any] | None:
        """
        Find an existing fact by unique key (fast Redis SET lookup).
        Issue #315: Refactored to use helper for reduced nesting.

        Args:
            unique_key: The unique key to search for (e.g., "machine:os:command:section")

        Returns:
            Dict with fact info if found, None otherwise
        """
        try:
            # Check Redis SET for unique key mapping
            unique_key_name = "unique_key:man_page:%s" % unique_key
            fact_id = await asyncio.to_thread(self.redis_client.get, unique_key_name)

            if not fact_id:
                return None

            # Decode bytes if necessary
            if isinstance(fact_id, bytes):
                fact_id = fact_id.decode("utf-8")

            # Get the actual fact data
            fact_key = "fact:%s" % fact_id
            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)

            if not fact_data:
                return None

            # Use helper for decoding (Issue #315: extracted)
            decoded_data = _decode_redis_hash(fact_data)

            return {
                "fact_id": fact_id,
                "content": decoded_data.get("content", ""),
                "metadata": decoded_data.get("_parsed_metadata", {}),
            }

        except Exception as e:
            logger.debug("Error finding fact by unique key: %s", e)

        return None

    async def _find_existing_fact(self, content: str, metadata: Dict[str, Any]) -> str | None:
        """
        Check if a fact with identical content and metadata already exists.

        Args:
            content: Fact content
            metadata: Fact metadata

        Returns:
            Existing fact_id if found, None otherwise
        """
        try:
            # Create content hash for deduplication
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]

            # Check if hash exists in Redis
            hash_key = "content_hash:%s" % content_hash
            existing_id = await asyncio.to_thread(self.redis_client.get, hash_key)

            if existing_id:
                if isinstance(existing_id, bytes):
                    return existing_id.decode("utf-8")
                return existing_id

        except Exception as e:
            logger.debug("Error checking for existing fact: %s", e)

        return None

    async def _find_duplicate(self, content: str, threshold: float = 0.92) -> Dict[str, Any] | None:
        """Check ChromaDB for near-duplicate content before inserting.

        Issue #3788: Semantic similarity guard for individual fact writes.

        Queries the vector store for the closest existing fact. ChromaDB
        returns L2 distances; we convert to cosine similarity via
        ``1 - distance / 2`` (valid for unit-normalised embeddings).

        Args:
            content: Candidate fact text to check.
            threshold: Minimum similarity score to consider a duplicate (0.5-1.0).

        Returns:
            Metadata dict of the existing fact if a near-duplicate is found,
            else None.
        """
        if not self.vector_store:
            return None
        try:
            embedding = await _generate_embedding_with_npu_fallback(content)
            chroma_collection = self.vector_store._collection
            results = await asyncio.to_thread(
                chroma_collection.query,
                query_embeddings=[embedding],
                n_results=3,
                include=["metadatas", "distances"],
            )
            ids = (results.get("ids") or [[]])[0]
            distances = (results.get("distances") or [[]])[0]
            metadatas = (results.get("metadatas") or [[]])[0]
            for i, distance in enumerate(distances):
                similarity = 1.0 - distance / 2.0
                if similarity >= threshold:
                    meta = metadatas[i] if i < len(metadatas) else {}
                    meta.setdefault("id", ids[i] if i < len(ids) else "?")
                    logger.debug(
                        "_find_duplicate: similarity=%.4f >= threshold=%.4f, id=%s",
                        similarity,
                        threshold,
                        meta.get("id"),
                    )
                    return meta
        except Exception as exc:
            logger.debug("_find_duplicate: query failed, skipping check: %s", exc)
        return None

    async def _check_for_duplicates(self, content: str, metadata: Dict[str, Any]) -> Dict[str, Any] | None:
        """
        Check for duplicate facts by unique_key, content hash, or semantic similarity.

        Issue #281: Extracted helper for duplicate detection.
        Issue #3788: Added semantic similarity check via ChromaDB.

        Args:
            content: Fact content text
            metadata: Fact metadata dict

        Returns:
            Duplicate result dict if found, None otherwise
        """
        # Check for duplicates using unique_key if provided
        if "unique_key" in metadata:
            existing = await self._find_fact_by_unique_key(metadata["unique_key"])
            if existing:
                logger.info("Duplicate detected via unique_key: %s", metadata["unique_key"])
                return {
                    "status": "duplicate",
                    "fact_id": existing["fact_id"],
                    "message": "Fact already exists with this unique key",
                }

        # Check for content duplicates (exact hash match)
        existing_id = await self._find_existing_fact(content, metadata)
        if existing_id:
            logger.info("Duplicate content detected: %s", existing_id)
            return {
                "status": "duplicate",
                "fact_id": existing_id,
                "message": "Fact with identical content already exists",
            }

        # Issue #3788: Semantic similarity check against ChromaDB
        from autobot_shared.ssot_config import config as _cfg

        existing_meta = await self._find_duplicate(content, threshold=_cfg.cache.l2.kb_dedup_threshold)
        if existing_meta:
            dup_id = existing_meta.get("fact_id") or existing_meta.get("id", "?")
            logger.info("Near-duplicate fact detected via semantic check: %s", dup_id)
            return {
                "status": "duplicate",
                "fact_id": dup_id,
                "message": "Near-duplicate fact already exists (semantic similarity)",
            }

        return None

    async def _store_fact_in_redis(self, fact_id: str, content: str, metadata: Dict[str, Any]) -> None:
        """
        Store fact data in Redis with hash mappings.

        Issue #281: Extracted helper for Redis storage operations.
        Issue #547: Added session-fact relationship tracking for orphan cleanup.
        Issue #688: Added ownership index management for user-based access.

        Args:
            fact_id: Fact identifier
            content: Fact content text
            metadata: Fact metadata dict
        """
        # Store in Redis
        fact_key = "fact:%s" % fact_id
        await asyncio.to_thread(
            self.redis_client.hset,
            fact_key,
            mapping={
                "content": content,
                "metadata": json.dumps(metadata),
                "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            },
        )

        # Store content hash for deduplication
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
        await asyncio.to_thread(self.redis_client.set, "content_hash:%s" % content_hash, fact_id)

        # Store unique_key mapping if provided
        if "unique_key" in metadata:
            unique_key_name = "unique_key:man_page:%s" % metadata["unique_key"]
            await asyncio.to_thread(self.redis_client.set, unique_key_name, fact_id)

        # Issue #547: Track session-fact relationship for orphan cleanup
        source_session_id = metadata.get("source_session_id")
        if source_session_id:
            await self._track_session_fact_relationship(source_session_id, fact_id)

        # Issue #688: Track ownership indexes for user-based access control
        owner_id = metadata.get("owner_id") or metadata.get("user_id")
        if hasattr(self, "ownership_manager") and owner_id:
            await self.ownership_manager.set_owner(
                fact_id=fact_id,
                owner_id=owner_id,
                visibility=metadata.get("visibility", "private"),
                source_type=metadata.get("source_type", "manual"),
                shared_with=metadata.get("shared_with", []),
            )
        elif owner_id:
            # Issue #689: Fallback simple tracking when ownership manager
            # is not initialized
            await asyncio.to_thread(self.redis_client.sadd, "user:facts:%s" % owner_id, fact_id)

    async def _record_failed_vectorization(self, fact_id: str, reason: str) -> None:
        """Record a vectorization failure as queryable, retriable state (Issue #12312).

        Embedding generation can fail transiently (backend crash-loop, timeout). The
        fact content is already persisted; only its vector is missing. Rather than
        silently drop the vector (log-only, unrecoverable), mark the fact so it is:

        * **queryable** — ``vectorization_status=failed`` (plus error + timestamp) on
          the ``fact:<id>`` hash, so affected records can be found without log forensics;
        * **retriable / auto-backfilled** — added to the background reconciler's pending
          set (``kb:vectorize:pending``, #11296) which re-vectorizes it every cycle until
          it succeeds and is marked ``completed``.
        """
        from background_vectorization import PENDING_SET_KEY

        logger.error(
            "Vectorization FAILED for fact %s — vector NOT stored; marked failed and queued for retry. Reason: %s",
            fact_id,
            reason,
        )
        try:
            fact_key = "fact:%s" % fact_id
            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                mapping={
                    "vectorization_status": "failed",
                    "vectorization_error": reason,
                    "vectorization_failed_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
            await asyncio.to_thread(self.redis_client.sadd, PENDING_SET_KEY, fact_id)
        except Exception as exc:
            logger.error("Could not record vectorization failure for fact %s: %s", fact_id, exc)

    async def _mark_vectorization_succeeded(self, fact_id: str) -> None:
        """Clear any failed/pending vectorization state after a successful vector write (Issue #12312).

        Keeps the unvectorized-count metric accurate: a fact that previously failed
        and then succeeds inline is marked ``completed`` and dropped from the pending
        set immediately, rather than lingering as ``failed`` until the next reconcile
        cycle. Mirrors ``BackgroundVectorizer._mark_vectorization_complete`` (#11296).
        """
        from background_vectorization import PENDING_SET_KEY

        try:
            fact_key = "fact:%s" % fact_id
            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                mapping={
                    "vectorization_status": "completed",
                    "vectorized_at": datetime.now(tz=timezone.utc).isoformat(),
                },
            )
            await asyncio.to_thread(self.redis_client.srem, PENDING_SET_KEY, fact_id)
        except Exception as exc:
            logger.debug("Could not mark vectorization success for fact %s (non-critical): %s", fact_id, exc)

    async def _vectorize_fact_in_chromadb(
        self, fact_id: str, content: str, metadata: Dict[str, Any], max_attempts: int = 1
    ) -> None:
        """
        Vectorize and store fact in ChromaDB vector store.

        Issue #281: Extracted helper for ChromaDB vectorization.
        Issue #165: Uses NPU worker for hardware-accelerated embedding generation.

        Args:
            fact_id: Fact identifier
            content: Fact content text
            metadata: Fact metadata dict
            max_attempts: Embedding attempts before giving up. Issue #12312: defaults
                to 1 (fast-fail) for inline user-facing creates; the on-demand /
                reconcile path (``vectorize_existing_fact``) passes a higher count.
        """
        if not self.vector_store:
            return

        # Import sanitization utility
        from knowledge.utils import sanitize_metadata_for_chromadb as _sanitize_metadata_for_chromadb

        # Sanitize metadata for ChromaDB
        sanitized_metadata = _sanitize_metadata_for_chromadb(metadata)

        # Issue #165: Generate embedding using NPU worker with fallback
        # ChromaVectorStore.add() expects nodes with embeddings already set
        embedding = await _generate_embedding_with_npu_fallback(content, max_attempts=max_attempts)

        # Issue #12312: An empty embedding means generation failed upstream (backend
        # blip, timeout). Do NOT silently drop the vector and log success — record a
        # queryable, retriable failure so the background reconciler backfills it once
        # the backend recovers.
        if not embedding:
            await self._record_failed_vectorization(fact_id, "embedding generation returned an empty result")
            return

        # Issue #8391: Route through VectorWriteBuffer when available (LSM-style batching).
        # Falls back to direct LlamaIndex add() when buffer is not yet started.
        write_buffer = getattr(self, "_write_buffer", None)
        if write_buffer is not None:
            # Issue #12312: honour the write buffer's drop signal so the empty-embedding
            # contract self-enforces even if the guard above ever moves.
            if not await write_buffer.write(fact_id, embedding, content, sanitized_metadata):
                await self._record_failed_vectorization(fact_id, "write buffer rejected the embedding")
                return
        else:
            from llama_index.core import Document

            doc = Document(text=content, doc_id=fact_id, metadata=sanitized_metadata)
            doc.embedding = embedding
            await asyncio.to_thread(self.vector_store.add, [doc])

        await self._mark_vectorization_succeeded(fact_id)
        logger.info("Vectorized fact %s in ChromaDB", fact_id)

    def _prepare_fact_metadata(
        self, fact_id: str, metadata: Dict[str, Any] | None, content: str = ""
    ) -> Dict[str, Any]:
        """Prepare metadata with system fields for new fact (Issue #398: extracted).

        Issue #1252: Injects provenance defaults when not already present so every
        stored fact carries source and verification information.
        Issue #1375: Adds SHA-256 content fingerprint for cache invalidation.
        """
        if metadata is None:
            metadata = {}
        metadata["fact_id"] = fact_id
        metadata["timestamp"] = datetime.now(tz=timezone.utc).isoformat()
        metadata["embedding_model"] = self.embedding_model_name
        _apply_provenance_defaults(metadata)

        # Issue #1375: Compute content fingerprint for cache invalidation
        if content:
            from services.content_fingerprint import compute_fingerprint

            metadata["content_fingerprint"] = compute_fingerprint(content)

        return metadata

    async def _store_and_vectorize_fact(self, fact_id: str, content: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Store fact in Redis, vectorize, and update stats (Issue #398: extracted)."""
        await self._store_fact_in_redis(fact_id, content, metadata)
        await self._vectorize_fact_in_chromadb(fact_id, content, metadata)
        await asyncio.gather(
            self._increment_stat("total_facts"),
            self._increment_stat("total_vectors"),
        )
        self._schedule_bm25_refresh()
        return {"status": "success", "fact_id": fact_id, "action": "created"}

    async def store_fact(self, content: str, metadata: Dict[str, Any] = None, fact_id: str = None) -> Dict[str, Any]:
        """Store a new fact in Redis and vectorize it (Issue #398: refactored)."""
        self.ensure_initialized()

        if not content or not content.strip():
            return {"status": "error", "message": "Empty content provided"}

        try:
            fact_id = fact_id or str(uuid.uuid4())
            metadata = self._prepare_fact_metadata(fact_id, metadata, content)

            duplicate_result = await self._check_for_duplicates(content, metadata)
            if duplicate_result:
                return duplicate_result

            return await self._store_and_vectorize_fact(fact_id, content, metadata)

        except Exception as e:
            logger.error("Failed to store fact: %s", e)
            return {"status": "error", "message": "Knowledge operation failed"}

    async def _get_fact_for_vectorization(self, fact_id: str) -> Dict[str, Any] | None:
        """Get and decode fact data for vectorization (Issue #398: extracted)."""
        fact_key = "fact:%s" % fact_id
        fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)

        if not fact_data:
            return None

        decoded = _decode_redis_hash(fact_data)
        content = decoded.get("content", "")
        if not content:
            return {"error": "Fact has no content"}

        metadata = decoded.get("_parsed_metadata", {})
        metadata["fact_id"] = fact_id

        return {"content": content, "metadata": metadata}

    async def vectorize_existing_fact(self, fact_id: str) -> Dict[str, Any]:
        """Vectorize an existing fact (Issue #398: refactored)."""
        self.ensure_initialized()

        try:
            fact_info = await self._get_fact_for_vectorization(fact_id)

            if fact_info is None:
                return {"status": "error", "message": "Fact not found"}
            if "error" in fact_info:
                return {"status": "error", "message": fact_info["error"]}

            if not self.vector_store:
                return {"status": "error", "message": "Vector store not available"}

            # Issue #12312: This is the on-demand / reconcile retry path (admin batch,
            # retry jobs, background backfill), not a user-facing create — so retry
            # transient embedding failures with backoff here where latency is hidden.
            from services.npu_client import EMBEDDING_MAX_ATTEMPTS

            await self._vectorize_fact_in_chromadb(
                fact_id, fact_info["content"], fact_info["metadata"], max_attempts=EMBEDDING_MAX_ATTEMPTS
            )

            logger.info("Vectorized existing fact %s", fact_id)
            return {
                "status": "success",
                "message": "Fact vectorized successfully",
                "vector_indexed": True,
                "fact_id": fact_id,
            }

        except Exception as e:
            logger.error("Failed to vectorize fact %s: %s", fact_id, e)
            return {"status": "error", "message": "Knowledge operation failed"}

    def get_fact(self, fact_id: str) -> Dict[str, Any] | None:
        """
        Retrieve a single fact by ID (synchronous).

        Args:
            fact_id: Fact ID to retrieve

        Returns:
            Dict with fact data or None if not found
        """
        try:
            fact_key = "fact:%s" % fact_id
            fact_data = self.redis_client.hgetall(fact_key)

            if not fact_data:
                return None

            # Decode data
            decoded = {}
            for key, value in fact_data.items():
                k = key.decode("utf-8") if isinstance(key, bytes) else key
                v = value.decode("utf-8") if isinstance(value, bytes) else value
                decoded[k] = v

            # Parse metadata
            metadata = {}
            if "metadata" in decoded:
                try:
                    raw = decoded["metadata"]
                    metadata = raw if isinstance(raw, dict) else json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass

            _apply_usage_fields(decoded, metadata)
            return {
                "fact_id": fact_id,
                "content": decoded.get("content", ""),
                "metadata": metadata,
                "timestamp": decoded.get("timestamp", ""),
            }

        except Exception as e:
            logger.error("Error retrieving fact %s: %s", fact_id, e)
            return None

    async def record_fact_access(self, fact_ids: List[str]) -> None:
        """Schedule a non-blocking usage bump for surfaced facts (A1, #12552).

        Returns immediately: the actual ``HINCRBY`` runs in a background task so
        the read path is never blocked and a failure here never propagates to the
        caller. Reinforcement is best-effort — a dropped bump only costs one
        ranking signal, never correctness.
        """
        ids = [fid for fid in (fact_ids or []) if fid]
        if not ids:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            # No running loop (sync/test context): do it inline, still guarded.
            await self._bump_fact_access(ids)
            return
        task = loop.create_task(self._bump_fact_access(ids))
        _ACCESS_TASKS.add(task)
        task.add_done_callback(_ACCESS_TASKS.discard)

    async def _bump_fact_access(self, fact_ids: List[str]) -> None:
        """Atomically increment ``access_count`` and stamp ``last_accessed``.

        Counters are authoritative top-level hash fields, so the metadata JSON
        blob is never rewritten. The EXISTS+HINCRBY+HSET is done as one atomic
        Lua ``EVAL`` per fact, so a deleted fact is never resurrected by a bump
        racing a concurrent ``delete_fact``. Duplicate ids collapse to one bump.
        """
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        unique_ids = list(dict.fromkeys(fact_ids))

        def _work() -> None:
            for fid in unique_ids:
                try:
                    self.redis_client.eval(_ACCESS_BUMP_LUA, 1, "fact:%s" % fid, now_iso)
                except Exception:
                    logger.debug("record_fact_access: bump failed for %s (non-fatal)", fid)

        try:
            await asyncio.to_thread(_work)
        except Exception:
            logger.debug("record_fact_access bump failed (non-fatal)", exc_info=True)

    def _process_fact_data(
        self,
        key: str,
        fact_data: Dict[bytes, bytes],
        collection: str | None = None,
    ) -> Dict[str, Any] | None:
        """Process raw Redis fact data into structured dict (Issue #315: extracted helper).

        Args:
            key: Redis key for the fact
            fact_data: Raw Redis hash data
            collection: Optional collection filter

        Returns:
            Processed fact dict or None if filtered out
        """
        if not fact_data:
            return None

        # Extract fact_id from key
        fact_id = key.split(":")[-1] if isinstance(key, str) else key.decode("utf-8").split(":")[-1]

        # Decode data using helper
        decoded = _decode_redis_hash(fact_data)

        # Apply collection filter if specified
        metadata = decoded.get("_parsed_metadata", {})
        if collection and metadata.get("collection") != collection:
            return None

        _apply_usage_fields(decoded, metadata)
        return {
            "fact_id": fact_id,
            "content": decoded.get("content", ""),
            "metadata": metadata,
            "timestamp": decoded.get("timestamp", ""),
        }

    async def get_all_facts(
        self,
        limit: int | None = None,
        offset: int = 0,
        collection: str | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve facts from Redis with optional pagination and filtering.

        Args:
            limit: Maximum number of facts to retrieve (None = all)
            offset: Number of facts to skip
            collection: Filter by collection name (None = all collections)

        Returns:
            List of fact dictionaries with content and metadata
        """
        self.ensure_initialized()

        try:
            # Get all fact keys using async scanner
            fact_keys = await self._scan_redis_keys_async("fact:*")

            if not fact_keys:
                return []

            # Apply offset and limit
            if offset > 0:
                fact_keys = fact_keys[offset:]
            if limit is not None:
                fact_keys = fact_keys[:limit]

            # Batch fetch facts
            facts = []
            pipeline = self.redis().pipeline()
            for key in fact_keys:
                pipeline.hgetall(key)
            facts_data = await pipeline.execute()

            for key, fact_data in zip(fact_keys, facts_data):
                fact = self._process_fact_data(key, fact_data, collection)
                if fact:
                    facts.append(fact)

            return facts

        except Exception as e:
            logger.error("Error retrieving all facts: %s", e)
            return []

    def _decode_fact_data(self, fact_data: Dict) -> Dict[str, str]:
        """Decode Redis fact data from bytes (Issue #398: extracted)."""
        decoded = {}
        for key, value in fact_data.items():
            k = key.decode("utf-8") if isinstance(key, bytes) else key
            v = value.decode("utf-8") if isinstance(value, bytes) else value
            decoded[k] = v
        return decoded

    async def _revectorize_fact(self, fact_id: str, content: str, current_metadata: Dict) -> None:
        """Re-vectorize fact after content update (Issue #398: extracted).

        Issue #165: Uses NPU worker for hardware-accelerated embedding generation.
        Issue #8405: Routes add through VectorWriteBuffer when available.
        """
        from knowledge.utils import sanitize_metadata_for_chromadb as _sanitize

        sanitized_metadata = _sanitize(current_metadata)
        sanitized_metadata["fact_id"] = fact_id
        await asyncio.to_thread(self.vector_store.delete, fact_id)

        # Issue #165: Generate embedding using NPU worker with fallback
        embedding = await _generate_embedding_with_npu_fallback(content)

        # Issue #12312: The stale vector was already deleted above; if embedding
        # generation failed the fact is now unvectorized. Record a queryable,
        # retriable failure instead of silently dropping and logging success.
        if not embedding:
            await self._record_failed_vectorization(
                fact_id, "embedding generation returned an empty result (re-vectorize)"
            )
            return

        # Issue #8405: Route through VectorWriteBuffer when available, like _vectorize_fact_in_chromadb.
        write_buffer = getattr(self, "_write_buffer", None)
        if write_buffer is not None:
            # Issue #12312: honour the write buffer's drop signal (self-enforcing contract).
            if not await write_buffer.write(fact_id, embedding, content, sanitized_metadata):
                await self._record_failed_vectorization(fact_id, "write buffer rejected the embedding (re-vectorize)")
                return
        else:
            from llama_index.core import Document

            doc = Document(text=content, doc_id=fact_id, metadata=sanitized_metadata)
            doc.embedding = embedding
            await asyncio.to_thread(self.vector_store.add, [doc])
        await self._mark_vectorization_succeeded(fact_id)
        logger.info("Re-vectorized updated fact %s", fact_id)

    async def _refresh_content_hash(self, fact_id: str, old_content: str, new_content: str) -> None:
        """Refresh content_hash dedup key when content changes. Issue #1375."""
        if old_content:
            old_hash = hashlib.sha256(old_content.encode("utf-8")).hexdigest()[:16]
            await asyncio.to_thread(self.redis_client.delete, "content_hash:%s" % old_hash)
        new_hash = hashlib.sha256(new_content.encode("utf-8")).hexdigest()[:16]
        await asyncio.to_thread(self.redis_client.set, "content_hash:%s" % new_hash, fact_id)

    async def update_fact(self, fact_id: str, content: str = None, metadata: Dict[str, Any] = None) -> Dict[str, Any]:
        """Update an existing fact (Issue #398: refactored)."""
        self.ensure_initialized()

        try:
            fact_key = "fact:%s" % fact_id
            exists = await asyncio.to_thread(self.redis_client.exists, fact_key)
            if not exists:
                return {"status": "error", "message": "Fact not found"}

            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)
            decoded = self._decode_fact_data(fact_data)

            current_metadata = {}
            if "metadata" in decoded:
                try:
                    raw = decoded["metadata"]
                    current_metadata = raw if isinstance(raw, dict) else json.loads(raw)
                except (json.JSONDecodeError, TypeError):
                    pass

            if content is not None:
                # Issue #1375: Refresh dedup key + fingerprint on content change
                await self._refresh_content_hash(fact_id, decoded.get("content", ""), content)
                decoded["content"] = content
                from services.content_fingerprint import compute_fingerprint

                current_metadata["content_fingerprint"] = compute_fingerprint(content)
            if metadata is not None:
                current_metadata.update(metadata)
            current_metadata["updated_at"] = datetime.now(tz=timezone.utc).isoformat()

            await asyncio.to_thread(
                self.redis_client.hset,
                fact_key,
                mapping={
                    "content": decoded["content"],
                    "metadata": json.dumps(current_metadata),
                    "timestamp": decoded.get("timestamp", ""),
                },
            )

            if content is not None and self.vector_store:
                await self._revectorize_fact(fact_id, decoded["content"], current_metadata)

            return {"status": "success", "fact_id": fact_id, "action": "updated"}

        except Exception as e:
            logger.error("Failed to update fact %s: %s", fact_id, e)
            return {"status": "error", "message": "Knowledge operation failed"}

    async def _cleanup_fact_mappings(self, fact_id: str, content: str, metadata: Dict[str, Any]) -> None:
        """Clean up Redis mappings for a deleted fact. Issue #620 and #688.

        Removes content hash, unique key, session tracking mappings, and
        ownership indexes to prevent memory leaks.

        Args:
            fact_id: ID of the fact being deleted
            content: Fact content for hash cleanup
            metadata: Fact metadata for unique key cleanup
        """
        if content:
            content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]
            await asyncio.to_thread(self.redis_client.delete, "content_hash:%s" % content_hash)

        unique_key = metadata.get("unique_key")
        if unique_key:
            await asyncio.to_thread(self.redis_client.delete, "unique_key:man_page:%s" % unique_key)

        await asyncio.to_thread(self.redis_client.delete, "fact:origin:session:%s" % fact_id)

        # Issue #688: Clean up ownership indexes
        if hasattr(self, "ownership_manager"):
            await self.ownership_manager.cleanup_ownership_indexes(fact_id, metadata)

    async def _delete_fact_from_vector_store(self, fact_id: str) -> None:
        """Delete fact from ChromaDB vector store. Issue #620.

        Args:
            fact_id: ID of the fact to delete from vector store
        """
        if self.vector_store:
            try:
                await asyncio.to_thread(self.vector_store.delete, fact_id)
            except Exception as e:
                logger.warning("Could not delete vector for fact %s: %s", fact_id, e)

    async def delete_fact(self, fact_id: str, *, _skip_bm25_refresh: bool = False) -> dict:
        """Delete a fact from Redis and ChromaDB. Issue #620.

        Args:
            fact_id: ID of the fact to delete
            _skip_bm25_refresh: If True, skip per-item BM25 stats
                refresh. Callers doing bulk deletes should set this
                and call ``_schedule_bm25_refresh()`` once after the
                batch completes (#2079).

        Returns:
            Dict with status
        """
        self.ensure_initialized()

        try:
            fact_key = "fact:%s" % fact_id
            fact_data = await asyncio.to_thread(self.redis_client.hgetall, fact_key)
            if not fact_data:
                return {"status": "error", "message": "Fact not found"}

            decoded = _decode_redis_hash(fact_data)
            content = decoded.get("content", "")
            metadata = decoded.get("_parsed_metadata", {})

            await asyncio.to_thread(self.redis_client.delete, fact_key)
            await self._cleanup_fact_mappings(fact_id, content, metadata)
            await self._delete_fact_from_vector_store(fact_id)

            await asyncio.gather(
                self._decrement_stat("total_facts"),
                self._decrement_stat("total_vectors"),
            )

            if not _skip_bm25_refresh:
                self._schedule_bm25_refresh()
            logger.info("Deleted fact %s", fact_id)
            return {"status": "success", "fact_id": fact_id, "action": "deleted"}

        except Exception as e:
            logger.error("Failed to delete fact %s: %s", fact_id, e)
            return {"status": "error", "message": "Knowledge operation failed"}

    # Method references needed from other mixins
    async def _scan_redis_keys_async(self, pattern: str):
        """Scan Redis keys - implemented in base class"""
        raise NotImplementedError("Should be implemented in composed class")

    async def _increment_stat(self, field: str, amount: int = 1):
        """Increment stats counter - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    async def _decrement_stat(self, field: str, amount: int = 1):
        """Decrement stats counter - implemented in stats mixin"""
        raise NotImplementedError("Should be implemented in composed class")

    def ensure_initialized(self):
        """Ensure initialized - implemented in base class"""
        raise NotImplementedError("Should be implemented in composed class")

    # =========================================================================
    # SESSION-FACT RELATIONSHIP TRACKING (Issue #547)
    # =========================================================================

    async def _track_session_fact_relationship(self, session_id: str, fact_id: str) -> None:
        """
        Track bidirectional relationship between session and fact for orphan cleanup.

        Issue #547: Creates Redis indexes to enable cleanup when session is deleted.

        Redis Keys Created:
        - session:facts:{session_id} -> Set of fact IDs created in this session
        - fact:origin:session:{fact_id} -> String of session ID that created this fact

        Args:
            session_id: Chat session ID
            fact_id: Fact ID
        """
        try:
            # Add fact to session's fact set
            await asyncio.to_thread(self.redis_client.sadd, "session:facts:%s" % session_id, fact_id)

            # Store reverse lookup (fact -> session)
            await asyncio.to_thread(self.redis_client.set, "fact:origin:session:%s" % fact_id, session_id)

            logger.debug(
                "Tracked session-fact relationship: session=%s, fact=%s",
                session_id,
                fact_id,
            )

        except Exception as e:
            logger.warning(
                "Failed to track session-fact relationship: session=%s, fact=%s, error=%s",
                session_id,
                fact_id,
                e,
            )

    async def get_facts_by_session(self, session_id: str) -> List[str]:
        """
        Get all fact IDs created during a specific session.

        Issue #547: Used for orphan cleanup when session is deleted.

        Args:
            session_id: Chat session ID

        Returns:
            List of fact IDs created in this session
        """
        try:
            fact_ids = await asyncio.to_thread(self.redis_client.smembers, "session:facts:%s" % session_id)

            # Decode bytes to strings
            return [fid.decode("utf-8") if isinstance(fid, bytes) else fid for fid in (fact_ids or [])]

        except Exception as e:
            logger.error("Failed to get facts by session %s: %s", session_id, e)
            return []

    async def get_session_for_fact(self, fact_id: str) -> str | None:
        """
        Get the session ID that created a specific fact.

        Issue #547: Reverse lookup for fact -> session relationship.

        Args:
            fact_id: Fact ID

        Returns:
            Session ID or None if not tracked
        """
        try:
            session_id = await asyncio.to_thread(self.redis_client.get, "fact:origin:session:%s" % fact_id)

            if session_id:
                return session_id.decode("utf-8") if isinstance(session_id, bytes) else session_id
            return None

        except Exception as e:
            logger.error("Failed to get session for fact %s: %s", fact_id, e)
            return None

    async def _batch_check_important_facts(self, fact_ids: List[str]) -> set:
        """
        Batch check which facts are marked as important/preserve.

        Issue #547 code review: Optimizes performance by using Redis pipeline
        instead of individual blocking get_fact() calls.

        Args:
            fact_ids: List of fact IDs to check

        Returns:
            Set of fact IDs that should be preserved
        """
        if not fact_ids:
            return set()

        try:
            # Use pipeline for batch fetch
            pipeline = self.redis().pipeline()
            for fact_id in fact_ids:
                pipeline.hgetall("fact:%s" % fact_id)

            facts_data = await pipeline.execute()

            important_fact_ids = set()
            for fact_id, fact_data in zip(fact_ids, facts_data):
                if not fact_data:
                    continue
                decoded = _decode_redis_hash(fact_data)
                metadata = decoded.get("_parsed_metadata", {})
                if metadata.get("important") or metadata.get("preserve"):
                    important_fact_ids.add(fact_id)

            return important_fact_ids

        except Exception as e:
            logger.warning("Failed to batch check important facts: %s", e)
            return set()

    async def _delete_single_fact_for_session(
        self,
        fact_id: str,
        session_id: str,
        important_ids: set,
        preserve_important: bool,
        result: Dict[str, Any],
    ) -> None:
        """Delete a single fact during session cleanup (Issue #665: extracted helper).

        Args:
            fact_id: Fact ID to process
            session_id: Session ID being cleaned up
            important_ids: Set of fact IDs to preserve
            preserve_important: Whether to preserve important facts
            result: Result dict to update with counts/errors
        """
        try:
            # Check if fact should be preserved
            if preserve_important and fact_id in important_ids:
                logger.debug("Preserving important fact %s from session %s", fact_id, session_id)
                result["preserved_count"] += 1
                return

            # Delete the fact
            delete_result = await self.delete_fact(fact_id)

            if delete_result.get("status") == "success":
                result["deleted_count"] += 1
            else:
                result["errors"].append(
                    {
                        "fact_id": fact_id,
                        "error": delete_result.get("message", "Unknown error"),
                    }
                )

        except Exception as e:
            logger.error("Failed to delete fact %s: %s", fact_id, e)
            result["errors"].append({"fact_id": fact_id, "error": "Fact deletion failed"})

    async def _process_session_facts_deletion(
        self,
        session_id: str,
        fact_ids: List[str],
        preserve_important: bool,
        result: Dict[str, Any],
    ) -> None:
        """Process deletion of all facts in a session. Issue #620.

        Args:
            session_id: Session ID being cleaned up
            fact_ids: List of fact IDs to process
            preserve_important: Whether to preserve important facts
            result: Result dict to update with counts
        """
        important_ids = set()
        if preserve_important:
            important_ids = await self._batch_check_important_facts(fact_ids)

        for fact_id in fact_ids:
            await self._delete_single_fact_for_session(fact_id, session_id, important_ids, preserve_important, result)

        await self._cleanup_session_tracking(session_id, fact_ids)

    def _collect_prune_candidates(
        self, facts: List[Dict[str, Any]], quality_floor: float, cutoff: datetime, epoch: datetime
    ) -> List[str]:
        """Return fact_ids that are genuinely dead and safe to prune (A3 #12554).

        A candidate must satisfy ALL of: unprotected (incl. curated/ingested — see
        ``_fact_is_protected``); ``quality_score`` below the floor; ``access_count
        == 0`` (never recalled); creation time **after ``epoch``** so a 0 count
        reflects real non-use rather than predating A1 instrumentation; and older
        than ``cutoff``. Unknown-age, pre-epoch, or newer facts are kept (fail-safe).
        """
        candidates: List[str] = []
        for fact in facts:
            meta = fact.get("metadata") or {}
            if _fact_is_protected(meta):
                continue
            try:
                quality = float(meta.get("quality_score", 0.0) or 0.0)
                access = int(meta.get("access_count", 0) or 0)
            except (TypeError, ValueError):
                continue  # unparseable usage -> keep (fail-safe)
            if access != 0 or quality >= quality_floor:
                continue
            created = _parse_iso(fact.get("timestamp") or meta.get("timestamp"))
            # Keep if age unknown, created before instrumentation (0 count is
            # meaningless there), or not yet older than the age floor.
            if created is None or created <= epoch or created > cutoff:
                continue
            fid = fact.get("fact_id")
            if fid:
                candidates.append(fid)
        return candidates

    async def consolidate_facts(
        self,
        *,
        quality_floor: float = _FACTS_PRUNE_QUALITY_FLOOR,
        max_age_days: int = _FACTS_PRUNE_MAX_AGE_DAYS,
        dry_run: bool = True,
        now: datetime | None = None,
    ) -> Dict[str, Any]:
        """Delete-only consolidation of the essential-story facts lane (A3 #12554).

        Prunes only genuinely-dead facts (see ``_collect_prune_candidates``):
        unprotected, uncurated, low-quality, never recalled since instrumentation
        began, and aged out. Multiple no-data-loss safeguards, all fail-safe:

        - **Instrumentation epoch** (``AUTOBOT_FACTS_PRUNE_EPOCH``): UNSET → the
          task is inert (no candidates), so an unconfigured deploy can never
          delete. Set it to the date A1 access-tracking began for this instance;
          facts older than that are never eligible.
        - **Circuit breaker** (``AUTOBOT_FACTS_PRUNE_MAX_PER_RUN``): if a run would
          prune more than the cap, it refuses and logs loudly — a healthy decay
          sheds a trickle, a flood means the signals are wrong.
        - **dry_run** (default True): logs candidates without deleting.

        Owned/verified/pinned/curated facts are never eligible. Never raises.
        """
        self.ensure_initialized()
        now = now or datetime.now(tz=timezone.utc)
        cutoff = now - timedelta(days=max_age_days)
        epoch = _parse_iso(_FACTS_PRUNE_EPOCH)
        if epoch is None:
            logger.info(
                "consolidate_facts: AUTOBOT_FACTS_PRUNE_EPOCH unset — pruning disabled "
                "(set it to when A1 access-tracking began to enable decay)."
            )
            return {"scanned": 0, "candidates": 0, "pruned": 0, "remaining": 0, "dry_run": dry_run, "epoch_unset": True}
        try:
            facts = await self.get_all_facts(limit=_FACTS_PRUNE_SCAN_LIMIT)
        except Exception as exc:
            logger.warning("consolidate_facts: scan failed (non-fatal): %s", exc)
            return {"scanned": 0, "candidates": 0, "pruned": 0, "remaining": 0, "dry_run": dry_run}

        candidates = self._collect_prune_candidates(facts, quality_floor, cutoff, epoch)
        pruned = 0
        # Circuit breaker: an unexpectedly large candidate set means the signals
        # are wrong (mis-set epoch, instrumentation gap). Refuse and shout.
        if not dry_run and len(candidates) > _FACTS_PRUNE_MAX_PER_RUN:
            logger.error(
                "consolidate_facts: %d candidates exceed max-per-run %d — refusing to "
                "prune (likely misconfigured epoch/floor). Review before enforcing.",
                len(candidates),
                _FACTS_PRUNE_MAX_PER_RUN,
            )
            return {
                "scanned": len(facts),
                "candidates": len(candidates),
                "pruned": 0,
                "remaining": len(facts),
                "dry_run": dry_run,
                "circuit_broken": True,
            }
        if not dry_run:
            for fid in candidates:
                try:
                    res = await self.delete_fact(fid, _skip_bm25_refresh=True)
                    if res.get("status") == "success":
                        pruned += 1
                except Exception:
                    logger.debug("consolidate_facts: delete failed for %s (non-fatal)", fid)
            if pruned:
                self._schedule_bm25_refresh()

        summary = {
            "scanned": len(facts),
            "candidates": len(candidates),
            "pruned": pruned,
            "remaining": len(facts) - pruned,
            "dry_run": dry_run,
        }
        logger.info(
            "consolidate_facts: scanned=%d candidates=%d pruned=%d dry_run=%s",
            len(facts),
            len(candidates),
            pruned,
            dry_run,
        )
        return summary

    async def delete_facts_by_session(self, session_id: str, preserve_important: bool = True) -> Dict[str, Any]:
        """Delete all facts created during a specific session. Issue #620.

        Args:
            session_id: Chat session ID to cleanup
            preserve_important: If True, preserve facts marked as 'important'

        Returns:
            Dict with deletion statistics
        """
        self.ensure_initialized()

        result: Dict[str, Any] = {
            "deleted_count": 0,
            "preserved_count": 0,
            "errors": [],
        }

        try:
            fact_ids = await self.get_facts_by_session(session_id)
            if not fact_ids:
                logger.info("No facts found for session %s", session_id)
                return result

            logger.info(
                "Cleaning up %d facts for session %s (preserve_important=%s)",
                len(fact_ids),
                session_id,
                preserve_important,
            )

            await self._process_session_facts_deletion(session_id, fact_ids, preserve_important, result)

            logger.info(
                "Session %s cleanup complete: deleted=%d, preserved=%d, errors=%d",
                session_id,
                result["deleted_count"],
                result["preserved_count"],
                len(result["errors"]),
            )
            return result

        except Exception as e:
            logger.error("Failed to delete facts for session %s: %s", session_id, e)
            result["errors"].append({"session_id": session_id, "error": "Session facts deletion failed"})
            return result

    async def _cleanup_session_tracking(self, session_id: str, fact_ids: List[str]) -> None:
        """
        Clean up session tracking keys after facts deletion.

        Issue #547: Remove session-fact relationship tracking data.

        Args:
            session_id: Session ID being cleaned up
            fact_ids: List of fact IDs to clean up
        """
        try:
            # Delete the session's fact set
            await asyncio.to_thread(self.redis_client.delete, "session:facts:%s" % session_id)

            # Delete reverse lookup keys for each fact
            for fact_id in fact_ids:
                await asyncio.to_thread(self.redis_client.delete, "fact:origin:session:%s" % fact_id)

            logger.debug("Cleaned up tracking for session %s", session_id)

        except Exception as e:
            logger.warning("Failed to cleanup session tracking for %s: %s", session_id, e)

    # =========================================================================
    # FACT SHARING (Issue #689)
    # =========================================================================

    async def share_facts(
        self,
        fact_ids: List[str],
        shared_with: List[str],
        shared_by: str,
    ) -> Dict[str, Any]:
        """Share specific facts with other users.

        Creates sharing indices and updates fact metadata with
        shared_with user IDs while preserving original ownership.

        Args:
            fact_ids: List of fact IDs to share
            shared_with: List of user IDs to share with
            shared_by: User ID of the person sharing

        Returns:
            Dict with sharing results
        """
        shared_count = 0
        errors = []

        for fact_id in fact_ids:
            try:
                await self._share_single_fact(fact_id, shared_with, shared_by)
                shared_count += 1
            except Exception as e:
                logger.error("Failed to share fact %s: %s", fact_id, e)
                errors.append({"fact_id": fact_id, "error": "Fact sharing failed"})

        return {
            "shared_count": shared_count,
            "errors": errors,
        }

    async def _share_single_fact(self, fact_id: str, shared_with: List[str], shared_by: str) -> None:
        """Share a single fact with users. Helper for share_facts (#689)."""
        fact_key = "fact:%s" % fact_id
        raw = await asyncio.to_thread(self.redis_client.hget, fact_key, "metadata")
        if not raw:
            raise ValueError("Fact %s not found" % fact_id)

        raw_str = raw.decode("utf-8") if isinstance(raw, bytes) else raw
        metadata = json.loads(raw_str) if isinstance(raw_str, str) else raw_str

        existing_shared = metadata.get("shared_with", [])
        merged = list(set(existing_shared + shared_with))
        metadata["shared_with"] = merged
        metadata["shared_by"] = shared_by
        metadata["shared_at"] = datetime.now(tz=timezone.utc).isoformat()

        await asyncio.to_thread(self.redis_client.hset, fact_key, "metadata", json.dumps(metadata))

        for user_id in shared_with:
            await asyncio.to_thread(
                self.redis_client.sadd,
                "user:shared_facts:%s" % user_id,
                fact_id,
            )

    async def get_shared_facts(self, user_id: str) -> List[Dict[str, Any]]:
        """Get all facts shared with a user (#689).

        Args:
            user_id: Recipient user ID

        Returns:
            List of fact dicts with content and metadata
        """
        try:
            raw_ids = await asyncio.to_thread(self.redis_client.smembers, "user:shared_facts:%s" % user_id)
            fact_ids = [fid.decode("utf-8") if isinstance(fid, bytes) else fid for fid in (raw_ids or [])]
            facts = []
            for fid in fact_ids:
                fact = self.get_fact(fid)
                if fact:
                    facts.append(fact)
            return facts
        except Exception as e:
            logger.error("Failed to get shared facts for %s: %s", user_id, e)
            return []
