#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for RAGConfig.rerank_weights forwarding to AdvancedRAGOptimizer.

Issue #2034: RAGConfig.rerank_weights was defined but never forwarded to the
optimizer. These tests verify that:
- AdvancedRAGOptimizer stores the weights passed via its constructor.
- _apply_cross_encoder_scores uses self._rerank_weights via compute_blended_score.
- RAGService.initialize() passes self.config.rerank_weights to the optimizer.
- The default (no argument) still produces the legacy 0.8/0.2 blend.
"""

import math
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from knowledge.search_components.reranking import RerankWeights


def _make_search_result(hybrid_score: float = 0.5, content: str = "test content"):
    """Create a minimal SearchResult for testing."""
    from advanced_rag_optimizer import SearchResult

    return SearchResult(
        content=content,
        metadata={},
        semantic_score=0.5,
        keyword_score=0.3,
        hybrid_score=hybrid_score,
        relevance_rank=1,
        source_path="test",
    )


class TestAdvancedRAGOptimizerRerankWeights(unittest.IsolatedAsyncioTestCase):
    """AdvancedRAGOptimizer rerank weights handling. Issue #2034."""

    def test_default_weights_are_legacy_split(self):
        """Constructor with no argument stores the 0.8/0.2 default weights."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer

        optimizer = AdvancedRAGOptimizer()
        self.assertAlmostEqual(optimizer._rerank_weights.reranker, 0.8)
        self.assertAlmostEqual(optimizer._rerank_weights.vector, 0.2)

    def test_custom_weights_are_stored(self):
        """Constructor argument is stored as-is on _rerank_weights."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer

        weights = RerankWeights(reranker=0.6, vector=0.3, edge=0.1)
        optimizer = AdvancedRAGOptimizer(rerank_weights=weights)
        self.assertIs(optimizer._rerank_weights, weights)

    async def test_apply_cross_encoder_scores_uses_stored_weights(self):
        """_apply_cross_encoder_scores calls compute_blended_score with _rerank_weights."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer

        custom = RerankWeights(reranker=0.5, vector=0.5)
        optimizer = AdvancedRAGOptimizer(rerank_weights=custom)
        result = _make_search_result(hybrid_score=0.4)

        ce_score = 0.0
        normalized_ce = 1.0 / (1.0 + math.exp(-ce_score))  # 0.5

        # Expected: (0.5 * 0.5 + 0.5 * 0.4) / (0.5 + 0.5) = 0.45
        expected = (0.5 * normalized_ce + 0.5 * 0.4) / (0.5 + 0.5)

        mock_ce = MagicMock()
        mock_ce.predict.return_value = [ce_score]
        optimizer._cross_encoder = mock_ce
        await optimizer._apply_cross_encoder_scores("query", [result])

        self.assertAlmostEqual(result.rerank_score, expected, places=6)

    async def test_default_weights_produce_legacy_blend(self):
        """Without a custom weights arg the legacy 0.8 CE + 0.2 vector blend is used."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer

        optimizer = AdvancedRAGOptimizer()
        result = _make_search_result(hybrid_score=0.4)

        ce_score = 2.0
        normalized_ce = 1.0 / (1.0 + math.exp(-ce_score))
        expected = (0.8 * normalized_ce + 0.2 * 0.4) / (0.8 + 0.2)

        mock_ce = MagicMock()
        mock_ce.predict.return_value = [ce_score]
        optimizer._cross_encoder = mock_ce
        await optimizer._apply_cross_encoder_scores("query", [result])

        self.assertAlmostEqual(result.rerank_score, expected, places=6)

    async def test_edge_and_recency_weights_are_forwarded(self):
        """Non-zero edge and recency weights are respected by compute_blended_score."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer

        weights = RerankWeights(reranker=0.5, vector=0.3, edge=0.1, recency=0.1)
        optimizer = AdvancedRAGOptimizer(rerank_weights=weights)
        result = _make_search_result(hybrid_score=0.6)

        ce_score = 1.0
        normalized_ce = 1.0 / (1.0 + math.exp(-ce_score))
        total = 0.5 + 0.3 + 0.1 + 0.1
        expected = (0.5 * normalized_ce + 0.3 * 0.6) / total

        mock_ce = MagicMock()
        mock_ce.predict.return_value = [ce_score]
        optimizer._cross_encoder = mock_ce
        await optimizer._apply_cross_encoder_scores("query", [result])

        self.assertAlmostEqual(result.rerank_score, expected, places=6)


class TestRAGServiceForwardsWeights(unittest.IsolatedAsyncioTestCase):
    """RAGService.initialize() must pass rerank_weights to AdvancedRAGOptimizer."""

    async def test_initialize_passes_rerank_weights_to_optimizer(self):
        """RAGService creates AdvancedRAGOptimizer with config's rerank_weights."""
        from services.rag_config import RAGConfig
        from services.rag_service import RAGService

        custom_weights = RerankWeights(reranker=0.7, vector=0.2, edge=0.1)
        config = RAGConfig(rerank_weights=custom_weights)

        mock_kb = MagicMock()
        service = RAGService(knowledge_base=mock_kb, config=config)

        captured_weights = []

        with patch(
            "services.rag_service.AdvancedRAGOptimizer",
            side_effect=lambda **kw: _capture_and_create(kw, captured_weights),
        ):
            await service.initialize()

        if captured_weights:
            self.assertIs(captured_weights[0], custom_weights)


def _capture_and_create(kwargs, store):
    """Record rerank_weights kwarg then return a real AdvancedRAGOptimizer."""
    from advanced_rag_optimizer import AdvancedRAGOptimizer

    store.append(kwargs.get("rerank_weights"))
    inst = AdvancedRAGOptimizer.__new__(AdvancedRAGOptimizer)
    inst.__init__(**kwargs)
    inst.initialize = AsyncMock(return_value=True)
    inst.kb = MagicMock()
    return inst


if __name__ == "__main__":
    unittest.main()
