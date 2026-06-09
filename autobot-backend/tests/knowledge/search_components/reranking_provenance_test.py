# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for provenance-aware reranking (#4836).

Covers:
- provenance_adjustment() returns correct delta for each provenance value
- _apply_rerank_scores() boosts "extracted" above "inferred" above "ambiguous"
- Missing / None provenance is treated as "inferred" (no adjustment)
"""

import math

import pytest

from knowledge.search_components.reranking import (
    RerankWeights,
    ResultReranker,
    provenance_adjustment,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_result(
    score: float = 0.5,
    content: str = "text",
    source_provenance: str | None = None,
) -> dict:
    meta: dict = {}
    if source_provenance is not None:
        meta["source_provenance"] = source_provenance
    return {"chunk_id": "c1", "score": score, "content": content, "metadata": meta}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# =============================================================================
# Unit tests — provenance_adjustment()
# =============================================================================


class TestProvenanceAdjustment:
    def test_extracted_returns_positive_boost(self):
        assert provenance_adjustment("extracted") == pytest.approx(0.05)

    def test_inferred_returns_zero(self):
        assert provenance_adjustment("inferred") == pytest.approx(0.0)

    def test_ambiguous_returns_negative_penalty(self):
        assert provenance_adjustment("ambiguous") == pytest.approx(-0.05)

    def test_none_treated_as_inferred(self):
        assert provenance_adjustment(None) == pytest.approx(0.0)

    def test_unknown_value_returns_zero(self):
        assert provenance_adjustment("unknown_value") == pytest.approx(0.0)


# =============================================================================
# Integration tests — ResultReranker._apply_rerank_scores()
# =============================================================================


class TestApplyRerankScoresProvenance:
    """_apply_rerank_scores must consume source_provenance from result metadata."""

    def _reranker(self) -> ResultReranker:
        return ResultReranker()

    def test_extracted_ranks_above_inferred(self):
        """An extracted result outranks an inferred one with equal base scores."""
        reranker = self._reranker()
        extracted = _make_result(score=0.5, source_provenance="extracted")
        inferred = _make_result(score=0.5, source_provenance="inferred")
        # Both fed the same raw CE logit so only provenance differentiates them.
        reranker._apply_rerank_scores([extracted, inferred], scores=[0.0, 0.0])
        assert extracted["rerank_score"] > inferred["rerank_score"]

    def test_inferred_ranks_above_ambiguous(self):
        """An inferred result outranks an ambiguous one with equal base scores."""
        reranker = self._reranker()
        inferred = _make_result(score=0.5, source_provenance="inferred")
        ambiguous = _make_result(score=0.5, source_provenance="ambiguous")
        reranker._apply_rerank_scores([inferred, ambiguous], scores=[0.0, 0.0])
        assert inferred["rerank_score"] > ambiguous["rerank_score"]

    def test_extracted_ranks_above_ambiguous(self):
        """Extracted outranks ambiguous — end-to-end ordering."""
        reranker = self._reranker()
        extracted = _make_result(score=0.5, source_provenance="extracted")
        ambiguous = _make_result(score=0.5, source_provenance="ambiguous")
        reranker._apply_rerank_scores([extracted, ambiguous], scores=[0.0, 0.0])
        assert extracted["rerank_score"] > ambiguous["rerank_score"]

    def test_missing_provenance_neutral(self):
        """A result without source_provenance in metadata is unaffected."""
        reranker = self._reranker()
        # No metadata key at all
        no_meta = {"chunk_id": "c1", "score": 0.5, "content": "text"}
        inferred = _make_result(score=0.5, source_provenance="inferred")
        reranker._apply_rerank_scores([no_meta, inferred], scores=[0.0, 0.0])
        assert no_meta["rerank_score"] == pytest.approx(inferred["rerank_score"])

    def test_rerank_score_clamped_to_one(self):
        """A very high base score with extracted provenance does not exceed 1.0."""
        reranker = self._reranker()
        # logit=10 → sigmoid ≈ 0.9999954 → blended near 1; +0.05 boost must clamp
        result = _make_result(score=1.0, source_provenance="extracted")
        reranker._apply_rerank_scores([result], scores=[10.0])
        assert result["rerank_score"] <= 1.0

    def test_rerank_score_clamped_to_zero(self):
        """A very low base score with ambiguous provenance does not go below 0.0."""
        reranker = self._reranker()
        result = _make_result(score=0.0, source_provenance="ambiguous")
        reranker._apply_rerank_scores([result], scores=[-10.0])
        assert result["rerank_score"] >= 0.0

    def test_sort_order_reflects_provenance(self):
        """Results are sorted highest rerank_score first after provenance adjustment."""
        reranker = self._reranker()
        ambiguous = _make_result(score=0.5, source_provenance="ambiguous")
        extracted = _make_result(score=0.5, source_provenance="extracted")
        results = [ambiguous, extracted]
        reranker._apply_rerank_scores(results, scores=[0.0, 0.0])
        # After sort, extracted (higher score) must be first
        assert results[0]["rerank_score"] >= results[1]["rerank_score"]
        assert results[0] is extracted


# =============================================================================
# Interaction tests — staleness penalty × provenance boost (#4897)
# =============================================================================


class TestStalenessProvenanceInteraction:
    """Verify that the combined staleness penalty × provenance boost produces correct ordering.

    Issue #4897: _apply_rerank_scores() applies staleness penalty (multiplicative
    inside the blended score) then provenance adjustment (additive ±0.05).  The two
    effects must compose correctly so that a heavily-stale "extracted" result still
    ranks below a fresh "inferred" result.
    """

    def _reranker(self) -> ResultReranker:
        return ResultReranker()

    def test_stale_extracted_ranks_below_fresh_inferred(self):
        """Staleness penalty must outweigh the +0.05 extracted provenance boost.

        Setup (staleness weight = 0.5, reranker weight = 0.5, vector weight = 0):
          - stale_extracted:  staleness_score=0.8 → penalty_factor=0.2 → blended low;
                              provenance "extracted" adds +0.05
          - fresh_inferred:   staleness_score=0.0 → penalty_factor=1.0 → blended high;
                              provenance "inferred" adds 0.0

        Both results share the same cross-encoder logit (0.0 → sigmoid=0.5) and the
        same vector score (0.5) so provenance is the only non-staleness differentiator.
        """
        reranker = self._reranker()
        weights = RerankWeights(reranker=0.5, vector=0.0, staleness=0.5)

        stale_extracted = {
            "chunk_id": "stale-extracted",
            "score": 0.5,
            "content": "stale extracted doc",
            "metadata": {"source_provenance": "extracted"},
        }
        fresh_inferred = {
            "chunk_id": "fresh-inferred",
            "score": 0.5,
            "content": "fresh inferred doc",
            "metadata": {"source_provenance": "inferred"},
        }

        staleness_map = {
            "stale-extracted": 0.8,  # penalty_factor = 0.2
            "fresh-inferred": 0.0,  # penalty_factor = 1.0
        }

        reranker._apply_rerank_scores(
            [stale_extracted, fresh_inferred],
            scores=[0.0, 0.0],
            weights=weights,
            staleness_map=staleness_map,
        )

        assert stale_extracted["rerank_score"] < fresh_inferred["rerank_score"], (
            f"Expected stale-extracted ({stale_extracted['rerank_score']:.4f}) < "
            f"fresh-inferred ({fresh_inferred['rerank_score']:.4f})"
        )

    def test_stale_extracted_exact_scores(self):
        """Verify the exact combined score for a stale-extracted result.

        staleness_score=0.8 → penalty_factor=0.2
        weights: reranker=0.5, vector=0.0, staleness=0.5; total_weight=1.0
        logit=0.0 → normalized=0.5
        blended = (0.5*0.5 + 0.5*0.2) / 1.0 = 0.35
        rerank_score = clamp(0.35 + 0.05, 0, 1) = 0.40
        """
        reranker = self._reranker()
        weights = RerankWeights(reranker=0.5, vector=0.0, staleness=0.5)

        result = {
            "chunk_id": "doc-A",
            "score": 0.0,
            "content": "text",
            "metadata": {"source_provenance": "extracted"},
        }
        staleness_map = {"doc-A": 0.8}

        reranker._apply_rerank_scores([result], scores=[0.0], weights=weights, staleness_map=staleness_map)

        assert result["rerank_score"] == pytest.approx(0.40, abs=1e-6)

    def test_fresh_inferred_exact_scores(self):
        """Verify the exact combined score for a fresh-inferred result.

        staleness_score=0.0 → penalty_factor=1.0
        weights: reranker=0.5, vector=0.0, staleness=0.5; total_weight=1.0
        logit=0.0 → normalized=0.5
        blended = (0.5*0.5 + 0.5*1.0) / 1.0 = 0.75
        rerank_score = clamp(0.75 + 0.0, 0, 1) = 0.75
        """
        reranker = self._reranker()
        weights = RerankWeights(reranker=0.5, vector=0.0, staleness=0.5)

        result = {
            "chunk_id": "doc-B",
            "score": 0.0,
            "content": "text",
            "metadata": {"source_provenance": "inferred"},
        }
        staleness_map = {"doc-B": 0.0}

        reranker._apply_rerank_scores([result], scores=[0.0], weights=weights, staleness_map=staleness_map)

        assert result["rerank_score"] == pytest.approx(0.75, abs=1e-6)

    def test_sort_order_stale_extracted_below_fresh_inferred(self):
        """After _apply_rerank_scores the list is sorted: fresh-inferred must be first."""
        reranker = self._reranker()
        weights = RerankWeights(reranker=0.5, vector=0.0, staleness=0.5)

        stale_extracted = {
            "chunk_id": "stale-extracted",
            "score": 0.5,
            "content": "stale extracted doc",
            "metadata": {"source_provenance": "extracted"},
        }
        fresh_inferred = {
            "chunk_id": "fresh-inferred",
            "score": 0.5,
            "content": "fresh inferred doc",
            "metadata": {"source_provenance": "inferred"},
        }
        staleness_map = {"stale-extracted": 0.8, "fresh-inferred": 0.0}

        results = [stale_extracted, fresh_inferred]
        reranker._apply_rerank_scores(results, scores=[0.0, 0.0], weights=weights, staleness_map=staleness_map)

        assert results[0] is fresh_inferred, "fresh-inferred should be first (highest rerank_score) after sorting"
