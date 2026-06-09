# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for configurable reranker blend weights.

Issue #2004: Verifies RerankWeights, compute_blended_score, and recency_score.
"""

from knowledge.search_components.reranking import (
    RerankWeights,
    compute_blended_score,
    recency_score,
)


class TestDefaultWeightsMatchLegacy:
    """Default RerankWeights reproduce the old hardcoded 0.8/0.2 blend."""

    def test_default_weights_match_legacy(self):
        """compute_blended_score with defaults equals 0.8*reranker + 0.2*vector."""
        reranker = 0.9
        vector = 0.5
        expected = 0.8 * reranker + 0.2 * vector
        result = compute_blended_score(reranker_score=reranker, vector_score=vector)
        assert abs(result - expected) < 1e-9

    def test_default_weights_dataclass(self):
        """RerankWeights() defaults are 0.8/0.2/0.0/0.0."""
        w = RerankWeights()
        assert w.reranker == 0.8
        assert w.vector == 0.2
        assert w.edge == 0.0
        assert w.recency == 0.0

    def test_explicit_default_weights_equal_no_weights(self):
        """Passing RerankWeights() explicitly produces the same result as no weights."""
        reranker, vector = 0.7, 0.3
        assert compute_blended_score(reranker, vector) == compute_blended_score(
            reranker, vector, weights=RerankWeights()
        )


class TestCustomBlend:
    """Custom weight configurations produce the correct weighted sum."""

    def test_reranker_only_weights(self):
        """All weight on reranker returns reranker score unchanged."""
        w = RerankWeights(reranker=1.0, vector=0.0)
        result = compute_blended_score(0.75, 0.25, weights=w)
        assert abs(result - 0.75) < 1e-9

    def test_vector_only_weights(self):
        """All weight on vector returns vector score unchanged."""
        w = RerankWeights(reranker=0.0, vector=1.0)
        result = compute_blended_score(0.75, 0.25, weights=w)
        assert abs(result - 0.25) < 1e-9

    def test_equal_four_factor_blend(self):
        """Equal weights across all four factors produce simple average."""
        w = RerankWeights(reranker=1.0, vector=1.0, edge=1.0, recency=1.0)
        result = compute_blended_score(
            reranker_score=0.8,
            vector_score=0.4,
            edge_weight=0.6,
            recency_score_value=0.2,
            weights=w,
        )
        expected = (0.8 + 0.4 + 0.6 + 0.2) / 4.0
        assert abs(result - expected) < 1e-9

    def test_unnormalised_weights_are_normalised(self):
        """Weights that do not sum to 1 are normalised inside the function."""
        w = RerankWeights(reranker=4.0, vector=1.0)
        result = compute_blended_score(1.0, 0.0, weights=w)
        # After normalisation: 4/5 * 1.0 + 1/5 * 0.0 = 0.8
        assert abs(result - 0.8) < 1e-9

    def test_custom_three_factor_blend(self):
        """Three-factor blend matches manual calculation."""
        w = RerankWeights(reranker=0.5, vector=0.3, edge=0.2)
        reranker, vector, edge = 0.9, 0.6, 0.4
        expected = 0.5 * reranker + 0.3 * vector + 0.2 * edge
        result = compute_blended_score(reranker, vector, edge_weight=edge, weights=w)
        assert abs(result - expected) < 1e-9


class TestRecencyScore:
    """recency_score() returns the correct decay value."""

    def test_zero_days(self):
        """A document accessed today has recency score 1.0."""
        assert recency_score(0.0) == 1.0

    def test_one_day(self):
        """A document accessed one day ago has recency score 0.5."""
        assert abs(recency_score(1.0) - 0.5) < 1e-9

    def test_nine_days(self):
        """A document accessed nine days ago has recency score 0.1."""
        assert abs(recency_score(9.0) - 0.1) < 1e-9

    def test_monotone_decreasing(self):
        """Recency score strictly decreases as days_since_access increases."""
        scores = [recency_score(float(d)) for d in range(10)]
        for a, b in zip(scores, scores[1:]):
            assert a > b

    def test_always_positive(self):
        """Recency score is always positive, even for very large values."""
        assert recency_score(1_000_000.0) > 0.0
