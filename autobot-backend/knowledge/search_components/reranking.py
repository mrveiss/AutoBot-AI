# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Result Reranking Module

Issue #381: Extracted from search.py god class refactoring.
Contains cross-encoder reranking functionality.
"""

import asyncio
import logging
import math
import threading
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


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

    def _apply_rerank_scores(self, results: List[Dict[str, Any]], scores: list) -> None:
        """Apply rerank scores to results.

        Issue #281: Extracted helper.
        Issue #1533: Normalize raw cross-encoder logits with sigmoid
        so rerank_score stays in 0-1 range. Combine with original
        similarity score instead of overwriting it.
        """
        for i, result in enumerate(results):
            # Sigmoid: raw logits → 0-1 probability
            normalized = 1.0 / (1.0 + math.exp(-float(scores[i])))
            original_score = result.get("score", 0)
            result["original_score"] = original_score
            result["rerank_score"] = normalized * 0.8 + original_score * 0.2
        results.sort(key=lambda x: x.get("rerank_score", 0), reverse=True)
        for result in results:
            result["score"] = result.get("rerank_score", 0)

    async def rerank(
        self, query: str, results: List[Dict[str, Any]], top_k: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Rerank results using cross-encoder for improved relevance.

        Issue #281 refactor.

        Args:
            query: Search query
            results: Search results to rerank
            top_k: Optional limit on returned results

        Returns:
            Reranked results list
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
            self._apply_rerank_scores(results, scores)

            return results[:top_k] if top_k else results

        except Exception as e:
            logger.error("Reranking failed: %s", e)
            return results


# Module-level CrossEncoder singleton (Issue #1549: shared per-worker to avoid
# 400MB+ duplication when multiple instances each load their own copy).
_cross_encoder_model = None
_cross_encoder_lock = threading.Lock()


def get_cross_encoder():
    """Return the process-wide CrossEncoder model (thread-safe, lazy-loaded).

    Issue #1549: Loading CrossEncoder once per worker process and sharing it
    across all callers eliminates per-instance duplication (~100MB each).
    """
    global _cross_encoder_model
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
                    _cross_encoder_model = None
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
