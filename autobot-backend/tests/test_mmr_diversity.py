#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for MMR (Maximal Marginal Relevance) diversity scoring.

Issue #2090: Validates apply_mmr_reorder, RerankWeights.mmr_lambda,
RAGConfig.mmr_lambda, and ResultReranker MMR integration.

Acceptance criteria tested:
- Disabled (lambda=0): results unchanged, backward-compatible.
- Moderate diversity (lambda=0.5): diverse results preferred over redundant ones.
- High diversity (lambda=0.1): most diverse ordering selected.
- No embedding fallback: graceful degradation when embeddings absent.
- RAGConfig mmr_lambda propagates to rerank_weights.
"""

import math
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

from knowledge.search_components.reranking import (
    RerankWeights,
    _cosine_similarity,
    apply_mmr_reorder,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(
    content: str,
    score: float,
    embedding: List[float],
) -> Dict[str, Any]:
    """Return a minimal result dict with embedding attached."""
    return {
        "content": content,
        "rerank_score": score,
        "score": score,
        "embedding": embedding,
    }


def _unit(components: List[float]) -> List[float]:
    """Return a unit-normalised vector."""
    magnitude = math.sqrt(sum(c * c for c in components))
    if magnitude == 0.0:
        return components
    return [c / magnitude for c in components]


# ---------------------------------------------------------------------------
# _cosine_similarity
# ---------------------------------------------------------------------------


class TestCosineSimilarity(unittest.TestCase):
    """Unit tests for the _cosine_similarity helper (Issue #2090)."""

    def test_identical_vectors_return_one(self):
        vec = _unit([1.0, 2.0, 3.0])
        self.assertAlmostEqual(_cosine_similarity(vec, vec), 1.0, places=6)

    def test_orthogonal_vectors_return_zero(self):
        a = _unit([1.0, 0.0, 0.0])
        b = _unit([0.0, 1.0, 0.0])
        self.assertAlmostEqual(_cosine_similarity(a, b), 0.0, places=6)

    def test_opposite_vectors_return_minus_one(self):
        a = _unit([1.0, 0.0])
        b = _unit([-1.0, 0.0])
        self.assertAlmostEqual(_cosine_similarity(a, b), -1.0, places=6)

    def test_zero_vector_returns_zero(self):
        self.assertEqual(_cosine_similarity([0.0, 0.0], [1.0, 2.0]), 0.0)


# ---------------------------------------------------------------------------
# apply_mmr_reorder — disabled (lambda == 0)
# ---------------------------------------------------------------------------


class TestMMRDisabled(unittest.TestCase):
    """apply_mmr_reorder with lambda=0 must be a no-op (backward-compatible)."""

    def _results(self) -> List[Dict[str, Any]]:
        return [
            _make_result("alpha", 0.9, _unit([1.0, 0.0])),
            _make_result("beta", 0.8, _unit([0.9, 0.1])),
            _make_result("gamma", 0.7, _unit([0.0, 1.0])),
        ]

    def test_lambda_zero_returns_original_list(self):
        """lambda=0 should return the same list object unchanged."""
        results = self._results()
        reordered = apply_mmr_reorder(results, mmr_lambda=0.0)
        self.assertIs(reordered, results)

    def test_lambda_one_returns_original_list(self):
        """lambda=1 (pure relevance) is a trivial identity — return original."""
        results = self._results()
        reordered = apply_mmr_reorder(results, mmr_lambda=1.0)
        self.assertIs(reordered, results)

    def test_empty_results_returns_empty(self):
        self.assertEqual(apply_mmr_reorder([], mmr_lambda=0.5), [])


# ---------------------------------------------------------------------------
# apply_mmr_reorder — moderate diversity (lambda=0.5)
# ---------------------------------------------------------------------------


class TestMMRModerateDiversity(unittest.TestCase):
    """lambda=0.5 should prefer a diverse result over a redundant high-scorer."""

    def test_diverse_result_preferred_over_redundant(self):
        """
        Setup:
            result_a: score=0.9, embedding aligned with query direction
            result_b: score=0.85, embedding nearly identical to result_a (redundant)
            result_c: score=0.7, embedding orthogonal to result_a (diverse)

        With lambda=0.5 after selecting result_a, result_c should beat result_b
        because result_b is penalised by its high similarity to result_a.
        """
        emb_a = _unit([1.0, 0.0])
        emb_b = _unit([0.99, 0.141])  # near-duplicate of a
        emb_c = _unit([0.0, 1.0])  # orthogonal to a

        result_a = _make_result("doc_a", 0.9, emb_a)
        result_b = _make_result("doc_b", 0.85, emb_b)
        result_c = _make_result("doc_c", 0.7, emb_c)

        reordered = apply_mmr_reorder([result_a, result_b, result_c], mmr_lambda=0.5)

        self.assertEqual(reordered[0]["content"], "doc_a")
        # After selecting doc_a, doc_c (diverse) should be ranked before doc_b (redundant)
        self.assertEqual(reordered[1]["content"], "doc_c")
        self.assertEqual(reordered[2]["content"], "doc_b")

    def test_all_results_returned(self):
        """MMR must return every result — none are dropped."""
        results = [_make_result(f"doc_{i}", 1.0 - i * 0.1, _unit([float(i), 1.0])) for i in range(5)]
        reordered = apply_mmr_reorder(results, mmr_lambda=0.5)
        self.assertEqual(len(reordered), len(results))


# ---------------------------------------------------------------------------
# apply_mmr_reorder — high diversity (lambda=0.1)
# ---------------------------------------------------------------------------


class TestMMRHighDiversity(unittest.TestCase):
    """Low lambda (near 0) aggressively favours diversity over raw relevance.

    The MMR formula is: mmr(doc) = lambda * relevance - (1-lambda) * max_sim.
    lambda=1.0 is pure relevance; lambda=0.0 is pure diversity.
    A low lambda (e.g. 0.1) heavily weights the similarity penalty,
    causing near-duplicate documents to be ranked below diverse ones.
    """

    def test_low_lambda_strongly_penalises_duplicates(self):
        """
        Two near-identical high-scorers + one very different low-scorer.
        At lambda=0.1 (high diversity weight) the diverse low-scorer should
        be ranked 2nd because the near-duplicate is heavily penalised.
        """
        emb_dup = _unit([1.0, 0.01])
        emb_unique = _unit([0.0, 1.0])

        dup1 = _make_result("dup1", 0.95, emb_dup)
        dup2 = _make_result("dup2", 0.90, list(emb_dup))  # near copy
        unique = _make_result("unique", 0.60, emb_unique)

        reordered = apply_mmr_reorder([dup1, dup2, unique], mmr_lambda=0.1)

        self.assertEqual(reordered[0]["content"], "dup1")
        # unique should be promoted above dup2 due to strong diversity penalty on dup2
        self.assertEqual(reordered[1]["content"], "unique")
        self.assertEqual(reordered[2]["content"], "dup2")

    def test_single_result_unchanged(self):
        result = [_make_result("only", 0.9, _unit([1.0, 0.0]))]
        self.assertEqual(apply_mmr_reorder(result, mmr_lambda=0.9), result)


# ---------------------------------------------------------------------------
# apply_mmr_reorder — no embedding fallback
# ---------------------------------------------------------------------------


class TestMMRNoEmbedding(unittest.TestCase):
    """When results lack embeddings, MMR should degrade gracefully."""

    def test_no_embeddings_preserves_score_order(self):
        """Without embeddings, max_sim=0 for all → pure relevance ordering."""
        results = [{"content": f"doc_{i}", "rerank_score": 1.0 - i * 0.1} for i in range(4)]
        reordered = apply_mmr_reorder(results, mmr_lambda=0.5)
        scores = [r["rerank_score"] for r in reordered]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_mixed_embeddings_no_crash(self):
        """Mix of results with and without embeddings must not raise."""
        results = [
            _make_result("with_emb", 0.9, _unit([1.0, 0.0])),
            {"content": "no_emb", "rerank_score": 0.8},
        ]
        reordered = apply_mmr_reorder(results, mmr_lambda=0.5)
        self.assertEqual(len(reordered), 2)


# ---------------------------------------------------------------------------
# RerankWeights.mmr_lambda default
# ---------------------------------------------------------------------------


class TestRerankWeightsMMRLambda(unittest.TestCase):
    """RerankWeights should default mmr_lambda=0.0 (backward-compatible)."""

    def test_default_mmr_lambda_is_zero(self):
        weights = RerankWeights()
        self.assertEqual(weights.mmr_lambda, 0.0)

    def test_custom_mmr_lambda_stored(self):
        weights = RerankWeights(mmr_lambda=0.5)
        self.assertAlmostEqual(weights.mmr_lambda, 0.5)


# ---------------------------------------------------------------------------
# RAGConfig.mmr_lambda propagation
# ---------------------------------------------------------------------------


class TestRAGConfigMMRLambda(unittest.TestCase):
    """RAGConfig.mmr_lambda defaults to 0 and propagates to rerank_weights."""

    def test_default_mmr_lambda_is_zero(self):
        from services.rag_config import RAGConfig

        cfg = RAGConfig()
        self.assertEqual(cfg.mmr_lambda, 0.0)
        self.assertEqual(cfg.rerank_weights.mmr_lambda, 0.0)

    def test_top_level_mmr_lambda_propagates_to_rerank_weights(self):
        from services.rag_config import RAGConfig

        cfg = RAGConfig(mmr_lambda=0.7)
        self.assertAlmostEqual(cfg.mmr_lambda, 0.7)
        self.assertAlmostEqual(cfg.rerank_weights.mmr_lambda, 0.7)

    def test_explicit_rerank_weights_mmr_lambda_preserved(self):
        """If rerank_weights already carries mmr_lambda, top-level 0 must not overwrite."""
        from services.rag_config import RAGConfig

        weights = RerankWeights(mmr_lambda=0.3)
        cfg = RAGConfig(rerank_weights=weights)
        self.assertAlmostEqual(cfg.rerank_weights.mmr_lambda, 0.3)

    def test_invalid_mmr_lambda_raises(self):
        from services.rag_config import RAGConfig

        with self.assertRaises(ValueError):
            RAGConfig(mmr_lambda=1.5)

    def test_from_dict_round_trip(self):
        from services.rag_config import RAGConfig

        cfg = RAGConfig(mmr_lambda=0.4)
        d = cfg.to_dict()
        cfg2 = RAGConfig.from_dict(d)
        self.assertAlmostEqual(cfg2.mmr_lambda, 0.4)
        self.assertAlmostEqual(cfg2.rerank_weights.mmr_lambda, 0.4)


# ---------------------------------------------------------------------------
# ResultReranker MMR integration
# ---------------------------------------------------------------------------


class TestResultRerankerMMRIntegration(unittest.IsolatedAsyncioTestCase):
    """ResultReranker.rerank applies MMR when mmr_lambda > 0.

    These tests patch sentence_transformers in sys.modules so that the
    CrossEncoder availability check in rerank() does not cause an early return,
    and inject a mock _cross_encoder directly on the reranker instance to avoid
    loading a real model.
    """

    def setUp(self):
        """Inject a sentinel sentence_transformers stub so the import guard passes."""
        import sys

        # Stub out sentence_transformers so the `from sentence_transformers import
        # CrossEncoder` guard inside rerank() does not trigger ImportError.
        self._st_patcher = patch.dict(
            sys.modules,
            {
                "sentence_transformers": MagicMock(),
                "sentence_transformers.cross_encoder": MagicMock(),
            },
        )
        self._st_patcher.start()

    def tearDown(self):
        self._st_patcher.stop()

    def _make_results(self) -> List[Dict[str, Any]]:
        emb_a = _unit([1.0, 0.0])
        emb_b = _unit([0.99, 0.14])  # near-duplicate of a
        emb_c = _unit([0.0, 1.0])  # diverse
        return [
            {"content": "doc_a", "score": 0.9, "embedding": emb_a},
            {"content": "doc_b", "score": 0.85, "embedding": emb_b},
            {"content": "doc_c", "score": 0.7, "embedding": emb_c},
        ]

    def _make_reranker_with_mock_ce(self, predict_scores):
        """Return a ResultReranker with a mock cross-encoder pre-injected."""
        from knowledge.search_components.reranking import ResultReranker

        reranker = ResultReranker()
        mock_ce = MagicMock()
        mock_ce.predict.return_value = predict_scores
        reranker._cross_encoder = mock_ce
        return reranker

    async def test_mmr_disabled_when_lambda_zero(self):
        """With mmr_lambda=0, apply_mmr_reorder is not called."""
        reranker = self._make_reranker_with_mock_ce([2.0, 1.8, 1.0])
        results = self._make_results()

        weights = RerankWeights(mmr_lambda=0.0)

        with patch(
            "knowledge.search_components.reranking.apply_mmr_reorder",
            wraps=apply_mmr_reorder,
        ) as mock_mmr:
            await reranker.rerank("query", results, weights=weights)
            mock_mmr.assert_not_called()

    async def test_mmr_applied_when_lambda_positive(self):
        """With mmr_lambda=0.5, apply_mmr_reorder is called after scoring."""
        reranker = self._make_reranker_with_mock_ce([2.0, 1.9, 0.5])
        results = self._make_results()

        weights = RerankWeights(mmr_lambda=0.5)

        with patch(
            "knowledge.search_components.reranking.apply_mmr_reorder",
            wraps=apply_mmr_reorder,
        ) as mock_mmr:
            final = await reranker.rerank("query", results, weights=weights)
            mock_mmr.assert_called_once()

        # The diverse doc_c should appear before the near-duplicate doc_b
        contents = [r["content"] for r in final]
        self.assertIn("doc_c", contents)
        doc_b_pos = contents.index("doc_b")
        doc_c_pos = contents.index("doc_c")
        self.assertLess(doc_c_pos, doc_b_pos)

    async def test_mmr_does_not_drop_results(self):
        """MMR reorder must not drop any results."""
        reranker = self._make_reranker_with_mock_ce([2.0, 1.9, 0.5])
        results = self._make_results()

        weights = RerankWeights(mmr_lambda=0.5)
        final = await reranker.rerank("query", results, weights=weights)
        self.assertEqual(len(final), len(results))

    async def test_top_k_applied_after_mmr(self):
        """top_k slicing happens after the MMR reorder."""
        reranker = self._make_reranker_with_mock_ce([2.0, 1.9, 0.5])
        results = self._make_results()

        weights = RerankWeights(mmr_lambda=0.5)
        final = await reranker.rerank("query", results, top_k=2, weights=weights)
        self.assertEqual(len(final), 2)


if __name__ == "__main__":
    unittest.main()
