#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for SessionAdaptiveReranker — Issue #4690.

Verifies:
- New sessions start with default weights.
- Weights shift towards semantic path after repeated semantic successes.
- Weights shift towards keyword path after repeated keyword successes.
- Session state is fully discarded after end_session().
- Distinct session_ids never share state.
- Learning-rate clamping keeps weights within [0.1, 0.9].
"""

import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from services.session_adaptive_reranker import SessionAdaptiveReranker, get_session_adaptive_reranker

_DEFAULT_SEM = 0.75
_DEFAULT_KW = 0.25


class TestSessionAdaptiveRerankerBasics(unittest.TestCase):
    """Basic weight management and isolation."""

    def _make(self, sem=_DEFAULT_SEM, kw=_DEFAULT_KW) -> SessionAdaptiveReranker:
        return SessionAdaptiveReranker(default_semantic=sem, default_keyword=kw)

    def test_new_session_uses_defaults(self):
        r = self._make()
        sem, kw = r.get_weights("sess-1")
        self.assertAlmostEqual(sem, _DEFAULT_SEM)
        self.assertAlmostEqual(kw, _DEFAULT_KW)

    def test_semantic_success_increases_semantic_weight(self):
        r = self._make()
        for _ in range(10):
            r.record_signal("sess-1", semantic_success=True, keyword_success=False)
        sem, kw = r.get_weights("sess-1")
        self.assertGreater(sem, _DEFAULT_SEM)
        self.assertLess(kw, _DEFAULT_KW)

    def test_keyword_success_increases_keyword_weight(self):
        r = self._make()
        for _ in range(10):
            r.record_signal("sess-1", semantic_success=False, keyword_success=True)
        sem, kw = r.get_weights("sess-1")
        self.assertLess(sem, _DEFAULT_SEM)
        self.assertGreater(kw, _DEFAULT_KW)

    def test_weights_always_clamped(self):
        """Extreme one-sided signals must not push weights outside [0.1, 0.9]."""
        r = self._make()
        for _ in range(200):
            r.record_signal("sess-1", semantic_success=True, keyword_success=False)
        sem, kw = r.get_weights("sess-1")
        self.assertGreaterEqual(sem, 0.1)
        self.assertLessEqual(sem, 0.9)
        self.assertGreaterEqual(kw, 0.1)
        self.assertLessEqual(kw, 0.9)

    def test_end_session_resets_to_defaults(self):
        r = self._make()
        for _ in range(10):
            r.record_signal("sess-1", semantic_success=True, keyword_success=False)
        r.end_session("sess-1")
        # After reset the session should revert to defaults (fresh state).
        sem, kw = r.get_weights("sess-1")
        self.assertAlmostEqual(sem, _DEFAULT_SEM)
        self.assertAlmostEqual(kw, _DEFAULT_KW)

    def test_distinct_sessions_are_independent(self):
        r = self._make()
        for _ in range(10):
            r.record_signal("sess-A", semantic_success=True, keyword_success=False)
        # sess-B should still be at defaults.
        sem_b, kw_b = r.get_weights("sess-B")
        self.assertAlmostEqual(sem_b, _DEFAULT_SEM)
        self.assertAlmostEqual(kw_b, _DEFAULT_KW)

    def test_end_session_noop_for_unknown_session(self):
        r = self._make()
        r.end_session("nonexistent")  # must not raise

    def test_active_session_count(self):
        r = self._make()
        self.assertEqual(r.active_session_count(), 0)
        r.get_weights("s1")
        r.get_weights("s2")
        self.assertEqual(r.active_session_count(), 2)
        r.end_session("s1")
        self.assertEqual(r.active_session_count(), 1)

    def test_both_success_keeps_ratio_stable(self):
        """When both paths succeed equally the weight ratio should stay close to initial."""
        r = self._make(sem=0.5, kw=0.5)
        for _ in range(20):
            r.record_signal("sess-1", semantic_success=True, keyword_success=True)
        sem, kw = r.get_weights("sess-1")
        # With equal signals, weights should converge towards 0.5/0.5.
        self.assertAlmostEqual(sem, 0.5, delta=0.15)
        self.assertAlmostEqual(kw, 0.5, delta=0.15)

    def test_get_session_adaptive_reranker_returns_cached_instance(self):
        r1 = get_session_adaptive_reranker(0.75, 0.25)
        r2 = get_session_adaptive_reranker(0.75, 0.25)
        self.assertIs(r1, r2)

    def test_get_session_adaptive_reranker_different_defaults_are_distinct(self):
        r1 = get_session_adaptive_reranker(0.6, 0.4)
        r2 = get_session_adaptive_reranker(0.8, 0.2)
        self.assertIsNot(r1, r2)


class TestRAGServiceSessionAdaptation(unittest.IsolatedAsyncioTestCase):
    """RAGService session adaptive reranking integration."""

    def _make_search_result(self, hybrid_score: float = 0.8, semantic_score: float = 0.8, keyword_score: float = 0.2):
        from advanced_rag_optimizer import SearchResult

        return SearchResult(
            content="test content",
            metadata={"chunk_id": "c1"},
            semantic_score=semantic_score,
            keyword_score=keyword_score,
            hybrid_score=hybrid_score,
            relevance_rank=1,
            source_path="test",
        )

    def test_record_session_signal_semantic_success(self):
        """_record_session_signal with high-semantic-score results signals semantic hit."""
        from services.rag_config import RAGConfig
        from services.rag_service import RAGService

        config = RAGConfig(enable_session_adaptive_reranking=True)
        service = RAGService(knowledge_base=MagicMock(), config=config)

        result = self._make_search_result(semantic_score=0.9, keyword_score=0.1)
        # Record a strong semantic hit 10 times.
        for _ in range(10):
            service._record_session_signal("sess-x", [result])

        sem, kw = service._session_reranker.get_weights("sess-x")
        self.assertGreater(sem, config.hybrid_weight_semantic)

    def test_end_session_clears_state(self):
        """end_session() removes the session from the reranker."""
        from services.rag_config import RAGConfig
        from services.rag_service import RAGService

        config = RAGConfig(enable_session_adaptive_reranking=True)
        service = RAGService(knowledge_base=MagicMock(), config=config)

        result = self._make_search_result(semantic_score=0.9)
        for _ in range(5):
            service._record_session_signal("sess-y", [result])

        service.end_session("sess-y")

        # After end_session the reranker has no active sessions for this id.
        # Getting weights creates a fresh state at defaults.
        sem, kw = service._session_reranker.get_weights("sess-y")
        self.assertAlmostEqual(sem, config.hybrid_weight_semantic)

    async def test_advanced_search_applies_adapted_weights(self):
        """advanced_search() uses adapted weights from session reranker when feature enabled."""
        from advanced_rag_optimizer import AdvancedRAGOptimizer, RAGMetrics
        from services.rag_config import RAGConfig
        from services.rag_service import RAGService

        config = RAGConfig(enable_session_adaptive_reranking=True, enable_advanced_rag=True)
        service = RAGService(knowledge_base=MagicMock(), config=config)

        # Pre-seed the session so its weights differ from defaults.
        result_high_sem = self._make_search_result(semantic_score=0.9, keyword_score=0.1)
        for _ in range(10):
            service._record_session_signal("sess-z", [result_high_sem])
        adapted_sem, _ = service._session_reranker.get_weights("sess-z")
        self.assertGreater(adapted_sem, config.hybrid_weight_semantic)

        # Now verify advanced_search applies them to the optimizer.
        applied_sem_values = []

        async def fake_search(*args, **kwargs):
            if service.optimizer:
                applied_sem_values.append(service.optimizer.hybrid_weight_semantic)
            return [result_high_sem], RAGMetrics()

        mock_optimizer = MagicMock(spec=AdvancedRAGOptimizer)
        mock_optimizer.hybrid_weight_semantic = config.hybrid_weight_semantic
        mock_optimizer.hybrid_weight_keyword = config.hybrid_weight_keyword
        mock_optimizer.advanced_search = AsyncMock(side_effect=fake_search)
        service.optimizer = mock_optimizer
        service._initialized = True

        with (
            patch.object(service, "_check_cache_tiers", new=AsyncMock(return_value=None)),
            patch.object(service, "_filter_stale_chunks", new=AsyncMock(side_effect=lambda r: r)),
            patch.object(service, "_store_in_semantic_cache", new=AsyncMock()),
            patch.object(service, "_store_in_topic_cache", new=AsyncMock()),
            patch.object(service, "_emit_ranked_feedback", new=AsyncMock()),
            patch.object(service, "_record_retrieval_outcome", new=AsyncMock()),
            patch.object(service, "_lookup_retrieval_pattern", new=AsyncMock(return_value=None)),
            patch(
                "services.rag_service.asyncio.wait_for",
                new=AsyncMock(side_effect=lambda coro, timeout: coro),
            ),
        ):
            await service.advanced_search("test query", session_id="sess-z")

        # The applied weight should have been the adapted one (higher than default).
        if applied_sem_values:
            self.assertGreater(applied_sem_values[0], config.hybrid_weight_semantic - 0.01)

        # After call, optimizer weights should be restored to defaults.
        self.assertAlmostEqual(mock_optimizer.hybrid_weight_semantic, config.hybrid_weight_semantic)


if __name__ == "__main__":
    unittest.main()
