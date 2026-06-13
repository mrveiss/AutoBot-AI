# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Tests for autobot_memory_graph.semantic_search (#3612).

Covers:
- HybridScorer.bm25_score
- HybridScorer.cosine_similarity
- HybridScorer.combined_score
- MemoryGraphQueryProcessor._extract_intent (entity type → UPPERCASE)
- MemoryGraphQueryProcessor._build_redis_query
- MemoryGraphQueryProcessor._extract_keywords
- MemoryGraphQueryProcessor._entity_to_terms
- MemoryGraphQueryProcessor._score_and_rank
- MemoryGraphQueryProcessor.process_query (mocked Redis + embeddings)
"""

from __future__ import annotations

import math
import sys
import types
from datetime import datetime, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Bootstrap stub modules so the package can be imported without the full
# AutoBot runtime (no autobot_shared, no Redis, etc.)
# ---------------------------------------------------------------------------


def _bootstrap_stubs() -> None:
    """Create minimal stubs for autobot_shared imports."""
    # autobot_shared
    autobot_shared = types.ModuleType("autobot_shared")
    sys.modules.setdefault("autobot_shared", autobot_shared)

    # autobot_shared.ssot_config
    ssot_config_mod = types.ModuleType("autobot_shared.ssot_config")

    class _Config:
        def get(self, key: str, default: Any = None) -> Any:
            return default

        @property
        def vm(self):
            class _VM:
                redis = "127.0.0.1"

            return _VM()

    ssot_config_mod.config = _Config()
    sys.modules.setdefault("autobot_shared.ssot_config", ssot_config_mod)
    autobot_shared.ssot_config = ssot_config_mod  # type: ignore[attr-defined]

    # autobot_shared.redis_client
    redis_client_mod = types.ModuleType("autobot_shared.redis_client")
    redis_client_mod.get_redis_client = MagicMock(return_value=MagicMock())  # type: ignore[attr-defined]
    sys.modules.setdefault("autobot_shared.redis_client", redis_client_mod)

    # autobot_shared.redis_management.types
    rm = types.ModuleType("autobot_shared.redis_management")
    sys.modules.setdefault("autobot_shared.redis_management", rm)
    rm_types = types.ModuleType("autobot_shared.redis_management.types")
    rm_types.DATABASE_MAPPING = {"knowledge": 2}  # type: ignore[attr-defined]
    sys.modules.setdefault("autobot_shared.redis_management.types", rm_types)


_bootstrap_stubs()

# Now we can import the module under test
from autobot_memory_graph.semantic_search import (  # noqa: E402
    HybridScorer,
    MemoryGraphQueryProcessor,
    QueryIntent,
    SearchResult,
    ensure_indexes,
)

# ===========================================================================
# HybridScorer tests
# ===========================================================================


class TestHybridScorerBM25:
    """Tests for HybridScorer.bm25_score."""

    def setup_method(self) -> None:
        self.scorer = HybridScorer()

    def test_bm25_empty_query_returns_zero(self) -> None:
        score = self.scorer.bm25_score([], ["redis", "bug", "fix"])
        assert score == 0.0

    def test_bm25_empty_document_returns_zero(self) -> None:
        score = self.scorer.bm25_score(["bug"], [])
        assert score == 0.0

    def test_bm25_perfect_overlap_positive(self) -> None:
        score = self.scorer.bm25_score(["bug", "fix"], ["bug", "fix", "redis"])
        assert score > 0.0

    def test_bm25_no_overlap_returns_zero(self) -> None:
        score = self.scorer.bm25_score(["python"], ["redis", "graph"])
        assert score == 0.0

    def test_bm25_match_beats_no_match(self) -> None:
        # A document that contains the query term must score higher than one
        # that does not contain it at all.
        score_match = self.scorer.bm25_score(["bug"], ["bug", "task", "feature"])
        score_no_match = self.scorer.bm25_score(["bug"], ["redis", "graph"])
        assert score_match > score_no_match

    def test_bm25_partial_overlap(self) -> None:
        score = self.scorer.bm25_score(["bug", "fix"], ["bug", "feature"])
        # Only "bug" matches; score should be positive but less than full match
        full = self.scorer.bm25_score(["bug", "fix"], ["bug", "fix"])
        assert 0.0 < score <= full

    def test_bm25_returns_float(self) -> None:
        score = self.scorer.bm25_score(["redis"], ["redis"])
        assert isinstance(score, float)


class TestHybridScorerCosine:
    """Tests for HybridScorer.cosine_similarity."""

    def setup_method(self) -> None:
        self.scorer = HybridScorer()

    def test_cosine_identical_vectors_is_one(self) -> None:
        v = [1.0, 0.0, 0.5]
        assert math.isclose(self.scorer.cosine_similarity(v, v), 1.0, rel_tol=1e-6)

    def test_cosine_orthogonal_vectors_is_zero(self) -> None:
        assert self.scorer.cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_cosine_empty_vectors_returns_zero(self) -> None:
        assert self.scorer.cosine_similarity([], [1.0]) == 0.0
        assert self.scorer.cosine_similarity([1.0], []) == 0.0

    def test_cosine_mismatched_length_returns_zero(self) -> None:
        assert self.scorer.cosine_similarity([1.0, 0.0], [1.0]) == 0.0

    def test_combined_score_weights(self) -> None:
        score = self.scorer.combined_score(semantic_score=1.0, keyword_score=1.0)
        assert math.isclose(score, 1.0, rel_tol=1e-6)

    def test_combined_score_zero_inputs(self) -> None:
        assert self.scorer.combined_score(0.0, 0.0) == 0.0


# ===========================================================================
# MemoryGraphQueryProcessor._extract_intent tests
# ===========================================================================


class TestExtractIntent:
    """Tests for intent extraction — entity types must be UPPERCASE."""

    def setup_method(self) -> None:
        redis_mock = MagicMock()
        self.proc = MemoryGraphQueryProcessor(redis_client=redis_mock)

    def test_bug_query_maps_to_BUG(self) -> None:
        intent = self.proc._extract_intent("What bugs did we fix today?")
        assert "BUG" in intent.entity_types

    def test_fix_query_maps_to_BUG(self) -> None:
        intent = self.proc._extract_intent("show me all fixes from this week")
        assert "BUG" in intent.entity_types

    def test_feature_query_maps_to_FEATURE(self) -> None:
        intent = self.proc._extract_intent("list recent features")
        assert "FEATURE" in intent.entity_types

    def test_task_query_maps_to_TASK(self) -> None:
        intent = self.proc._extract_intent("what tasks are pending?")
        assert "TASK" in intent.entity_types

    def test_decision_query_maps_to_DECISION(self) -> None:
        intent = self.proc._extract_intent("show architecture decisions")
        assert "DECISION" in intent.entity_types

    def test_no_entity_type_query(self) -> None:
        intent = self.proc._extract_intent("tell me about redis performance")
        assert intent.entity_types == []

    def test_entity_types_are_uppercase(self) -> None:
        intent = self.proc._extract_intent("bugs and features and tasks")
        for t in intent.entity_types:
            assert t == t.upper(), f"Expected uppercase, got: {t!r}"

    def test_time_today_extracted(self) -> None:
        intent = self.proc._extract_intent("bugs fixed today")
        assert intent.time_range is not None
        assert "start" in intent.time_range

    def test_time_last_7_days(self) -> None:
        intent = self.proc._extract_intent("issues from last 7 days")
        assert intent.time_range is not None
        expected_start = datetime.now(tz=timezone.utc).date() - __import__("datetime").timedelta(days=7)
        assert intent.time_range["start"] == expected_start

    def test_status_completed_extracted(self) -> None:
        intent = self.proc._extract_intent("show completed tasks")
        assert intent.status_filter is not None
        assert "completed" in intent.status_filter

    def test_keywords_extracted(self) -> None:
        intent = self.proc._extract_intent("Redis memory graph optimisation")
        assert "redis" in intent.keywords
        assert "memory" in intent.keywords

    def test_stop_words_excluded(self) -> None:
        intent = self.proc._extract_intent("what are the bugs")
        assert "what" not in intent.keywords
        assert "are" not in intent.keywords
        assert "the" not in intent.keywords


# ===========================================================================
# MemoryGraphQueryProcessor._build_redis_query
# ===========================================================================


class TestBuildRedisQuery:
    def setup_method(self) -> None:
        redis_mock = MagicMock()
        self.proc = MemoryGraphQueryProcessor(redis_client=redis_mock)

    def test_empty_intent_returns_wildcard(self) -> None:
        intent = QueryIntent()
        assert self.proc._build_redis_query(intent) == "*"

    def test_single_entity_type_tag(self) -> None:
        intent = QueryIntent(entity_types=["BUG"])
        q = self.proc._build_redis_query(intent)
        assert "@type:{BUG}" in q

    def test_multiple_entity_types_joined(self) -> None:
        intent = QueryIntent(entity_types=["BUG", "FEATURE"])
        q = self.proc._build_redis_query(intent)
        assert "BUG|FEATURE" in q or "FEATURE|BUG" in q

    def test_status_filter_in_query(self) -> None:
        intent = QueryIntent(status_filter=["completed"])
        q = self.proc._build_redis_query(intent)
        assert "@status:{completed}" in q

    def test_keywords_in_query(self) -> None:
        intent = QueryIntent(keywords=["redis", "graph"])
        q = self.proc._build_redis_query(intent)
        assert "redis" in q and "graph" in q


# ===========================================================================
# MemoryGraphQueryProcessor.process_query (mocked)
# ===========================================================================


class TestProcessQuery:
    """Integration-style tests with mocked Redis and embedding service."""

    def _make_entity(self, name: str, etype: str) -> Dict[str, Any]:
        return {
            "id": "test-uuid",
            "name": name,
            "type": etype,
            "observations": [f"{name} observation about redis graph"],
            "metadata": {"status": "active", "priority": "medium"},
        }

    def _make_processor_with_candidates(self, candidates: List[Dict[str, Any]]) -> MemoryGraphQueryProcessor:
        redis_mock = AsyncMock()
        # FT.SEARCH returns empty raw to trigger scan fallback
        redis_mock.execute_command = AsyncMock(side_effect=Exception("no index"))
        # scan_iter yields no keys to keep test simple

        async def _scan_iter(**kwargs):
            return
            yield  # pragma: no cover

        redis_mock.scan_iter = _scan_iter

        proc = MemoryGraphQueryProcessor(redis_client=redis_mock)

        # Patch _scan_fallback to return our test candidates
        async def _fake_fallback(limit: int) -> List[Dict[str, Any]]:
            return candidates[:limit]

        proc._scan_fallback = _fake_fallback  # type: ignore[method-assign]

        # Patch _generate_embedding to return a dummy vector
        async def _fake_embed(text: str) -> List[float]:
            return [0.1] * 10

        proc._generate_embedding = _fake_embed  # type: ignore[method-assign]

        return proc

    @pytest.mark.asyncio
    async def test_process_query_empty_string_returns_empty(self) -> None:
        redis_mock = MagicMock()
        proc = MemoryGraphQueryProcessor(redis_client=redis_mock)
        result = await proc.process_query("")
        assert result == []

    @pytest.mark.asyncio
    async def test_process_query_returns_search_results(self) -> None:
        entities = [
            self._make_entity("Redis Bug Fix", "BUG"),
            self._make_entity("New Feature", "FEATURE"),
        ]
        proc = self._make_processor_with_candidates(entities)
        results = await proc.process_query("redis bug")
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, SearchResult)

    @pytest.mark.asyncio
    async def test_process_query_limit_respected(self) -> None:
        entities = [self._make_entity(f"Entity {i}", "TASK") for i in range(20)]
        proc = self._make_processor_with_candidates(entities)
        results = await proc.process_query("task", limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_search_result_has_required_fields(self) -> None:
        entities = [self._make_entity("Test Bug", "BUG")]
        proc = self._make_processor_with_candidates(entities)
        results = await proc.process_query("test bug")
        if results:
            r = results[0]
            assert hasattr(r, "entity")
            assert hasattr(r, "score")
            assert hasattr(r, "semantic_score")
            assert hasattr(r, "keyword_score")
            assert hasattr(r, "matched_keywords")
            assert hasattr(r, "explanation")

    def test_score_and_rank_higher_match_ranked_first(self) -> None:
        redis_mock = MagicMock()
        proc = MemoryGraphQueryProcessor(redis_client=redis_mock)
        intent = QueryIntent(keywords=["redis", "bug"])
        entities = [
            {"name": "Unrelated Entity", "type": "TASK", "observations": []},
            {"name": "Redis Bug Fix", "type": "BUG", "observations": ["redis bug"]},
        ]
        results = proc._score_and_rank(entities, [], intent, 10)
        # Redis Bug Fix should score higher due to keyword match
        assert results[0].entity["name"] == "Redis Bug Fix"


# ===========================================================================
# ensure_indexes (smoke test with mock)
# ===========================================================================


class TestEnsureIndexes:
    @pytest.mark.asyncio
    async def test_ensure_indexes_calls_ft_create(self) -> None:
        redis_mock = AsyncMock()
        # First call to FT.INFO raises (index doesn't exist) → triggers FT.CREATE
        redis_mock.execute_command = AsyncMock(side_effect=Exception("not found"))

        await ensure_indexes(redis_mock)

        # Should have been called for both FT.INFO and FT.CREATE per index
        assert redis_mock.execute_command.call_count >= 2

    @pytest.mark.asyncio
    async def test_ensure_indexes_skips_existing(self) -> None:
        redis_mock = AsyncMock()
        # FT.INFO succeeds → index exists → FT.CREATE should NOT be called
        redis_mock.execute_command = AsyncMock(return_value=["some", "info"])

        await ensure_indexes(redis_mock)

        calls = [str(c) for c in redis_mock.execute_command.call_args_list]
        assert not any("FT.CREATE" in c for c in calls)


class TestCoreCreateSearchIndexes:
    """Regression guard for #9943: the production init path must actually
    create the FT indexes (it was a no-op stub, so search stayed on SCAN)."""

    @pytest.mark.asyncio
    async def test_create_search_indexes_delegates_to_ensure_indexes(self, monkeypatch) -> None:
        from autobot_memory_graph.core import AutoBotMemoryGraphCore

        # Bypass the heavy __init__ (Config/Redis) — only the redis_client
        # attribute matters for this wiring check.
        inst = AutoBotMemoryGraphCore.__new__(AutoBotMemoryGraphCore)
        fake_client = MagicMock()
        inst.redis_client = fake_client

        captured: Dict[str, Any] = {}

        async def fake_ensure(client: Any) -> None:
            captured["client"] = client

        monkeypatch.setattr("autobot_memory_graph.semantic_search.ensure_indexes", fake_ensure)

        await inst._create_search_indexes()

        # The stub used to create nothing; it must now pass the live client
        # through to ensure_indexes so FT.CREATE actually runs.
        assert captured.get("client") is fake_client
