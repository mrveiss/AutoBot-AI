# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for staleness-aware reranking integration (#2547).

Covers:
- _apply_rerank_scores() with staleness_map applies the penalty
- _apply_rerank_scores() without staleness_map (weight=0) is backward-compatible
- _fetch_staleness_map() returns None when staleness weight is 0
- rerank() integrates the staleness lookup correctly (mocked Redis)
"""

import math
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from knowledge.search_components.reranking import (
    RerankWeights,
    ResultReranker,
    compute_blended_score,
    staleness_penalty,
)

# =============================================================================
# Helpers
# =============================================================================


def _make_result(chunk_id: str, score: float = 0.5, content: str = "text") -> dict:
    return {"chunk_id": chunk_id, "score": score, "content": content}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


# =============================================================================
# staleness_penalty()
# =============================================================================


class TestStalenessPenalty:
    """staleness_penalty() converts raw staleness score to a 0-1 factor."""

    def test_fresh_document_no_penalty(self):
        assert staleness_penalty(0.0) == 1.0

    def test_fully_stale_document_max_penalty(self):
        assert staleness_penalty(1.0) == 0.0

    def test_midpoint(self):
        assert staleness_penalty(0.5) == pytest.approx(0.5)

    def test_clamped_at_zero(self):
        """Scores above 1.0 are clamped to 0 penalty."""
        assert staleness_penalty(2.0) == 0.0


# =============================================================================
# _apply_rerank_scores() staleness path
# =============================================================================


class TestApplyRerankScoresStaleness:
    """_apply_rerank_scores applies staleness penalty when weight > 0."""

    def _score_with_map(self, staleness_score: float, staleness_weight: float = 0.5) -> float:
        """Return rerank_score for a single result with the given staleness."""
        reranker = ResultReranker()
        result = _make_result("doc-A", score=0.6)
        raw_logit = 2.0
        weights = RerankWeights(reranker=0.5, vector=0.0, staleness=staleness_weight)
        staleness_map = {"doc-A": staleness_score}

        reranker._apply_rerank_scores([result], [raw_logit], weights=weights, staleness_map=staleness_map)
        return result["rerank_score"]

    def test_fresh_doc_gets_full_penalty_factor(self):
        """staleness=0.0 → penalty factor 1.0 → higher score than stale doc."""
        fresh_score = self._score_with_map(0.0)
        stale_score = self._score_with_map(1.0)
        assert fresh_score > stale_score

    def test_fully_stale_doc_reduces_score(self):
        """staleness=1.0 applies maximum penalty (penalty factor 0.0)."""
        reranker = ResultReranker()
        result = _make_result("doc-A", score=0.6)
        raw_logit = 2.0
        weights = RerankWeights(reranker=0.5, vector=0.0, staleness=0.5)
        staleness_map = {"doc-A": 1.0}

        reranker._apply_rerank_scores([result], [raw_logit], weights=weights, staleness_map=staleness_map)

        normalized = _sigmoid(raw_logit)
        # penalty factor = staleness_penalty(1.0) = 0.0
        expected = compute_blended_score(
            reranker_score=normalized,
            vector_score=0.6,
            staleness_penalty_value=0.0,
            weights=weights,
        )
        assert result["rerank_score"] == pytest.approx(expected)

    def test_missing_chunk_id_treated_as_fresh(self):
        """A result with no chunk_id in the map is treated as staleness 0."""
        reranker = ResultReranker()
        result = _make_result("unknown-id", score=0.5)
        raw_logit = 1.0
        weights = RerankWeights(reranker=0.5, vector=0.5, staleness=0.3)
        staleness_map = {}  # empty — no entry for unknown-id

        reranker._apply_rerank_scores([result], [raw_logit], weights=weights, staleness_map=staleness_map)

        # Default staleness=0 → penalty factor=1.0
        normalized = _sigmoid(raw_logit)
        expected = compute_blended_score(
            reranker_score=normalized,
            vector_score=0.5,
            staleness_penalty_value=1.0,
            weights=weights,
        )
        assert result["rerank_score"] == pytest.approx(expected)

    def test_staleness_weight_zero_skips_lookup(self):
        """When staleness weight is 0, staleness_map=None is safe (no key error)."""
        reranker = ResultReranker()
        result = _make_result("doc-A", score=0.5)
        raw_logit = 1.0
        weights = RerankWeights(reranker=0.8, vector=0.2, staleness=0.0)

        # No staleness_map — should not raise
        reranker._apply_rerank_scores([result], [raw_logit], weights=weights, staleness_map=None)

        assert "rerank_score" in result

    def test_results_sorted_by_rerank_score_descending(self):
        """Fresh document (lower staleness) should rank above stale one."""
        reranker = ResultReranker()
        fresh = _make_result("fresh", score=0.5)
        stale = _make_result("stale", score=0.5)
        raw_logits = [2.0, 2.0]  # equal cross-encoder scores
        weights = RerankWeights(reranker=0.5, vector=0.0, staleness=0.5)
        staleness_map = {"fresh": 0.0, "stale": 0.9}

        results = [stale, fresh]
        reranker._apply_rerank_scores(results, raw_logits, weights=weights, staleness_map=staleness_map)

        # fresh should be first after sorting
        assert results[0]["chunk_id"] == "fresh"
        assert results[1]["chunk_id"] == "stale"


# =============================================================================
# _fetch_staleness_map()
# =============================================================================


class TestFetchStalenessMap:
    """_fetch_staleness_map returns None when staleness is disabled."""

    @pytest.mark.asyncio
    async def test_returns_none_when_weight_zero(self):
        """No Redis calls when staleness weight is 0."""
        reranker = ResultReranker()
        results = [_make_result("doc-A")]
        weights = RerankWeights(staleness=0.0)

        result = await reranker._fetch_staleness_map(results, weights)

        assert result is None

    @pytest.mark.asyncio
    async def test_returns_scores_when_weight_nonzero(self):
        """Staleness scores are fetched from Redis when weight > 0."""
        reranker = ResultReranker()
        results = [_make_result("doc-A"), _make_result("doc-B")]
        weights = RerankWeights(staleness=0.3)

        mock_redis = AsyncMock()

        # Patch at the source modules because _fetch_staleness_map uses lazy imports
        with (
            patch("autobot_shared.redis_client.get_redis_client", return_value=mock_redis),
            patch(
                "services.mesh_brain.staleness_propagator.get_staleness_score",
                new=AsyncMock(side_effect=lambda r, doc_id: 0.7 if doc_id == "doc-A" else 0.0),
            ),
        ):
            staleness_map = await reranker._fetch_staleness_map(results, weights)

        assert staleness_map is not None
        assert staleness_map["doc-A"] == pytest.approx(0.7)
        assert staleness_map["doc-B"] == pytest.approx(0.0)

    @pytest.mark.asyncio
    async def test_returns_none_on_redis_error(self):
        """Redis failures degrade gracefully — returns None instead of raising."""
        reranker = ResultReranker()
        results = [_make_result("doc-A")]
        weights = RerankWeights(staleness=0.3)

        with patch(
            "autobot_shared.redis_client.get_redis_client",
            side_effect=RuntimeError("Redis unavailable"),
        ):
            staleness_map = await reranker._fetch_staleness_map(results, weights)

        assert staleness_map is None

    @pytest.mark.asyncio
    async def test_deduplicates_chunk_ids(self):
        """Duplicate chunk_ids trigger only one Redis lookup each."""
        reranker = ResultReranker()
        results = [_make_result("doc-A"), _make_result("doc-A")]  # duplicate
        weights = RerankWeights(staleness=0.3)

        call_count = 0

        async def _fake_get_staleness(redis, doc_id):
            nonlocal call_count
            call_count += 1
            return 0.5

        mock_redis = MagicMock()

        with (
            patch("autobot_shared.redis_client.get_redis_client", return_value=mock_redis),
            patch(
                "services.mesh_brain.staleness_propagator.get_staleness_score",
                side_effect=_fake_get_staleness,
            ),
        ):
            await reranker._fetch_staleness_map(results, weights)

        assert call_count == 1  # deduplication ensures only one lookup
