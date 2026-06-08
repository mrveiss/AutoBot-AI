# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) mrveiss. All rights reserved.
# AutoBot - AI-Powered Automation Platform
"""
Memory Graph Hybrid Scorer — Phase 2.

Issue #3384: Hybrid scoring combining semantic similarity (cosine) and
keyword relevance (BM25-style TF-IDF) for memory-graph entity search.

Scoring formula:
    score = SEMANTIC_WEIGHT * cosine_similarity(q_embed, entity_embed)
          + KEYWORD_WEIGHT  * bm25_score(keywords, entity_text)

Both components are normalised to [0.0, 1.0] before combination so that
neither dominates purely because of scale differences.

Entity embeddings are retrieved from Redis (key ``mg:entity_embed:<id>``)
where they are stored by the indexer that accompanies Phase 1 of issue #3385.
When an embedding is absent the semantic score defaults to 0.0 and only the
keyword score contributes.
"""

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Scoring weights
# ---------------------------------------------------------------------------

SEMANTIC_WEIGHT: float = 0.6
KEYWORD_WEIGHT: float = 0.4

# BM25 parameters
_BM25_K1: float = 1.2
_BM25_B: float = 0.75

# Redis key prefix where entity embeddings are stored by the indexer
_ENTITY_EMBED_KEY_PREFIX = "mg:entity_embed:"


# ---------------------------------------------------------------------------
# Data structure
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """A ranked result from the memory-graph hybrid search."""

    entity: Dict[str, Any]
    score: float  # combined hybrid score [0.0, 1.0]
    semantic_score: float  # cosine similarity [0.0, 1.0]
    keyword_score: float  # BM25 keyword relevance [0.0, 1.0]
    matched_keywords: List[str] = field(default_factory=list)
    explanation: str = ""


# ---------------------------------------------------------------------------
# HybridScorer
# ---------------------------------------------------------------------------


class HybridScorer(AsyncRedisClientMixin):
    """
    Combines cosine-similarity (semantic) and BM25 (keyword) scores.

    Issue #3384 — Phase 2.

    Designed to be instantiated once and reused across requests.
    All methods are synchronous except ``score_and_rank`` which fetches
    entity embeddings from Redis asynchronously.
    """

    _redis_database = "knowledge"

    def __init__(self, redis_client=None) -> None:
        """
        Args:
            redis_client: Optional async Redis client for embedding lookups.
                          When None a client is acquired lazily on first use.
        """
        if redis_client is not None:
            self._redis = redis_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def score_and_rank(
        self,
        query: str,
        intent: Any,  # QueryIntent — avoid circular import; duck-typed
        candidates: List[Dict[str, Any]],
        query_embedding: List[float] | None,
        limit: int = 10,
    ) -> List["SearchResult"]:
        """
        Score all candidates and return the top *limit* results.

        Args:
            query:           Original user query (for explanation text).
            intent:          QueryIntent produced by the query processor.
            candidates:      Entity dicts returned by Redis FT.SEARCH.
            query_embedding: Pre-computed query embedding, or None.
            limit:           Maximum results to return.

        Returns:
            Sorted list of SearchResult (highest score first).
        """
        keywords = getattr(intent, "keywords", [])
        results: List[SearchResult] = []
        redis = await self._get_redis()

        for entity in candidates:
            entity_text = _entity_to_text(entity)
            entity_id = entity.get("id", "")

            # Semantic score
            entity_embedding = await _fetch_entity_embedding(entity_id, redis)
            sem_score = (
                cosine_similarity(query_embedding, entity_embedding) if query_embedding and entity_embedding else 0.0
            )

            # Keyword (BM25) score
            kw_score, matched = self.bm25_score(keywords, entity_text)

            # Combined score
            combined = SEMANTIC_WEIGHT * sem_score + KEYWORD_WEIGHT * kw_score

            results.append(
                SearchResult(
                    entity=entity,
                    score=round(combined, 4),
                    semantic_score=round(sem_score, 4),
                    keyword_score=round(kw_score, 4),
                    matched_keywords=matched,
                    explanation=_build_explanation(sem_score, kw_score, combined, matched),
                )
            )

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Cosine similarity
    # ------------------------------------------------------------------

    @staticmethod
    def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
        """Return cosine similarity in [0.0, 1.0] between two vectors."""
        return cosine_similarity(vec_a, vec_b)

    # ------------------------------------------------------------------
    # BM25 keyword scoring
    # ------------------------------------------------------------------

    def bm25_score(
        self,
        keywords: List[str],
        document: str,
        avg_doc_length: float = 150.0,
    ) -> tuple:  # (float, List[str])
        """
        Compute a normalised BM25 score for *keywords* against *document*.

        The score is normalised to [0.0, 1.0] by dividing by the maximum
        possible per-term score (k1 + 1) times the number of keywords,
        so results are directly comparable across documents of varying length.

        Args:
            keywords:        List of query term strings (already lower-cased).
            document:        Full entity text to score against.
            avg_doc_length:  Average document length in tokens used for BM25
                             length normalisation (default: 150 tokens).

        Returns:
            Tuple of (normalised_score, matched_keyword_list).
        """
        if not keywords or not document:
            return 0.0, []

        doc_lower = document.lower()
        doc_tokens = doc_lower.split()
        doc_length = len(doc_tokens)

        raw_score = 0.0
        matched: List[str] = []

        for term in keywords:
            tf = doc_tokens.count(term)
            if tf == 0:
                continue

            matched.append(term)
            # BM25 TF component (IDF set to 1 — single-document context)
            tf_component = (tf * (_BM25_K1 + 1)) / (
                tf + _BM25_K1 * (1 - _BM25_B + _BM25_B * doc_length / avg_doc_length)
            )
            raw_score += tf_component

        if not matched:
            return 0.0, []

        # Normalise: max per-term score is k1+1 when tf dominates
        max_possible = (_BM25_K1 + 1) * len(keywords)
        normalised = min(raw_score / max_possible, 1.0)
        return round(normalised, 4), matched


# ---------------------------------------------------------------------------
# Module-level helpers (exported for direct use / testing)
# ---------------------------------------------------------------------------


def cosine_similarity(vec_a: List[float] | None, vec_b: List[float] | None) -> float:
    """
    Compute cosine similarity between two float vectors.

    Returns a value in [0.0, 1.0].  Returns 0.0 when either vector is
    None, empty, or has zero magnitude.
    """
    if not vec_a or not vec_b:
        return 0.0

    if len(vec_a) != len(vec_b):
        logger.warning(
            "cosine_similarity: dimension mismatch %d vs %d",
            len(vec_a),
            len(vec_b),
        )
        return 0.0

    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))

    if mag_a == 0.0 or mag_b == 0.0:
        return 0.0

    # Clamp to [0, 1] — cosine can be slightly outside due to float rounding
    return max(0.0, min(1.0, dot / (mag_a * mag_b)))


def _entity_to_text(entity: Dict[str, Any]) -> str:
    """
    Build a weighted text representation of an entity for BM25 scoring.

    Applies the same weights used for embedding generation:
      name × 3  (weight 0.3)
      type × 1  (weight 0.1)
      observations × 6  (weight 0.6)
    """
    name = entity.get("name", "")
    entity_type = entity.get("type", "")
    observations = entity.get("observations", [])

    if isinstance(observations, str):
        # May arrive as a JSON string when parsed from Redis hash fields
        try:
            observations = json.loads(observations)
        except (ValueError, json.JSONDecodeError):
            observations = [observations]

    obs_text = " ".join(str(o) for o in observations)

    parts = [
        f"{name} " * 3,
        entity_type,
        f"{obs_text} " * 6,
    ]
    return " ".join(p.strip() for p in parts if p.strip())


def _build_explanation(
    sem_score: float,
    kw_score: float,
    combined: float,
    matched_keywords: List[str],
) -> str:
    """Produce a human-readable explanation of the hybrid score."""
    kw_part = f"keywords matched: {', '.join(matched_keywords)}" if matched_keywords else "no keyword matches"
    return (
        f"score={combined:.2f} "
        f"(semantic={sem_score:.2f} × {SEMANTIC_WEIGHT}, "
        f"keyword={kw_score:.2f} × {KEYWORD_WEIGHT}); "
        f"{kw_part}"
    )


async def _fetch_entity_embedding(
    entity_id: str,
    redis_client: Any,
) -> List[float] | None:
    """
    Retrieve a pre-computed entity embedding from Redis.

    Returns None if the embedding has not yet been indexed so that the
    caller can degrade gracefully to keyword-only scoring.

    Args:
        entity_id:    Entity UUID (without key prefix).
        redis_client: Async Redis client — caller supplies to avoid N connections.
    """
    if not entity_id:
        return None

    try:
        key = f"{_ENTITY_EMBED_KEY_PREFIX}{entity_id}"
        raw = await redis_client.get(key)
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.debug("Failed to fetch entity embedding for %s: %s", entity_id, exc)

    return None
