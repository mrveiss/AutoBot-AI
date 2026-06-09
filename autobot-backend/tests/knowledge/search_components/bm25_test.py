# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for BM25Scorer — Issue #1720.

Verifies IDF smoothing, length normalization, unknown-term handling,
and configurable k1/b parameters.
"""

import pytest

from knowledge.search_components.bm25 import BM25Scorer


class TestBM25Scorer:
    """Unit tests for BM25Scorer (#1720)."""

    def test_rare_terms_score_higher(self):
        """Rare terms (low df) must score higher than common terms for identical TF."""
        scorer = BM25Scorer(
            total_docs=100,
            avg_doc_length=50.0,
            doc_frequencies={"python": 10, "banana": 1},
        )
        score_rare = scorer.score(["banana"], "banana fruit", 2)
        score_common = scorer.score(["python"], "python lang", 2)
        assert (
            score_rare > score_common
        ), f"Expected rare term score {score_rare:.4f} > common term score {score_common:.4f}"

    def test_shorter_docs_score_higher(self):
        """Same TF in a shorter document must yield a higher score than in a longer one."""
        scorer = BM25Scorer(
            total_docs=100,
            avg_doc_length=50.0,
            doc_frequencies={"x": 10},
        )
        short_doc = "x y"
        long_doc = "x " + "w " * 100

        score_short = scorer.score(["x"], short_doc, 2)
        score_long = scorer.score(["x"], long_doc, 101)
        assert score_short > score_long, f"Expected short doc score {score_short:.4f} > long doc score {score_long:.4f}"

    def test_unknown_terms_smoothed(self):
        """Terms absent from doc_frequencies must still receive a positive BM25 score."""
        scorer = BM25Scorer(
            total_docs=100,
            avg_doc_length=50.0,
            doc_frequencies={},
        )
        score = scorer.score(["unknown"], "unknown term", 2)
        assert score > 0, f"Expected positive score for unknown term, got {score}"

    @pytest.mark.parametrize("k1,b", [(1.2, 0.75), (0.5, 0.3)])
    def test_configurable_parameters(self, k1, b):
        """Scorer must return a positive score for any valid k1/b combination."""
        scorer = BM25Scorer(
            total_docs=10,
            avg_doc_length=20.0,
            doc_frequencies={"t": 5},
            k1=k1,
            b=b,
        )
        score = scorer.score(["t"], "t doc", 2)
        assert score > 0, f"Expected positive score with k1={k1}, b={b}, got {score}"

    def test_no_matching_terms_returns_zero(self):
        """Query terms absent from document must yield a score of exactly 0."""
        scorer = BM25Scorer(
            total_docs=50,
            avg_doc_length=30.0,
            doc_frequencies={"redis": 5},
        )
        score = scorer.score(["redis"], "completely unrelated content", 3)
        assert score == 0.0, f"Expected 0 for no token match, got {score}"

    def test_idf_increases_as_df_decreases(self):
        """IDF value must increase as document frequency decreases."""
        scorer_common = BM25Scorer(100, 50.0, {"term": 80})
        scorer_rare = BM25Scorer(100, 50.0, {"term": 2})
        assert scorer_rare.idf("term") > scorer_common.idf("term"), (
            f"Expected rare idf {scorer_rare.idf('term'):.4f} " f"> common idf {scorer_common.idf('term'):.4f}"
        )
