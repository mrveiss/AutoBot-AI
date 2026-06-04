# Copyright (c) mrveiss. All rights reserved.
# AutoBot - AI-Powered Automation Platform
"""
Memory Graph Query Processor — Phase 1 & 2.

Issue #3384: Core infrastructure for semantic search over memory-graph entities.

5-stage pipeline:
  Stage 1  Intent extraction  (pattern matching — time, entity type, status)
  Stage 2  Filter generation  (Redis FT.SEARCH query string)
  Stage 3  Query embedding    (via existing npu_client fallback)
  Stage 4  Hybrid search      (Redis candidates + vector ranking)
  Stage 5  Result ranking     (HybridScorer — semantic + BM25)

Redis key layout (read-only; written by autobot_memory_graph):
  memory:entity:<uuid>   JSON — entity document
  FT index name          memory_entity_idx
"""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_redis_client
from knowledge.memory_graph.hybrid_scorer import HybridScorer, SearchResult

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_EMBEDDING_CACHE_TTL_SECONDS = 3600  # 1 hour L2 cache for query embeddings
_EMBEDDING_CACHE_KEY_PREFIX = "mg:embed:"
_RESULT_CACHE_TTL_SECONDS = 300  # 5 minutes L2 cache for search results
_RESULT_CACHE_KEY_PREFIX = "mg:search:"

_DEFAULT_CANDIDATE_LIMIT = 50  # Redis candidates before vector ranking
_DEFAULT_RESULT_LIMIT = 10

_FT_INDEX = "memory_entity_idx"
_ENTITY_KEY_PREFIX = "memory:entity:"

# Intent pattern tables
_TIME_PATTERNS: List[Tuple[str, Any]] = [
    (r"\btoday\b", lambda: {"start": datetime.now(tz=timezone.utc).date()}),
    (
        r"\byesterday\b",
        lambda: {"start": (datetime.now(tz=timezone.utc) - timedelta(days=1)).date()},
    ),
    (
        r"\bthis week\b",
        lambda: {
            "start": (datetime.now(tz=timezone.utc) - timedelta(days=datetime.now(tz=timezone.utc).weekday())).date()
        },
    ),
    (
        r"\blast (\d+) days?\b",
        lambda m: {"start": (datetime.now(tz=timezone.utc) - timedelta(days=int(m.group(1)))).date()},
    ),
    (
        r"\bthis month\b",
        lambda: {"start": datetime.now(tz=timezone.utc).replace(day=1).date()},
    ),
]

_ENTITY_TYPE_PATTERNS: List[Tuple[str, List[str]]] = [
    (r"\bbugs?\b", ["bug_fix"]),
    (r"\bfix(es)?\b", ["bug_fix"]),
    (r"\bfeatures?\b", ["feature"]),
    (r"\bdecisions?\b", ["decision"]),
    (r"\btasks?\b", ["task"]),
    (r"\bconversations?\b", ["conversation"]),
]

_STATUS_PATTERNS: List[Tuple[str, str]] = [
    (r"\b(worked on|completed|finished|fixed)\b", "completed"),
    (r"\b(started|began|working on|in progress)\b", "in_progress"),
    (r"\b(planned|todo|pending)\b", "pending"),
    (r"\bactive\b", "active"),
]

# Stopwords to strip before keyword extraction
_STOPWORDS = frozenset(
    {
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
        "we",
        "i",
        "me",
        "us",
        "you",
        "he",
        "she",
        "it",
        "they",
        "what",
        "which",
        "who",
        "whom",
        "this",
        "that",
        "these",
        "those",
        "show",
        "find",
        "get",
        "tell",
        "give",
        "list",
        "me",
    }
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class QueryIntent:
    """Structured intent extracted from a natural language query."""

    entity_types: List[str] = field(default_factory=list)
    time_range: Dict[str, Any] | None = None
    status_filter: str | None = None
    keywords: List[str] = field(default_factory=list)
    semantic_query: str = ""


# ---------------------------------------------------------------------------
# MemoryGraphQueryProcessor
# ---------------------------------------------------------------------------


class MemoryGraphQueryProcessor:
    """
    Natural language query processor for memory-graph entities.

    Issue #3384: Phase 1 (core infrastructure) + Phase 2 (hybrid scoring).

    Usage::

        processor = MemoryGraphQueryProcessor()
        results = await processor.process_query("What bugs did we fix today?")

    The processor is stateless except for the injected Redis client, so a
    single shared instance per application process is safe.
    """

    def __init__(
        self,
        redis_client=None,
        candidate_limit: int = _DEFAULT_CANDIDATE_LIMIT,
    ) -> None:
        """
        Initialise processor.

        Args:
            redis_client: Async aioredis client pointing at the *knowledge*
                database.  When None the processor lazily fetches one via
                ``get_redis_client``.
            candidate_limit: Maximum entities pulled from Redis before vector
                ranking (keeps latency bounded).
        """
        self._redis = redis_client
        self._candidate_limit = candidate_limit
        self._scorer = HybridScorer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def process_query(
        self,
        query: str,
        filters: Dict[str, Any] | None = None,
        limit: int = _DEFAULT_RESULT_LIMIT,
    ) -> List[SearchResult]:
        """
        Run the 5-stage hybrid search pipeline.

        Args:
            query:   Natural language query string.
            filters: Optional caller-supplied structured filters that are
                     merged with intent-extracted filters.
            limit:   Maximum results to return.

        Returns:
            Ranked list of SearchResult objects (highest score first).
        """
        query = (query or "").strip()
        if not query:
            logger.warning("process_query called with empty query")
            return []

        t_start = time.monotonic()

        # Stage 1: intent extraction
        intent = self._extract_intent(query)
        if filters:
            _merge_filters(intent, filters)

        # Stage 2: build Redis query string
        redis_query = _build_redis_query(intent)

        # Stages 3 & 4 run concurrently
        embedding_task = asyncio.create_task(self._get_query_embedding(intent.semantic_query or query))
        candidates_task = asyncio.create_task(self._fetch_candidates(redis_query, self._candidate_limit))

        query_embedding, candidates = await asyncio.gather(embedding_task, candidates_task)

        if not candidates:
            logger.info("No candidates found for query: %s", query)
            return []

        # Stage 5: hybrid score + rank
        results = await self._scorer.score_and_rank(
            query=query,
            intent=intent,
            candidates=candidates,
            query_embedding=query_embedding,
            limit=limit,
        )

        elapsed_ms = (time.monotonic() - t_start) * 1000
        logger.info(
            "process_query completed in %.1f ms, %d/%d results returned",
            elapsed_ms,
            len(results),
            len(candidates),
        )
        return results

    async def get_entity(self, entity_id: str) -> Dict[str, Any] | None:
        """
        Retrieve a single entity document by its UUID.

        Args:
            entity_id: UUID string (without the ``memory:entity:`` prefix).

        Returns:
            Entity dict, or None if not found.
        """
        redis = await self._get_redis()
        key = f"{_ENTITY_KEY_PREFIX}{entity_id}"
        try:
            doc = await redis.json().get(key)
            return doc
        except Exception as exc:
            logger.warning("get_entity failed for %s: %s", entity_id, exc)
            return None

    async def get_entity_by_name(self, name: str) -> Dict[str, Any] | None:
        """
        Retrieve the first entity matching *name* exactly.

        Args:
            name: Exact entity name string.

        Returns:
            Entity dict, or None if not found.
        """
        redis = await self._get_redis()
        # Escape RediSearch special chars in the name
        safe_name = re.sub(r"([-@!(){}[\]/\\^$*?.,|:;])", r"\\\1", name)
        ft_query = f"@name:({safe_name})"
        try:
            raw = await redis.execute_command(
                "FT.SEARCH",
                _FT_INDEX,
                ft_query,
                "LIMIT",
                "0",
                "1",
            )
            entities = _parse_ft_results(raw)
            return entities[0] if entities else None
        except Exception as exc:
            logger.warning("get_entity_by_name failed for %s: %s", name, exc)
            return None

    async def get_related_entities(
        self,
        entity_name: str,
        relation_type: str | None = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        """
        Retrieve entities related to the given entity via the relations index.

        Args:
            entity_name:   Name of the source entity.
            relation_type: If given, filter to this relation type only.
            limit:         Maximum relations to follow.

        Returns:
            List of related entity dicts.
        """
        redis = await self._get_redis()
        # Relations are keyed by UUID; resolve name → UUID via FT.SEARCH first
        # Key prefix matches schema.py RELATIONS_OUT_PREFIX = "memory:relations:out:"
        source = await self.get_entity_by_name(entity_name)
        if not source:
            return []
        rel_key = f"memory:relations:out:{source['id']}"
        try:
            raw_json = await redis.json().get(rel_key)
            if not raw_json:
                return []
            doc = raw_json if isinstance(raw_json, dict) else {}
            relations: List[Dict[str, Any]] = doc.get("relations", [])
        except Exception as exc:
            logger.warning("Failed to read relations for %s: %s", entity_name, exc)
            return []

        if relation_type:
            relations = [r for r in relations if r.get("type") == relation_type]

        related: List[Dict[str, Any]] = []
        for rel in relations[:limit]:
            target_name = rel.get("to", "")
            if not target_name:
                continue
            entity = await self.get_entity_by_name(target_name)
            if entity:
                related.append(entity)

        return related

    # ------------------------------------------------------------------
    # Stage 1: Intent extraction
    # ------------------------------------------------------------------

    def _extract_intent(self, query: str) -> QueryIntent:
        """Extract structured intent from a natural language query."""
        query_lower = query.lower()
        intent = QueryIntent(semantic_query=query)

        # Time filters — try each pattern; handlers accept an optional match
        intent.time_range = _extract_time_range(query_lower)

        # Entity type filters
        for pattern, types in _ENTITY_TYPE_PATTERNS:
            if re.search(pattern, query_lower):
                for t in types:
                    if t not in intent.entity_types:
                        intent.entity_types.append(t)

        # Status filters
        for pattern, status in _STATUS_PATTERNS:
            if re.search(pattern, query_lower):
                intent.status_filter = status
                break

        # Keywords for hybrid scoring
        intent.keywords = self._extract_keywords(query_lower)

        # Derive a clean semantic query by removing stop words
        semantic_terms = [k for k in query_lower.split() if k not in _STOPWORDS]
        intent.semantic_query = " ".join(semantic_terms) if semantic_terms else query

        return intent

    def _extract_keywords(self, text: str) -> List[str]:
        """Extract non-stopword alphabetic tokens from text."""
        tokens = re.findall(r"[a-z]+", text.lower())
        return [t for t in tokens if t not in _STOPWORDS and len(t) > 2]

    # ------------------------------------------------------------------
    # Stage 3: Embedding
    # ------------------------------------------------------------------

    async def _get_query_embedding(self, semantic_query: str) -> List[float] | None:
        """
        Return an embedding vector for *semantic_query*.

        Checks the Redis L2 embedding cache first; generates via the NPU
        client fallback on a miss.
        """
        if not semantic_query:
            return None

        cache_key = _embedding_cache_key(semantic_query)
        redis = await self._get_redis()

        # L2 cache read
        try:
            cached = await redis.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as exc:
            logger.debug("Embedding cache read failed: %s", exc)

        # Generate via NPU worker / Ollama fallback
        embedding = await _generate_embedding(semantic_query)

        # L2 cache write (best-effort)
        if embedding:
            try:
                await redis.setex(
                    cache_key,
                    _EMBEDDING_CACHE_TTL_SECONDS,
                    json.dumps(embedding),
                )
            except Exception as exc:
                logger.debug("Embedding cache write failed: %s", exc)

        return embedding

    # ------------------------------------------------------------------
    # Stage 4: Redis candidate retrieval
    # ------------------------------------------------------------------

    async def _fetch_candidates(self, redis_query: str, limit: int) -> List[Dict[str, Any]]:
        """
        Execute FT.SEARCH to retrieve entity candidates.

        Falls back to a scan-based approach if the full-text index is
        unavailable (e.g., development without RediSearch).
        """
        redis = await self._get_redis()
        try:
            raw = await redis.execute_command(
                "FT.SEARCH",
                _FT_INDEX,
                redis_query,
                "LIMIT",
                "0",
                str(limit),
            )
            return _parse_ft_results(raw)
        except Exception as exc:
            logger.warning("FT.SEARCH failed (%s), falling back to scan", exc)
            return await self._scan_fallback(limit)

    async def _scan_fallback(self, limit: int) -> List[Dict[str, Any]]:
        """Scan Redis for entity keys when FT index is unavailable."""
        redis = await self._get_redis()
        entities: List[Dict[str, Any]] = []
        try:
            async for key in redis.scan_iter(match=f"{_ENTITY_KEY_PREFIX}*", count=100):
                if len(entities) >= limit:
                    break
                doc = await redis.json().get(key)
                if doc:
                    entities.append(doc)
        except Exception as exc:
            logger.warning("scan_fallback failed: %s", exc)
        return entities

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _get_redis(self):
        """Lazily obtain the async Redis client."""
        if self._redis is None:
            self._redis = await get_redis_client(async_client=True, database="knowledge")
        return self._redis


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _extract_time_range(query_lower: str) -> Dict[str, Any] | None:
    """Try each time pattern and return the first match."""
    for pattern, handler in _TIME_PATTERNS:
        m = re.search(pattern, query_lower)
        if m:
            try:
                # Handlers that need the match object accept it positionally
                return handler(m)
            except TypeError:
                return handler()
    return None


def _build_redis_query(intent: QueryIntent) -> str:
    """
    Translate a QueryIntent into a RediSearch FT.SEARCH query string.

    Returns ``*`` (match all) when no intent filters are present so that
    the caller always gets candidates to vector-rank.
    """
    parts: List[str] = []

    if intent.entity_types:
        type_filter = "|".join(intent.entity_types)
        parts.append(f"@type:({type_filter})")

    if intent.status_filter:
        parts.append(f"@status:{{{intent.status_filter}}}")

    if intent.time_range and intent.time_range.get("start"):
        start_dt = intent.time_range["start"]
        # created_at stored as ms-since-epoch integer
        if hasattr(start_dt, "timetuple"):
            ts = int(datetime(start_dt.year, start_dt.month, start_dt.day).timestamp() * 1000)
        else:
            ts = int(start_dt) * 1000
        parts.append(f"@created_at:[{ts} +inf]")

    return " ".join(parts) if parts else "*"


def _merge_filters(intent: QueryIntent, filters: Dict[str, Any]) -> None:
    """Merge caller-supplied filters into an extracted intent (in-place)."""
    if "entity_types" in filters:
        for t in filters["entity_types"]:
            if t not in intent.entity_types:
                intent.entity_types.append(t)

    if "time_range" in filters and intent.time_range is None:
        intent.time_range = filters["time_range"]

    if "status" in filters and intent.status_filter is None:
        intent.status_filter = filters["status"]


def _parse_ft_results(raw: Any) -> List[Dict[str, Any]]:
    """
    Parse raw FT.SEARCH response into a list of entity dicts.

    Redis returns: [total_count, key1, [field, value, ...], key2, ...]
    When RETURN is not specified every stored field is returned.
    """
    if not raw or not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return []

    entities: List[Dict[str, Any]] = []
    # Results start at index 1; each entry is (key, field_list) pairs
    i = 1
    while i < len(raw):
        key = raw[i]
        if isinstance(key, bytes):
            key = key.decode("utf-8", errors="replace")

        fields_raw = raw[i + 1] if i + 1 < len(raw) else []
        entity: Dict[str, Any] = {}

        if isinstance(fields_raw, (list, tuple)):
            # Interleaved [field, value, field, value, ...]
            for j in range(0, len(fields_raw) - 1, 2):
                fname = fields_raw[j]
                fval = fields_raw[j + 1]
                if isinstance(fname, bytes):
                    fname = fname.decode("utf-8", errors="replace")
                if isinstance(fval, bytes):
                    fval = fval.decode("utf-8", errors="replace")
                # Try JSON decode for list/dict fields
                try:
                    entity[fname] = json.loads(fval)
                except (TypeError, ValueError, json.JSONDecodeError):
                    entity[fname] = fval

        # Ensure we have at least the Redis key
        if not entity:
            entity["_key"] = key

        entities.append(entity)
        i += 2

    return entities


def _embedding_cache_key(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{_EMBEDDING_CACHE_KEY_PREFIX}{digest}"


async def _generate_embedding(text: str) -> List[float] | None:
    """
    Generate a text embedding using the NPU worker / Ollama fallback.

    Imports lazily to avoid circular imports and to allow the module to be
    imported in test environments where the service is mocked.
    """
    try:
        from autobot_shared.ssot_config import config
        from services.npu_client import generate_embedding_with_fallback

        model_name = config.get("knowledge.embedding_model", "nomic-embed-text")
        return await generate_embedding_with_fallback(text, model_name=model_name)
    except Exception as exc:
        logger.warning("Embedding generation failed: %s", exc)
        return None
