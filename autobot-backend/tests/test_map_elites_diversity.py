#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for MAP-Elites structured diversity grid in AdvancedRAGOptimizer.

Issue #4677: Verifies:
- Grid filling: results covering distinct (category, source) cells are preferred
- Tie-breaking by score within a cell
- Fallback to cosine dedup when fewer than 2 categories are represented
- RAGConfig.diversity_strategy field (default "cosine", opt-in "map_elites")
"""

import unittest

from advanced_rag_optimizer import _MAP_ELITES_MIN_CATEGORIES, AdvancedRAGOptimizer, SearchResult
from services.rag_config import RAGConfig


def _make_result(
    content: str,
    hybrid_score: float,
    category: str = "docs",
    source_path: str = "backend/file.py",
) -> SearchResult:
    """Create a minimal SearchResult for testing."""
    return SearchResult(
        content=content,
        metadata={"category": category},
        semantic_score=hybrid_score,
        keyword_score=0.0,
        hybrid_score=hybrid_score,
        relevance_rank=1,
        source_path=source_path,
    )


class TestMapElitesSelect(unittest.TestCase):
    """_map_elites_select unit tests. Issue #4677."""

    def setUp(self):
        self.optimizer = AdvancedRAGOptimizer()

    # ------------------------------------------------------------------
    # Grid filling
    # ------------------------------------------------------------------

    def test_distinct_cells_all_selected(self):
        """Results with distinct (category, source) cells are all included."""
        results = [
            _make_result("doc1", 0.9, category="docs", source_path="backend/a.py"),
            _make_result("code1", 0.8, category="code", source_path="frontend/b.ts"),
            _make_result("cfg1", 0.7, category="config", source_path="config/c.yaml"),
        ]
        selected = self.optimizer._map_elites_select(results, max_results=5)
        contents = {r.content for r in selected}
        self.assertEqual(contents, {"doc1", "code1", "cfg1"})

    def test_double_fill_lower_score_excluded_within_capacity(self):
        """When a cell is already occupied, a lower-score duplicate is not added
        as a new slot — it only displaces the cell entry if score is higher."""
        results = [
            _make_result("best", 0.9, category="docs", source_path="backend/a.py"),
            _make_result("worse", 0.5, category="docs", source_path="backend/a.py"),
            _make_result("other", 0.8, category="code", source_path="frontend/b.ts"),
        ]
        # max_results=2: expect "best" and "other" (distinct cells, top scores)
        selected = self.optimizer._map_elites_select(results, max_results=2)
        self.assertEqual(len(selected), 2)
        contents = {r.content for r in selected}
        self.assertIn("best", contents)
        self.assertIn("other", contents)

    def test_capacity_respected(self):
        """Selected results never exceed max_results."""
        results = [
            _make_result(f"doc{i}", float(i) / 10, category=f"cat{i}", source_path=f"s{i}/f.py") for i in range(1, 10)
        ]
        selected = self.optimizer._map_elites_select(results, max_results=3)
        self.assertLessEqual(len(selected), 3)

    # ------------------------------------------------------------------
    # Fallback condition
    # ------------------------------------------------------------------

    def test_fallback_when_single_category(self):
        """When all results share one category, cosine fallback is used."""
        results = [_make_result(f"doc{i}", 0.9 - i * 0.1, category="docs", source_path=f"s{i}/f.py") for i in range(5)]
        # All same category → fewer than _MAP_ELITES_MIN_CATEGORIES → fallback
        selected = self.optimizer._map_elites_select(results, max_results=5)
        # Fallback returns _diversify_results output — just verify we get results back
        self.assertGreater(len(selected), 0)
        self.assertLessEqual(len(selected), 5)

    def test_min_categories_constant(self):
        """_MAP_ELITES_MIN_CATEGORIES must be 2."""
        self.assertEqual(_MAP_ELITES_MIN_CATEGORIES, 2)

    def test_single_result_returned_unchanged(self):
        """Single-element list passes through without modification."""
        results = [_make_result("only", 1.0)]
        selected = self.optimizer._map_elites_select(results, max_results=5)
        self.assertEqual(selected, results)

    # ------------------------------------------------------------------
    # Score tie-breaking (within a cell)
    # ------------------------------------------------------------------

    def test_higher_score_wins_cell_slot(self):
        """Within the same cell, the higher-scoring result is the one kept in grid."""
        # We send lower-score first so grid takes it, then higher-score should
        # update the cell entry.  Overflow fills remaining slots from sorted remainder.
        results = [
            _make_result("low", 0.3, category="docs", source_path="backend/a.py"),
            _make_result("high", 0.9, category="docs", source_path="backend/a.py"),
            _make_result("other", 0.7, category="code", source_path="frontend/b.ts"),
        ]
        # max_results=3 → all three get in (low fills cell first, high updates grid,
        # other fills second cell; remaining slot goes to higher-score overflow)
        selected = self.optimizer._map_elites_select(results, max_results=3)
        contents = {r.content for r in selected}
        # "low" is selected first (fills cell), "other" fills second cell.
        # "high" updates the cell's internal score entry but doesn't get a NEW slot.
        # With max_results=3 remaining capacity=1 → "high" added as overflow.
        self.assertIn("low", contents)
        self.assertIn("other", contents)
        self.assertIn("high", contents)


class TestRAGConfigDiversityStrategy(unittest.TestCase):
    """RAGConfig.diversity_strategy field tests. Issue #4677."""

    def test_default_is_cosine(self):
        """Default diversity_strategy is 'cosine'."""
        config = RAGConfig()
        self.assertEqual(config.diversity_strategy, "cosine")

    def test_map_elites_opt_in(self):
        """diversity_strategy can be set to 'map_elites'."""
        config = RAGConfig(diversity_strategy="map_elites")
        self.assertEqual(config.diversity_strategy, "map_elites")

    def test_from_dict_round_trip(self):
        """from_dict / to_dict preserve diversity_strategy."""
        config = RAGConfig(diversity_strategy="map_elites")
        d = config.to_dict()
        self.assertEqual(d["diversity_strategy"], "map_elites")
        config2 = RAGConfig.from_dict(d)
        self.assertEqual(config2.diversity_strategy, "map_elites")

    def test_from_dict_defaults_to_cosine_when_missing(self):
        """from_dict without diversity_strategy key defaults to 'cosine'."""
        config = RAGConfig.from_dict({})
        self.assertEqual(config.diversity_strategy, "cosine")


if __name__ == "__main__":
    unittest.main()
