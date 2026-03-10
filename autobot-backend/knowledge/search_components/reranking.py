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
        """Ensure cross-encoder model is loaded. Issue #281: Extracted helper."""
        from sentence_transformers import CrossEncoder

        if self._cross_encoder is None:
            self._cross_encoder = await asyncio.to_thread(CrossEncoder, self.MODEL_NAME)
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
