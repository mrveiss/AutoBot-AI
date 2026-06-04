# Copyright (c) mrveiss. All rights reserved.
"""
AutoBot Memory Graph - Semantic Search Module

Implements hybrid search (RedisSearch + BM25 + vector embeddings) for the
memory graph.  Resolves #3612: extends autobot_memory_graph with the query
processor and hybrid scorer that were planned in #3384 / #3385 so that the
parallel knowledge/memory_graph/ package is never needed.

Architecture:
    MemoryGraphQueryProcessor  - natural-language → structured search pipeline
    HybridScorer               - cosine similarity + BM25 re-ranking
    SearchResult               - result dataclass (entity + scores)
    QueryIntent                - extracted intent dataclass
"""

from __future__ import annotations

import asyncio
import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any, Dict, List, Sequence

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config as ssot_config

from .core import ENTITY_TYPES as _ENTITY_TYPES  # noqa: F401 — re-exported via package

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Entity-type intent patterns → UPPERCASE canonical names
# ---------------------------------------------------------------------------

_ENTITY_TYPE_PATTERNS: Dict[str, List[str]] = {
    r"bug[s]?|fix(?:es)?|fixed|patch(?:es)?": ["BUG"],
    r"feature[s]?|enhancement[s]?": ["FEATURE"],
    r"decision[s]?|decided|chose|selected": ["DECISION"],
    r"task[s]?|todo[s]?|action[s]?": ["TASK"],
    r"conversation[s]?|chat[s]?|session[s]?": ["CONVERSATION"],
    r"terminal|shell|command[s]?": ["TERMINAL_ACTIVITY"],
    r"file[s]?|upload[s]?|document[s]?": ["FILE_ACTIVITY"],
    r"browser|web|url": ["BROWSER_ACTIVITY"],
    r"desktop|vnc|novnc": ["DESKTOP_ACTIVITY"],
    r"user[s]?|account[s]?": ["USER"],
    r"secret[s]?|credential[s]?|key[s]?": ["SECRET", "SECRET_USAGE"],
}

_TIME_PATTERNS: Dict[str, Any] = {
    r"\btoday\b": lambda: {"start": datetime.now(tz=timezone.utc).date()},
    r"\byesterday\b": lambda: {
        "start": datetime.now(tz=timezone.utc).date() - timedelta(days=1),
        "end": datetime.now(tz=timezone.utc).date() - timedelta(days=1),
    },
    r"\bthis week\b": lambda: {
        "start": datetime.now(tz=timezone.utc).date() - timedelta(days=datetime.now(tz=timezone.utc).weekday())
    },
    r"\blast (\d+) days?\b": lambda m: {
        "start": datetime.now(tz=timezone.utc).date() - timedelta(days=int(m.group(1)))
    },
    r"\bthis month\b": lambda: {"start": datetime.now(tz=timezone.utc).date().replace(day=1)},
}

_STATUS_PATTERNS: Dict[str, List[str]] = {
    r"\b(completed?|finished|done|resolved)\b": ["completed"],
    r"\b(active|in.?progress|working on|started)\b": ["active"],
    r"\b(pending|planned|todo|not started)\b": ["pending"],
    r"\b(archived?)\b": ["archived"],
}


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class QueryIntent:
    """Structured intent extracted from a natural-language query."""

    entity_types: List[str] = field(default_factory=list)
    time_range: Dict[str, date] | None = None
    status_filter: List[str] | None = None
    semantic_query: str = ""
    keywords: List[str] = field(default_factory=list)


@dataclass
class SearchResult:
    """A single ranked search result from the memory graph."""

    entity: Dict[str, Any]
    score: float
    semantic_score: float
    keyword_score: float
    matched_keywords: List[str]
    explanation: str


# ---------------------------------------------------------------------------
# HybridScorer
# ---------------------------------------------------------------------------


class HybridScorer:
    """
    Combines cosine similarity and BM25 scoring for memory graph results.

    BM25 parameters follow Robertson et al. (k1=1.5, b=0.75).
    """

    _BM25_K1 = 1.5
    _BM25_B = 0.75
    _SEMANTIC_WEIGHT = 0.6
    _KEYWORD_WEIGHT = 0.4

    def bm25_score(
        self,
        query_terms: List[str],
        document_terms: List[str],
        avg_doc_len: float = 50.0,
    ) -> float:
        """
        Compute BM25 score for a document against a list of query terms.

        Args:
            query_terms:  Tokenized query words (lower-case).
            document_terms: Tokenized document words (lower-case).
            avg_doc_len:  Average document length for corpus normalisation.

        Returns:
            Non-negative BM25 score.
        """
        if not query_terms or not document_terms:
            return 0.0

        doc_len = len(document_terms)
        term_freqs: Dict[str, int] = {}
        for term in document_terms:
            term_freqs[term] = term_freqs.get(term, 0) + 1

        score = 0.0
        for term in set(query_terms):
            tf = term_freqs.get(term, 0)
            if tf == 0:
                continue
            idf = math.log(1 + (1.0 / (tf + 0.5)))
            numerator = tf * (self._BM25_K1 + 1)
            denominator = tf + self._BM25_K1 * (1 - self._BM25_B + self._BM25_B * doc_len / max(avg_doc_len, 1))
            score += idf * (numerator / denominator)

        return score

    @staticmethod
    def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
        """
        Compute cosine similarity between two vectors.

        Returns 0.0 for zero-length or mismatched vectors.
        """
        if not vec_a or not vec_b or len(vec_a) != len(vec_b):
            return 0.0

        dot = sum(a * b for a, b in zip(vec_a, vec_b))
        mag_a = math.sqrt(sum(a * a for a in vec_a))
        mag_b = math.sqrt(sum(b * b for b in vec_b))

        if mag_a == 0.0 or mag_b == 0.0:
            return 0.0

        return dot / (mag_a * mag_b)

    def combined_score(
        self,
        semantic_score: float,
        keyword_score: float,
    ) -> float:
        """Return weighted combination of semantic and keyword scores."""
        return self._SEMANTIC_WEIGHT * semantic_score + self._KEYWORD_WEIGHT * keyword_score


# ---------------------------------------------------------------------------
# MemoryGraphQueryProcessor
# ---------------------------------------------------------------------------


class MemoryGraphQueryProcessor:
    """
    Natural-language query → structured hybrid search pipeline.

    Stages:
        1. Intent extraction (entity types, time range, status, keywords)
        2. Redis filter construction
        3. Query embedding generation
        4. Hybrid search (Redis + vector scoring)
        5. BM25 re-ranking

    The Redis client and embedding model are injected once at construction;
    no per-call Redis initialisation is performed.
    """

    def __init__(self, redis_client: Any, embedding_model: str | None = None):
        """
        Args:
            redis_client:    Async Redis client (already connected, knowledge DB).
            embedding_model: Ollama model name.  Falls back to
                             config["knowledge.embedding_model"] or
                             "nomic-embed-text".
        """
        self._redis = redis_client
        self._scorer = HybridScorer()
        if embedding_model:
            self._embedding_model = embedding_model
        else:
            # ssot_config is a Pydantic model; use getattr with fallback
            self._embedding_model = getattr(ssot_config, "embedding_model", "nomic-embed-text")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_query(
        self,
        query: str,
        filters: Dict[str, Any] | None = None,
        limit: int = 10,
    ) -> List[SearchResult]:
        """
        Execute a hybrid memory graph search.

        Args:
            query:   Natural language search string.
            filters: Optional explicit overrides (entity_types, status, etc.).
            limit:   Maximum number of results to return.

        Returns:
            Ranked list of SearchResult objects.
        """
        if not query or not query.strip():
            return []

        intent = self._extract_intent(query)

        # Allow caller-supplied filters to override extracted intent
        if filters:
            if "entity_types" in filters:
                intent.entity_types = filters["entity_types"]
            if "status" in filters:
                intent.status_filter = filters["status"]

        redis_query = self._build_redis_query(intent)

        candidates, query_embedding = await asyncio.gather(
            self._redis_search(redis_query, limit * 5),
            self._generate_embedding(intent.semantic_query or query),
        )

        results = self._score_and_rank(candidates, query_embedding, intent, limit)
        logger.info("process_query returned %d results for query %r", len(results), query)
        return results

    # ------------------------------------------------------------------
    # Stage 1 — intent extraction
    # ------------------------------------------------------------------

    def _extract_intent(self, query: str) -> QueryIntent:
        """Extract structured intent from a natural-language query string."""
        q = query.lower()
        intent = QueryIntent(semantic_query=query)

        # Entity types
        for pattern, types in _ENTITY_TYPE_PATTERNS.items():
            if re.search(pattern, q):
                for t in types:
                    if t not in intent.entity_types:
                        intent.entity_types.append(t)

        # Time range
        for pattern, handler in _TIME_PATTERNS.items():
            m = re.search(pattern, q)
            if m:
                try:
                    if callable(handler):
                        # Some handlers accept a match arg, others don't
                        try:
                            intent.time_range = handler(m)
                        except TypeError:
                            intent.time_range = handler()
                except Exception:
                    pass
                break

        # Status
        for pattern, statuses in _STATUS_PATTERNS.items():
            if re.search(pattern, q):
                intent.status_filter = statuses
                break

        # Keywords: simple whitespace tokenisation, remove stop words
        intent.keywords = self._extract_keywords(query)

        return intent

    @staticmethod
    def _extract_keywords(query: str) -> List[str]:
        _STOP = {
            "a",
            "an",
            "the",
            "and",
            "or",
            "but",
            "in",
            "on",
            "at",
            "to",
            "for",
            "of",
            "with",
            "by",
            "from",
            "up",
            "about",
            "into",
            "through",
            "during",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "have",
            "has",
            "had",
            "do",
            "does",
            "did",
            "will",
            "would",
            "could",
            "should",
            "may",
            "might",
            "can",
            "what",
            "which",
            "who",
            "when",
            "where",
            "why",
            "how",
            "all",
            "both",
            "we",
            "i",
            "you",
            "it",
            "me",
            "my",
            "our",
            "your",
            "its",
        }
        words = re.findall(r"[a-z0-9_]+", query.lower())
        return [w for w in words if w not in _STOP and len(w) > 2]

    # ------------------------------------------------------------------
    # Stage 2 — Redis filter construction
    # ------------------------------------------------------------------

    def _build_redis_query(self, intent: QueryIntent) -> str:
        """Build an FT.SEARCH query string from an extracted intent."""
        parts: List[str] = []

        if intent.entity_types:
            # TAG filter: @type:{BUG|FEATURE}
            tag_val = "|".join(intent.entity_types)
            parts.append(f"@type:{{{tag_val}}}")

        if intent.status_filter:
            tag_val = "|".join(intent.status_filter)
            parts.append(f"@status:{{{tag_val}}}")

        if intent.time_range:
            start = intent.time_range.get("start")
            end = intent.time_range.get("end")
            if start:
                start_ms = int(
                    datetime.combine(start, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp() * 1000
                )
                end_ms = "+inf"
                if end:
                    end_ms = str(
                        int(datetime.combine(end, datetime.max.time()).replace(tzinfo=timezone.utc).timestamp() * 1000)
                    )
                parts.append(f"@created_at:[{start_ms} {end_ms}]")

        if intent.keywords:
            kw_query = " ".join(intent.keywords)
            parts.append(f"({kw_query})")

        return " ".join(parts) if parts else "*"

    # ------------------------------------------------------------------
    # Stage 3 — embedding generation
    # ------------------------------------------------------------------

    async def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate a vector embedding via the canonical NPU/Ollama fallback helper.

        Returns an empty list if the embedding service is unavailable.
        """
        if not text:
            return []
        from services.npu_client import generate_embedding_with_fallback

        embedding = await generate_embedding_with_fallback(text, model_name=self._embedding_model)
        return embedding or []

    # ------------------------------------------------------------------
    # Stage 4 — Redis candidate retrieval
    # ------------------------------------------------------------------

    async def _redis_search(self, redis_query: str, limit: int) -> List[Dict[str, Any]]:
        """Execute FT.SEARCH on memory_entity_idx and return entity dicts."""
        try:
            raw = await self._redis.execute_command(
                "FT.SEARCH",
                "memory_entity_idx",
                redis_query,
                "LIMIT",
                "0",
                str(limit),
            )
            keys = self._parse_ft_results(raw)
            return await self._fetch_entities_by_keys(keys)
        except Exception as exc:
            logger.warning("Redis FT.SEARCH failed (%s); using scan fallback", exc)
            return await self._scan_fallback(limit)

    @staticmethod
    def _parse_ft_results(raw: Any) -> List[str]:
        """Parse raw FT.SEARCH output into entity key strings.

        FT.SEARCH returns: [total, key1, [field, val, ...], key2, ...]
        """
        keys: List[str] = []
        if not raw or len(raw) <= 1:
            return keys

        i = 1
        while i < len(raw):
            key = raw[i]
            if isinstance(key, bytes):
                key = key.decode("utf-8")
            keys.append(key)
            i += 1
            if i < len(raw) and isinstance(raw[i], list):
                i += 1
        return keys

    async def _scan_fallback(self, limit: int) -> List[Dict[str, Any]]:
        """Fallback: scan memory:entity:* keys when FT.SEARCH unavailable."""
        keys: List[str] = []
        try:
            async for key in self._redis.scan_iter(match="memory:entity:*"):
                if isinstance(key, bytes):
                    key = key.decode("utf-8")
                keys.append(key)
                if len(keys) >= limit:
                    break
        except Exception as exc:
            logger.warning("Redis scan fallback failed: %s", exc)
            return []

        return await self._fetch_entities_by_keys(keys)

    async def _fetch_entities_by_keys(self, keys: List[str]) -> List[Dict[str, Any]]:
        """Batch-fetch JSON entities from Redis."""
        if not keys:
            return []
        try:
            pipe = self._redis.pipeline()
            for key in keys:
                pipe.json().get(key)
            results = await pipe.execute()
            return [r for r in results if r is not None]
        except Exception as exc:
            logger.warning("Batch entity fetch failed: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Stage 5 — scoring and ranking
    # ------------------------------------------------------------------

    def _score_and_rank(
        self,
        candidates: List[Dict[str, Any]],
        query_embedding: List[float],
        intent: QueryIntent,
        limit: int,
    ) -> List[SearchResult]:
        """Score candidates with hybrid scorer and return top-N."""
        if not candidates:
            return []

        scored: List[SearchResult] = []
        query_terms = intent.keywords

        for entity in candidates:
            entity_text_terms = self._entity_to_terms(entity)
            kw_raw = self._scorer.bm25_score(query_terms, entity_text_terms)
            # Normalise BM25 to [0, 1] (soft cap at 5.0)
            kw_score = min(kw_raw / 5.0, 1.0) if kw_raw > 0 else 0.0

            entity_emb = entity.get("_embedding", [])
            sem_score = (
                self._scorer.cosine_similarity(query_embedding, entity_emb) if query_embedding and entity_emb else 0.0
            )

            combined = self._scorer.combined_score(sem_score, kw_score)

            matched = [t for t in query_terms if t in entity_text_terms]

            explanation = (
                f"combined={combined:.3f} "
                f"(semantic={sem_score:.3f} x {HybridScorer._SEMANTIC_WEIGHT}, "
                f"keyword={kw_score:.3f} x {HybridScorer._KEYWORD_WEIGHT})"
            )

            scored.append(
                SearchResult(
                    entity=entity,
                    score=combined,
                    semantic_score=sem_score,
                    keyword_score=kw_score,
                    matched_keywords=matched,
                    explanation=explanation,
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:limit]

    @staticmethod
    def _entity_to_terms(entity: Dict[str, Any]) -> List[str]:
        """Tokenise an entity's searchable text fields into lower-case terms."""
        parts: List[str] = []
        name = entity.get("name", "")
        if name:
            parts.extend(re.findall(r"[a-z0-9_]+", name.lower()))

        entity_type = entity.get("type", "")
        if entity_type:
            parts.extend(re.findall(r"[a-z0-9_]+", entity_type.lower()))

        for obs in entity.get("observations", []):
            if obs:
                parts.extend(re.findall(r"[a-z0-9_]+", obs.lower()))

        return parts


# ---------------------------------------------------------------------------
# ensure_indexes — standalone coroutine (exported from package)
# ---------------------------------------------------------------------------


async def ensure_indexes(redis_client: Any) -> None:
    """
    Create the FT.CREATE indexes required by the memory graph.

    Idempotent: skips index creation if the index already exists.

    Indexes created:
        memory_entity_idx   — primary entity index (TAG + TEXT + NUMERIC)
        memory_fulltext_idx — phonetic full-text index

    Args:
        redis_client: Async Redis client connected to the knowledge database.
    """
    await asyncio.gather(
        _ensure_entity_idx(redis_client),
        _ensure_fulltext_idx(redis_client),
    )


async def _ensure_entity_idx(redis_client: Any) -> None:
    index_name = "memory_entity_idx"
    if await _index_exists(redis_client, index_name):
        logger.debug("Index %s already exists, skipping creation", index_name)
        return
    try:
        await redis_client.execute_command(
            "FT.CREATE",
            index_name,
            "ON",
            "JSON",
            "PREFIX",
            "1",
            "memory:entity:",
            "SCHEMA",
            "$.type",
            "AS",
            "type",
            "TAG",
            "SORTABLE",
            "$.name",
            "AS",
            "name",
            "TEXT",
            "WEIGHT",
            "2.0",
            "SORTABLE",
            "$.observations[*]",
            "AS",
            "observations",
            "TEXT",
            "$.created_at",
            "AS",
            "created_at",
            "NUMERIC",
            "SORTABLE",
            "$.updated_at",
            "AS",
            "updated_at",
            "NUMERIC",
            "SORTABLE",
            "$.metadata.priority",
            "AS",
            "priority",
            "TAG",
            "$.metadata.status",
            "AS",
            "status",
            "TAG",
            "SORTABLE",
            "$.metadata.tags[*]",
            "AS",
            "tags",
            "TAG",
            "SEPARATOR",
            ",",
            "$.metadata.session_id",
            "AS",
            "session_id",
            "TAG",
        )
        logger.info("Created Redis search index: %s", index_name)
    except Exception as exc:
        logger.warning("Could not create index %s: %s", index_name, exc)


async def _ensure_fulltext_idx(redis_client: Any) -> None:
    index_name = "memory_fulltext_idx"
    if await _index_exists(redis_client, index_name):
        logger.debug("Index %s already exists, skipping creation", index_name)
        return
    try:
        await redis_client.execute_command(
            "FT.CREATE",
            index_name,
            "ON",
            "JSON",
            "PREFIX",
            "1",
            "memory:entity:",
            "LANGUAGE",
            "english",
            "SCHEMA",
            "$.name",
            "AS",
            "name",
            "TEXT",
            "PHONETIC",
            "dm:en",
            "$.observations[*]",
            "AS",
            "content",
            "TEXT",
        )
        logger.info("Created Redis search index: %s", index_name)
    except Exception as exc:
        logger.warning("Could not create index %s: %s", index_name, exc)


async def _index_exists(redis_client: Any, index_name: str) -> bool:
    try:
        info = await redis_client.execute_command("FT.INFO", index_name)
        return info is not None
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Public exports
# ---------------------------------------------------------------------------

__all__ = [
    "MemoryGraphQueryProcessor",
    "HybridScorer",
    "SearchResult",
    "QueryIntent",
    "ensure_indexes",
]
