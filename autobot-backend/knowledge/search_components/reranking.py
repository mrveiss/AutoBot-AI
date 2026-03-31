# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Result Reranking Module

Issue #381: Extracted from search.py god class refactoring.
Contains cross-encoder reranking functionality.
Issue #2004: Configurable blend weights (RerankWeights, compute_blended_score,
recency_score) replace the hardcoded 0.8/0.2 split.
"""

import asyncio
import logging
import math
import threading
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RerankWeights:
    """Blend weights for multi-factor reranker scoring.

    Issue #2004: Replaces the hardcoded 0.8 * reranker + 0.2 * vector split.
    Weights do not need to sum to 1.0; compute_blended_score normalises them.

    Attributes:
        reranker:   Weight for the cross-encoder reranker score.
        vector:     Weight for the original vector-similarity score.
        edge:       Weight for graph edge strength (Neural Mesh phase 3+).
        recency:    Weight for time-based recency score (Neural Mesh phase 3+).
        staleness:  Weight for staleness penalty; 0 disables it (Issue #2111).
        mmr_lambda: MMR diversity trade-off (Issue #2090).
                    0.0 = disabled (pure relevance ordering, backward-compatible).
                    Values in (0, 1] apply MMR after cross-encoder scoring:
                    score = λ * relevance - (1-λ) * max_sim_to_selected.
    """

    reranker: float = 0.8
    vector: float = 0.2
    edge: float = 0.0
    recency: float = 0.0
    staleness: float = (
        0.0  # Issue #2111: penalty weight for stale documents (0 = disabled)
    )
    mmr_lambda: float = 0.0  # Issue #2090: MMR diversity pass (0 = disabled)


def recency_score(days_since_access: float) -> float:
    """Return a 0-1 recency score that decays with age.

    Issue #2004: Used by compute_blended_score when RerankWeights.recency > 0.

    Args:
        days_since_access: Number of days since the document was last accessed.

    Returns:
        1.0 for a document accessed today, approaching 0 for very old ones.
        Formula: 1 / (1 + days_since_access).
    """
    return 1.0 / (1.0 + days_since_access)


def staleness_penalty(staleness_score: float) -> float:
    """Convert a staleness score (0-1) to a penalty factor (1-0).

    Issue #2111: Used by compute_blended_score when RerankWeights.staleness > 0.
    Fresh documents (staleness=0) get factor 1.0 (no penalty).
    Very stale documents (staleness=1) get factor 0.0 (maximum penalty).

    Args:
        staleness_score: BFS-propagated staleness value from staleness_propagator.

    Returns:
        Penalty factor in range [0.0, 1.0].
    """
    return max(0.0, 1.0 - staleness_score)


def _cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Return cosine similarity between two equal-length float vectors.

    Issue #2090: Used by apply_mmr_reorder to measure redundancy between results.
    Returns 0.0 when either vector is all-zeros.
    """
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


def apply_mmr_reorder(
    results: List[Dict[str, Any]],
    mmr_lambda: float,
    embedding_key: str = "embedding",
    score_key: str = "rerank_score",
) -> List[Dict[str, Any]]:
    """Re-order results with Maximal Marginal Relevance (MMR) to reduce redundancy.

    Issue #2090: Applied after cross-encoder reranking when mmr_lambda > 0.

    MMR score formula:
        mmr(doc) = λ * relevance(doc) - (1-λ) * max_sim(doc, already_selected)

    Args:
        results:       Reranked result dicts (sorted by score_key descending).
        mmr_lambda:    Trade-off parameter in [0, 1].
                       1.0 → pure relevance (identity permutation).
                       0.0 → pure diversity (maximise minimum similarity distance).
        embedding_key: Key under which each result dict stores its embedding vector.
                       Results without this key fall back to using score_key only,
                       treating all pairwise similarities as 0.
        score_key:     Key holding the normalised relevance score (0–1).

    Returns:
        New list with the same results re-ordered for diversity.  When every
        result lacks an embedding the function degrades gracefully and returns
        the original order.
    """
    if not results or mmr_lambda >= 1.0:
        return results

    selected: List[Dict[str, Any]] = []
    remaining = list(results)

    # Pre-extract embeddings once to avoid repeated dict lookups
    embeddings: List[Optional[List[float]]] = [r.get(embedding_key) for r in remaining]
    has_embeddings = any(e is not None for e in embeddings)

    while remaining:
        best_idx = 0
        best_mmr = float("-inf")

        for i, candidate in enumerate(remaining):
            relevance = candidate.get(score_key, 0.0)

            if has_embeddings and embeddings[i] is not None:
                # Max cosine similarity to any already-selected document
                selected_with_emb = [s for s in selected if s.get(embedding_key) is not None]
                if selected_with_emb:
                    max_sim = max(
                        _cosine_similarity(embeddings[i], sel[embedding_key])
                        for sel in selected_with_emb
                    )
                else:
                    max_sim = 0.0
            else:
                max_sim = 0.0

            mmr_score = mmr_lambda * relevance - (1.0 - mmr_lambda) * max_sim
            if mmr_score > best_mmr:
                best_mmr = mmr_score
                best_idx = i

        selected.append(remaining.pop(best_idx))
        if has_embeddings:
            embeddings.pop(best_idx)

    logger.debug(
        "MMR reorder applied (lambda=%.2f): %d results reordered",
        mmr_lambda,
        len(selected),
    )
    return selected


def compute_blended_score(
    reranker_score: float,
    vector_score: float,
    edge_weight: float = 0.0,
    recency_score_value: float = 0.0,
    staleness_penalty_value: float = 1.0,
    weights: Optional[RerankWeights] = None,
) -> float:
    """Compute a weighted blend of reranker, vector, edge, recency, and staleness scores.

    Issue #2004: Replaces the hardcoded 0.8 * reranker + 0.2 * original
    expression in _apply_rerank_scores().
    Issue #2111: Adds optional staleness penalty term.

    Weights are normalised so that callers do not need to ensure they sum
    to exactly 1.0.  If the total weight is 0 the function falls back to
    the plain reranker score.

    Args:
        reranker_score:        Sigmoid-normalised cross-encoder score (0-1).
        vector_score:          Original vector-similarity score (0-1).
        edge_weight:           Graph edge strength contribution (0-1).
        recency_score_value:   Time-based recency score (0-1).
        staleness_penalty_value: staleness_penalty() output (1=fresh, 0=max stale).
        weights:               RerankWeights instance; defaults to RerankWeights().

    Returns:
        Blended score in the same 0-1 range.
    """
    if weights is None:
        weights = RerankWeights()

    total_weight = (
        weights.reranker
        + weights.vector
        + weights.edge
        + weights.recency
        + weights.staleness
    )
    if total_weight == 0.0:
        logger.warning("All RerankWeights are zero; returning raw reranker score")
        return reranker_score

    blended = (
        weights.reranker * reranker_score
        + weights.vector * vector_score
        + weights.edge * edge_weight
        + weights.recency * recency_score_value
        + weights.staleness * staleness_penalty_value
    )
    return blended / total_weight


class ResultReranker:
    """
    Reranks search results using a cross-encoder model.

    Uses the MS MARCO MiniLM model for efficient relevance scoring.
    """

    MODEL_NAME = "cross-encoder/ms-marco-MiniLM-L-6-v2"

    def __init__(self):
        """Initialize reranker."""
        self._cross_encoder = None

    async def _ensure_cross_encoder(self):
        """Return process-wide CrossEncoder model. Issue #281: Extracted helper.

        Issue #1549: Delegates to module-level get_cross_encoder() to ensure
        only one model instance exists per worker process.
        """
        if self._cross_encoder is None:
            self._cross_encoder = await asyncio.to_thread(get_cross_encoder)
        return self._cross_encoder

    def _apply_rerank_scores(
        self,
        results: List[Dict[str, Any]],
        scores: list,
        weights: Optional[RerankWeights] = None,
    ) -> None:
        """Apply rerank scores to results.

        Issue #281: Extracted helper.
        Issue #1533: Normalize raw cross-encoder logits with sigmoid
        so rerank_score stays in 0-1 range. Combine with original
        similarity score instead of overwriting it.
        Issue #2004: Blend is now driven by compute_blended_score() so
        caller-supplied weights replace the former hardcoded 0.8/0.2 split.
        """
        effective_weights = weights if weights is not None else RerankWeights()
        for i, result in enumerate(results):
            # Sigmoid: raw logits → 0-1 probability
            normalized = 1.0 / (1.0 + math.exp(-float(scores[i])))
            original_score = result.get("score", 0)
            result["original_score"] = original_score
            result["rerank_score"] = compute_blended_score(
                reranker_score=normalized,
                vector_score=original_score,
                weights=effective_weights,
            )
        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        for result in results:
            result["score"] = result.get("rerank_score", 0)

    async def rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        weights: Optional[RerankWeights] = None,
    ) -> List[Dict[str, Any]]:
        """
        Rerank results using cross-encoder for improved relevance.

        Issue #281 refactor.
        Issue #2004: Optional weights parameter forwards blend configuration
        to _apply_rerank_scores(); defaults to RerankWeights() (0.8/0.2).

        Args:
            query:   Search query.
            results: Search results to rerank.
            top_k:   Optional limit on returned results.
            weights: Optional RerankWeights for multi-factor blending.

        Returns:
            Reranked results list.
        """
        try:
            try:
                from sentence_transformers import CrossEncoder  # noqa: F401
            except ImportError:
                logger.warning("CrossEncoder not available, skipping reranking")
                return results

            if not results:
                return results

            cross_encoder = await self._ensure_cross_encoder()
            pairs = [(query, r.get("content", "")) for r in results]
            scores = await asyncio.to_thread(cross_encoder.predict, pairs)
            self._apply_rerank_scores(results, scores, weights=weights)

            # Issue #2090: optional MMR diversity pass after cross-encoder scoring
            effective_weights = weights if weights is not None else RerankWeights()
            if effective_weights.mmr_lambda > 0.0:
                results = apply_mmr_reorder(results, effective_weights.mmr_lambda)

            return results[:top_k] if top_k else results

        except Exception as e:
            logger.error("Reranking failed: %s", e)
            return results


# Module-level CrossEncoder singleton (Issue #1549: shared per-worker to avoid
# 400MB+ duplication when multiple instances each load their own copy).
#
# Issue #1562: sentinel distinguishes "not yet loaded" (None) from "load failed"
# (_LOAD_FAILED) so that a non-ImportError load failure does not cause
# get_cross_encoder() to retry the expensive model load on every subsequent call.
_LOAD_FAILED = object()
_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()


def get_cross_encoder():
    """Return the process-wide CrossEncoder model (thread-safe, lazy-loaded).

    Issue #1549: Loading CrossEncoder once per worker process and sharing it
    across all callers eliminates per-instance duplication (~100MB each).

    Issue #1562: Returns None for both the ImportError case (library absent)
    and the permanent-failure case (_LOAD_FAILED sentinel). The sentinel
    prevents retrying a failed load on every subsequent call.
    """
    global _cross_encoder_model
    if _cross_encoder_model is _LOAD_FAILED:
        return None
    if _cross_encoder_model is None:
        with _cross_encoder_lock:
            if _cross_encoder_model is None:
                try:
                    from sentence_transformers import CrossEncoder

                    logger.info(
                        "Loading shared CrossEncoder model: %s",
                        ResultReranker.MODEL_NAME,
                    )
                    _cross_encoder_model = CrossEncoder(ResultReranker.MODEL_NAME)
                    logger.info("Shared CrossEncoder model loaded successfully")
                except ImportError:
                    logger.warning(
                        "sentence-transformers not available, CrossEncoder disabled"
                    )
                    _cross_encoder_model = None
                except Exception as exc:
                    logger.error("Failed to load CrossEncoder model: %s", exc)
                    _cross_encoder_model = _LOAD_FAILED
    if _cross_encoder_model is _LOAD_FAILED:
        return None
    return _cross_encoder_model


# Module-level instance for convenience (thread-safe, Issue #613)
_reranker = None
_reranker_lock = threading.Lock()


def get_reranker() -> ResultReranker:
    """Get the shared ResultReranker instance (thread-safe).

    Uses double-check locking pattern to ensure thread safety while
    minimizing lock contention after initialization (Issue #613).
    """
    global _reranker
    if _reranker is None:
        with _reranker_lock:
            # Double-check after acquiring lock
            if _reranker is None:
                _reranker = ResultReranker()
    return _reranker
