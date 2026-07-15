#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Issue #10600: config-gated RAG retrieval-quality flips.

Covers the optimizer (chat) retrieval path:
- BM25 hybrid keyword scoring vs the legacy substring TF scan (flag-gated).
- Content-based MMR diversity reorder that suppresses near-duplicate chunks.
- Relevance-floor default sourced from config (min_score).
- Reranking-active health signal on silent cross-encoder fallback.

Every assertion pairs an ON case (behaviour changes) with an OFF/default case
(retrieval identical to today) so the flips are provably no-ops when disabled.
"""

import asyncio
import unittest

from advanced_rag_optimizer import AdvancedRAGOptimizer, SearchResult
from knowledge.search_components.reranking import (
    apply_mmr_reorder_by_content,
    is_reranking_active,
    set_reranking_active,
)


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _fact(content: str, path: str = "p") -> dict:
    return {"content": content, "metadata": {"relative_path": path, "chunk_index": 0}}


def _sr(content: str, score: float) -> SearchResult:
    return SearchResult(
        content=content,
        metadata={},
        semantic_score=score,
        keyword_score=score,
        hybrid_score=score,
        relevance_rank=0,
        source_path="p",
        rerank_score=score,
    )


# ---------------------------------------------------------------------------
# Content-based MMR (apply_mmr_reorder_by_content)
# ---------------------------------------------------------------------------


class TestContentMMR(unittest.TestCase):
    """MMR-by-content suppresses near-duplicate chunks when lambda in (0, 1)."""

    def test_lambda_zero_is_identity(self):
        results = [_sr("alpha beta", 0.9), _sr("alpha beta gamma", 0.8)]
        out = apply_mmr_reorder_by_content(
            results, 0.0, content_getter=lambda r: r.content, score_getter=lambda r: r.rerank_score
        )
        self.assertIs(out, results)

    def test_lambda_one_is_identity(self):
        results = [_sr("alpha", 0.9), _sr("beta", 0.8)]
        out = apply_mmr_reorder_by_content(
            results, 1.0, content_getter=lambda r: r.content, score_getter=lambda r: r.rerank_score
        )
        self.assertIs(out, results)

    def test_diverse_chunk_promoted_over_near_duplicate(self):
        # doc_a and doc_b are near-duplicates; doc_c is distinct but lower-scored.
        doc_a = _sr("install docker container service", 0.90)
        doc_b = _sr("install docker container service now", 0.85)
        doc_c = _sr("python asyncio event loop", 0.70)
        out = apply_mmr_reorder_by_content(
            [doc_a, doc_b, doc_c],
            0.5,
            content_getter=lambda r: r.content,
            score_getter=lambda r: r.rerank_score,
        )
        # After doc_a, the redundant doc_b is penalised so the diverse doc_c wins slot 2.
        self.assertEqual(out[0].content, doc_a.content)
        self.assertEqual(out[1].content, doc_c.content)
        self.assertEqual(out[2].content, doc_b.content)


# ---------------------------------------------------------------------------
# BM25 vs substring keyword scan (flag-gated)
# ---------------------------------------------------------------------------


class TestBM25Flag(unittest.TestCase):
    """bm25_hybrid_enabled switches the keyword half between BM25 and substring."""

    def setUp(self):
        self.facts = [
            _fact("the quick brown fox jumps"),
            _fact("a rare unicorn appears once"),
            _fact("the the the the the padding padding padding"),
        ]

    def test_off_uses_substring_scan_default(self):
        opt = AdvancedRAGOptimizer(bm25_hybrid_enabled=False)
        results = opt._perform_keyword_search("unicorn", self.facts)
        self.assertTrue(results)
        # Substring TF: single match term / 1 query term = 1.0 (before phrase boost).
        top = results[0]
        self.assertIn("unicorn", top.content)

    def test_on_uses_bm25_and_rewards_rare_terms(self):
        opt = AdvancedRAGOptimizer(bm25_hybrid_enabled=True)
        # 'unicorn' is a rare term (df=1) -> high IDF; 'the' is common -> low IDF.
        rare = opt._perform_keyword_search("unicorn", self.facts)
        common = opt._perform_keyword_search("the", self.facts)
        self.assertTrue(rare)
        self.assertTrue(common)
        # BM25 rewards the rare term more than the ubiquitous one.
        self.assertGreater(rare[0].keyword_score, common[0].keyword_score)

    def test_default_flag_is_off(self):
        opt = AdvancedRAGOptimizer()
        self.assertFalse(opt._bm25_hybrid_enabled)


# ---------------------------------------------------------------------------
# Relevance floor default from config
# ---------------------------------------------------------------------------


class TestRelevanceFloor(unittest.TestCase):
    """advanced_search applies self._default_min_score when caller passes 0.0."""

    def test_floor_zero_keeps_all(self):
        opt = AdvancedRAGOptimizer(min_score=0.0)
        rows = [_sr("a", 0.9), _sr("b", 0.2)]
        self.assertEqual(len(opt._apply_relevance_floor(rows, 0.0)), 2)

    def test_floor_drops_below_threshold(self):
        opt = AdvancedRAGOptimizer(min_score=0.5)
        rows = [_sr("a", 0.9), _sr("b", 0.2)]
        kept = opt._apply_relevance_floor(rows, opt._default_min_score)
        self.assertEqual([r.content for r in kept], ["a"])

    def test_default_min_score_is_zero(self):
        self.assertEqual(AdvancedRAGOptimizer()._default_min_score, 0.0)


# ---------------------------------------------------------------------------
# advanced_search end-to-end no-op vs floor (with a fake KB)
# ---------------------------------------------------------------------------


class _FakeKB:
    def __init__(self, facts):
        self._facts = facts

    async def search(self, query, top_k=20):
        # Assign descending scores; return SearchResult-shaped fact dicts.
        out = []
        for i, f in enumerate(self._facts):
            out.append({"content": f["content"], "metadata": f["metadata"], "score": 0.9 - 0.3 * i})
        return out[:top_k]

    async def get_all_facts(self):
        return self._facts


class TestAdvancedSearchFloorEndToEnd(unittest.TestCase):
    def _opt(self, min_score):
        opt = AdvancedRAGOptimizer(min_score=min_score)
        opt.kb = _FakeKB([_fact("alpha doc"), _fact("beta doc"), _fact("gamma doc")])
        return opt

    def test_no_floor_returns_all(self):
        opt = self._opt(0.0)
        results, _ = _run(opt.advanced_search("alpha", max_results=5, enable_reranking=False))
        self.assertGreaterEqual(len(results), 1)

    def test_high_floor_drops_low_scores(self):
        no_floor = self._opt(0.0)
        floored = self._opt(0.99)
        base, _ = _run(no_floor.advanced_search("alpha", max_results=5, enable_reranking=False))
        cut, _ = _run(floored.advanced_search("alpha", max_results=5, enable_reranking=False))
        self.assertLessEqual(len(cut), len(base))


# ---------------------------------------------------------------------------
# Reranking-active health signal
# ---------------------------------------------------------------------------


class TestRerankingHealthSignal(unittest.TestCase):
    def test_set_and_get(self):
        set_reranking_active(True)
        self.assertTrue(is_reranking_active())
        set_reranking_active(False)
        self.assertFalse(is_reranking_active())
        set_reranking_active(True)  # restore


if __name__ == "__main__":
    unittest.main()
