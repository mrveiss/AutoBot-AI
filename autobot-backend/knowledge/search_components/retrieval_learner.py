# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Retrieval Pattern Learner — closes the RAG feedback loop. Issue #2095.

Consumes rag:feedback:{date} Redis streams, scores retrieval trajectories by
user acceptance (rerank-position gain), distils successful patterns into
reusable Redis hashes, and exposes a query-time hint API so RAGService can
adapt its strategy based on historical evidence.

Redis key layout
----------------
rag:retrieval_patterns:{pattern_hash}   HASH   — per-pattern metrics & hints
rag:rl:cursor:{date}                    STRING — last processed entry ID per day
"""

import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Patterns are kept for 30 days; unused ones are pruned at consolidation time.
_PATTERN_TTL_SECONDS = 30 * 24 * 3600
# Minimum usage count before we prune old patterns.
_PRUNE_MIN_USAGE = 3
# Cosine-similarity threshold above which two patterns are considered duplicates.
_DEDUP_SIMILARITY_THRESHOLD = 0.95
# Minimum rerank-position improvement ratio for a trajectory to count as "successful".
_SUCCESS_THRESHOLD = 0.6
# Number of stream entries read per XRANGE batch.
_XRANGE_BATCH = 100
# Redis cursor hash key (one entry per date key).
_CURSOR_HASH_KEY = "rag:rl:cursors"
# Hash prefix for distilled patterns.
_PATTERN_KEY_PREFIX = "rag:retrieval_patterns:"


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RetrievalPattern:
    """A distilled retrieval pattern extracted from successful feedback trajectories."""

    pattern_hash: str
    query_type: str  # QueryComplexity.value string
    chunk_categories: List[str]
    strategy_hints: Dict[str, str]  # e.g. {"enable_reranking": "true"}
    success_rate: float
    usage_count: int
    last_seen: float = field(default_factory=time.time)

    def to_redis_mapping(self) -> Dict[str, str]:
        """Serialise to a flat string dict suitable for Redis HSET."""
        return {
            "pattern_hash": self.pattern_hash,
            "query_type": self.query_type,
            "chunk_categories": json.dumps(self.chunk_categories, ensure_ascii=False),
            "strategy_hints": json.dumps(self.strategy_hints, ensure_ascii=False),
            "success_rate": str(self.success_rate),
            "usage_count": str(self.usage_count),
            "last_seen": str(self.last_seen),
        }

    @classmethod
    def from_redis_mapping(cls, mapping: Dict) -> "RetrievalPattern":
        """Deserialise from a Redis HGETALL response."""

        def _decode(v):
            return v.decode("utf-8") if isinstance(v, bytes) else v

        m = {_decode(k): _decode(v) for k, v in mapping.items()}
        return cls(
            pattern_hash=m["pattern_hash"],
            query_type=m.get("query_type", "simple"),
            chunk_categories=json.loads(m.get("chunk_categories", "[]")),
            strategy_hints=json.loads(m.get("strategy_hints", "{}")),
            success_rate=float(m.get("success_rate", 0.0)),
            usage_count=int(m.get("usage_count", 0)),
            last_seen=float(m.get("last_seen", 0.0)),
        )


# ---------------------------------------------------------------------------
# Core learner
# ---------------------------------------------------------------------------


class RetrievalLearner:
    """Closed-loop retrieval learning from rag:feedback streams.

    Lifecycle:
    1. consume_feedback_stream(date_key) — read new events from a stream day.
    2. _score_trajectory()               — determine success per event.
    3. _distil_pattern()                 — hash & persist to Redis.
    4. consolidate()                     — dedup + prune old patterns.

    Query-time API:
    - get_matching_pattern(query, complexity) → RetrievalPattern | None
    - record_pattern_outcome(pattern_hash, success) → updates success_rate

    Cursor tracking mirrors EdgeLearner's approach (#2210): each date key has
    its own cursor stored in the rag:rl:cursors Redis hash so the scheduler
    can call consume_feedback_stream() repeatedly without re-processing events.
    """

    def __init__(self, redis=None) -> None:
        self._redis = redis
        self._redis_lock = threading.Lock()
        self._cursors: Dict[str, str] = {}
        self._cursors_loaded = False

    # ------------------------------------------------------------------
    # Redis access
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Lazily obtain an async Redis client from the canonical factory."""
        if self._redis is None:
            from autobot_shared.redis_client import get_redis_client

            self._redis = await get_redis_client(
                async_client=True, database="analytics"
            )
        return self._redis

    # ------------------------------------------------------------------
    # Cursor management (mirrors EdgeLearner #2210)
    # ------------------------------------------------------------------

    async def _load_cursors(self) -> None:
        """Load persisted per-date cursors from Redis on first call."""
        if self._cursors_loaded:
            return
        try:
            redis = await self._get_redis()
            stored = await redis.hgetall(_CURSOR_HASH_KEY)
            if stored:
                self._cursors.update(
                    {
                        (k.decode() if isinstance(k, bytes) else k): (
                            v.decode() if isinstance(v, bytes) else v
                        )
                        for k, v in stored.items()
                    }
                )
                logger.info(
                    "RetrievalLearner: loaded %d persisted cursors",
                    len(stored),
                )
        except Exception as exc:
            logger.warning("RetrievalLearner: could not load cursors: %s", exc)
        self._cursors_loaded = True

    async def _save_cursor(self, stream_key: str, cursor: str) -> None:
        """Persist a single cursor entry to Redis."""
        try:
            redis = await self._get_redis()
            await redis.hset(_CURSOR_HASH_KEY, stream_key, cursor)
        except Exception as exc:
            logger.warning(
                "RetrievalLearner: could not save cursor for %s: %s", stream_key, exc
            )

    # ------------------------------------------------------------------
    # Stream consumption
    # ------------------------------------------------------------------

    async def consume_feedback_stream(self, date_key: Optional[str] = None) -> int:
        """Consume new events from rag:feedback:{date_key} and distil patterns.

        Uses a per-stream cursor so repeated scheduler calls only read NEW
        entries. Mirrors EdgeLearner.consume_feedback_stream() design.

        Args:
            date_key: UTC date string YYYY-MM-DD. Defaults to today.

        Returns:
            Number of new events processed.
        """
        if date_key is None:
            date_key = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")

        stream_key = f"rag:feedback:{date_key}"
        await self._load_cursors()

        resume_id = self._cursors.get(stream_key, "0-0")
        processed = 0

        redis = await self._get_redis()
        if redis is None:
            logger.debug("RetrievalLearner: Redis unavailable, skipping stream consume")
            return 0

        while True:
            try:
                entries = await redis.xrange(
                    stream_key, min=resume_id, count=_XRANGE_BATCH
                )
            except Exception as exc:
                logger.warning(
                    "RetrievalLearner: xrange failed for %s: %s", stream_key, exc
                )
                break

            if not entries:
                break

            for entry_id, fields in entries:
                await self._process_feedback_event(fields)
                ts, seq = (
                    entry_id.decode() if isinstance(entry_id, bytes) else entry_id
                ).split("-")
                resume_id = f"{ts}-{int(seq) + 1}"
                processed += 1

            if len(entries) < _XRANGE_BATCH:
                break

        if processed > 0:
            self._cursors[stream_key] = resume_id
            await self._save_cursor(stream_key, resume_id)
            logger.info(
                "RetrievalLearner: consumed %d new events from %s",
                processed,
                stream_key,
            )
        else:
            logger.debug("RetrievalLearner: no new events in %s", stream_key)

        return processed

    # ------------------------------------------------------------------
    # Event processing & pattern distillation
    # ------------------------------------------------------------------

    async def _process_feedback_event(self, fields: Dict) -> None:
        """Score a single feedback event and distil a pattern if successful."""

        def _decode(v):
            return v.decode("utf-8") if isinstance(v, bytes) else v

        try:
            retrieved_ids = json.loads(_decode(fields.get("retrieved_chunk_ids", "[]")))
            ranked_ids = json.loads(_decode(fields.get("final_ranked_ids", "[]")))
            complexity = _decode(fields.get("complexity", "simple"))
        except (json.JSONDecodeError, AttributeError) as exc:
            logger.debug("RetrievalLearner: malformed event fields: %s", exc)
            return

        if not retrieved_ids or not ranked_ids:
            return

        is_successful = self._score_trajectory(retrieved_ids, ranked_ids)
        if not is_successful:
            return

        # Extract chunk categories from metadata embedded in chunk IDs.
        # Chunk IDs follow the convention "<category>/<uuid>" when available.
        categories = _extract_categories(ranked_ids)
        strategy_hints = _build_strategy_hints(complexity, len(ranked_ids))

        await self._distil_pattern(complexity, categories, strategy_hints)

    @staticmethod
    def _score_trajectory(retrieved_ids: List[str], ranked_ids: List[str]) -> bool:
        """Return True when reranking substantially improved top-chunk positions.

        Measures rerank position gain: what fraction of the top-5 ranked chunks
        were not already in the top-5 retrieved positions (i.e. reranking moved
        them up). A ratio >= SUCCESS_THRESHOLD means the strategy was effective.

        When retrieval and ranking are identical (no reranking) or the list is
        tiny, we treat the trajectory as neutral (not successful) to avoid
        polluting the pattern store with trivial retrievals.
        """
        if not retrieved_ids or not ranked_ids:
            return False
        if retrieved_ids == ranked_ids:
            return False  # reranking made no change — neutral, not a "success"

        top_k = min(5, len(ranked_ids))
        top_ranked = set(ranked_ids[:top_k])
        top_retrieved = set(retrieved_ids[:top_k])

        promoted = len(top_ranked - top_retrieved)  # chunks reranking moved up
        gain_ratio = promoted / top_k
        return gain_ratio >= _SUCCESS_THRESHOLD

    async def _distil_pattern(
        self,
        query_type: str,
        categories: List[str],
        strategy_hints: Dict[str, str],
    ) -> None:
        """Upsert a retrieval pattern in Redis.

        The pattern hash is derived from (query_type, sorted categories) so
        that semantically identical patterns always map to the same key.
        """
        pattern_hash = _compute_pattern_hash(query_type, categories)
        redis_key = f"{_PATTERN_KEY_PREFIX}{pattern_hash}"

        try:
            redis = await self._get_redis()
            existing_raw = await redis.hgetall(redis_key)

            if existing_raw:
                pattern = RetrievalPattern.from_redis_mapping(existing_raw)
                pattern.usage_count += 1
                # Exponential moving average keeps success_rate responsive.
                pattern.success_rate = pattern.success_rate * 0.9 + 1.0 * 0.1
                pattern.last_seen = time.time()
            else:
                pattern = RetrievalPattern(
                    pattern_hash=pattern_hash,
                    query_type=query_type,
                    chunk_categories=categories,
                    strategy_hints=strategy_hints,
                    success_rate=1.0,
                    usage_count=1,
                )

            await redis.hset(redis_key, mapping=pattern.to_redis_mapping())
            await redis.expire(redis_key, _PATTERN_TTL_SECONDS)
            logger.debug(
                "RetrievalLearner: upserted pattern %s (%s)", pattern_hash, query_type
            )

        except Exception as exc:
            logger.warning("RetrievalLearner: failed to distil pattern: %s", exc)

    # ------------------------------------------------------------------
    # Query-time API
    # ------------------------------------------------------------------

    async def get_matching_pattern(
        self,
        query: str,
        complexity: str = "simple",
        categories: Optional[List[str]] = None,
    ) -> Optional[RetrievalPattern]:
        """Return the best matching historical pattern for a query, or None.

        Matching strategy (fast, no embedding required):
        1. Exact hash match on (complexity, sorted categories).
        2. Complexity-only match (ignore categories) when no exact match.

        Only returns patterns with success_rate >= 0.6 and usage_count >= 3
        to avoid acting on sparse evidence.

        Args:
            query:      Raw query string (unused in current implementation but
                        reserved for future embedding-based matching).
            complexity: QueryComplexity.value string.
            categories: Optional category list from the calling context.

        Returns:
            Best matching RetrievalPattern or None.
        """
        _ = query  # reserved for future embedding-based lookup
        cats = sorted(categories) if categories else []

        candidates = [
            _compute_pattern_hash(complexity, cats),
            _compute_pattern_hash(complexity, []),  # complexity-only fallback
        ]

        try:
            redis = await self._get_redis()
            for ph in candidates:
                redis_key = f"{_PATTERN_KEY_PREFIX}{ph}"
                raw = await redis.hgetall(redis_key)
                if not raw:
                    continue
                pattern = RetrievalPattern.from_redis_mapping(raw)
                if pattern.success_rate >= 0.6 and pattern.usage_count >= 3:
                    logger.debug(
                        "RetrievalLearner: matched pattern %s (rate=%.2f, usage=%d)",
                        ph,
                        pattern.success_rate,
                        pattern.usage_count,
                    )
                    return pattern
        except Exception as exc:
            logger.warning("RetrievalLearner: get_matching_pattern failed: %s", exc)

        return None

    async def record_pattern_outcome(self, pattern_hash: str, success: bool) -> None:
        """Update the success_rate of an existing pattern with a new outcome.

        Uses EMA (alpha=0.1) so that a single bad outcome does not discard an
        otherwise reliable pattern.

        Args:
            pattern_hash: Hash key returned by get_matching_pattern().
            success:      True if the retrieval led to a satisfactory response.
        """
        redis_key = f"{_PATTERN_KEY_PREFIX}{pattern_hash}"
        try:
            redis = await self._get_redis()
            raw = await redis.hgetall(redis_key)
            if not raw:
                logger.debug("RetrievalLearner: no pattern found for %s", pattern_hash)
                return
            pattern = RetrievalPattern.from_redis_mapping(raw)
            signal = 1.0 if success else 0.0
            pattern.success_rate = pattern.success_rate * 0.9 + signal * 0.1
            pattern.usage_count += 1
            pattern.last_seen = time.time()
            await redis.hset(redis_key, mapping=pattern.to_redis_mapping())
            await redis.expire(redis_key, _PATTERN_TTL_SECONDS)
            logger.debug(
                "RetrievalLearner: updated pattern %s success=%.2f",
                pattern_hash,
                pattern.success_rate,
            )
        except Exception as exc:
            logger.warning(
                "RetrievalLearner: record_pattern_outcome failed for %s: %s",
                pattern_hash,
                exc,
            )

    # ------------------------------------------------------------------
    # Consolidation (dedup + prune)
    # ------------------------------------------------------------------

    async def consolidate(self) -> Tuple[int, int]:
        """Deduplicate near-identical patterns and prune stale/unused ones.

        Dedup: two patterns are considered duplicates when their query_type
        matches and their category Jaccard similarity >= DEDUP_SIMILARITY_THRESHOLD.
        The one with higher usage_count survives; the other is deleted.

        Prune: patterns older than 30 days with usage_count < PRUNE_MIN_USAGE
        are deleted.

        Returns:
            (deduplicated_count, pruned_count) — counts of removed entries.
        """
        try:
            redis = await self._get_redis()
        except Exception as exc:
            logger.warning("RetrievalLearner: consolidate — redis unavailable: %s", exc)
            return 0, 0

        all_keys = await _scan_pattern_keys(redis, _PATTERN_KEY_PREFIX)
        patterns: List[RetrievalPattern] = []

        for key in all_keys:
            try:
                raw = await redis.hgetall(key)
                if raw:
                    patterns.append(RetrievalPattern.from_redis_mapping(raw))
            except Exception as exc:
                logger.debug("RetrievalLearner: skipping key %s: %s", key, exc)

        dedup_count = await self._dedup_patterns(redis, patterns)
        prune_count = await self._prune_patterns(redis, patterns)

        logger.info(
            "RetrievalLearner: consolidate complete — deduped=%d pruned=%d",
            dedup_count,
            prune_count,
        )
        return dedup_count, prune_count

    async def _dedup_patterns(self, redis, patterns: List[RetrievalPattern]) -> int:
        """Remove near-duplicate patterns, keeping the higher-usage survivor."""
        removed = 0
        deleted_hashes = set()

        for i, pat_a in enumerate(patterns):
            if pat_a.pattern_hash in deleted_hashes:
                continue
            for pat_b in patterns[i + 1 :]:
                if pat_b.pattern_hash in deleted_hashes:
                    continue
                if pat_a.query_type != pat_b.query_type:
                    continue
                sim = _jaccard_similarity(
                    pat_a.chunk_categories, pat_b.chunk_categories
                )
                if sim >= _DEDUP_SIMILARITY_THRESHOLD:
                    # Keep the one with more usage evidence.
                    to_delete = (
                        pat_b if pat_a.usage_count >= pat_b.usage_count else pat_a
                    )
                    deleted_hashes.add(to_delete.pattern_hash)
                    try:
                        await redis.delete(
                            f"{_PATTERN_KEY_PREFIX}{to_delete.pattern_hash}"
                        )
                        removed += 1
                        logger.debug(
                            "RetrievalLearner: dedup removed pattern %s",
                            to_delete.pattern_hash,
                        )
                    except Exception as exc:
                        logger.warning(
                            "RetrievalLearner: dedup delete failed for %s: %s",
                            to_delete.pattern_hash,
                            exc,
                        )
        return removed

    async def _prune_patterns(self, redis, patterns: List[RetrievalPattern]) -> int:
        """Delete patterns that are too old and too rarely used."""
        pruned = 0
        cutoff = time.time() - _PATTERN_TTL_SECONDS

        for pattern in patterns:
            if pattern.last_seen < cutoff and pattern.usage_count < _PRUNE_MIN_USAGE:
                try:
                    await redis.delete(f"{_PATTERN_KEY_PREFIX}{pattern.pattern_hash}")
                    pruned += 1
                    logger.debug(
                        "RetrievalLearner: pruned stale pattern %s",
                        pattern.pattern_hash,
                    )
                except Exception as exc:
                    logger.warning(
                        "RetrievalLearner: prune delete failed for %s: %s",
                        pattern.pattern_hash,
                        exc,
                    )
        return pruned


# ---------------------------------------------------------------------------
# Module-level singleton (thread-safe, mirrors QueryClassifier pattern)
# ---------------------------------------------------------------------------

_retrieval_learner: Optional["RetrievalLearner"] = None
_retrieval_learner_lock = threading.Lock()


def get_retrieval_learner() -> RetrievalLearner:
    """Return the shared RetrievalLearner singleton (thread-safe).

    Issue #2095: Mirrors get_query_classifier() double-check locking pattern.
    """
    global _retrieval_learner
    if _retrieval_learner is None:
        with _retrieval_learner_lock:
            if _retrieval_learner is None:
                _retrieval_learner = RetrievalLearner()
    return _retrieval_learner


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _compute_pattern_hash(query_type: str, categories: List[str]) -> str:
    """Stable 12-char hex hash from (query_type, sorted categories)."""
    key = json.dumps({"qt": query_type, "cats": sorted(categories)}, sort_keys=True)
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


def _extract_categories(chunk_ids: List[str]) -> List[str]:
    """Infer category names from chunk IDs following "<category>/<uuid>" convention."""
    cats = set()
    for cid in chunk_ids:
        if isinstance(cid, str) and "/" in cid:
            cats.add(cid.split("/")[0])
    return sorted(cats)


def _build_strategy_hints(complexity: str, result_count: int) -> Dict[str, str]:
    """Build strategy hint dict from observed retrieval parameters."""
    hints: Dict[str, str] = {"query_type": complexity}
    if result_count > 0:
        hints["result_count"] = str(result_count)
    if complexity in ("complex", "multi_hop"):
        hints["enable_reranking"] = "true"
    return hints


def _jaccard_similarity(a: List[str], b: List[str]) -> float:
    """Jaccard similarity between two category lists."""
    set_a, set_b = set(a), set(b)
    if not set_a and not set_b:
        return 1.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union else 0.0


async def _scan_pattern_keys(redis, prefix: str) -> List[str]:
    """SCAN for all keys matching the given prefix."""
    keys: List[str] = []
    cursor = 0
    while True:
        try:
            cursor, batch = await redis.scan(cursor, match=f"{prefix}*", count=100)
        except Exception as exc:
            logger.warning("RetrievalLearner: scan failed: %s", exc)
            break
        for k in batch:
            keys.append(k.decode("utf-8") if isinstance(k, bytes) else k)
        if cursor == 0:
            break
    return keys
