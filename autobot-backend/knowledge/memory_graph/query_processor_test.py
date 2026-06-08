# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) mrveiss. All rights reserved.
# AutoBot - AI-Powered Automation Platform
"""
Unit tests for memory graph query processor and hybrid scorer.

Issue #3384: Phase 1 & 2 tests — all Redis and embedding calls are mocked.

Run with:
    pytest autobot-backend/knowledge/memory_graph/query_processor_test.py -v
"""

import json
import math
import sys
import types
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Stub out heavy transitive imports before the module is loaded
# ---------------------------------------------------------------------------


def _make_module(name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(mod, k, v)
    return mod


# autobot_shared stubs
_redis_mod = _make_module("autobot_shared.redis_client")
_redis_mod.get_redis_client = AsyncMock(return_value=MagicMock())

_ssot_mod = _make_module("autobot_shared.ssot_config")
_ssot_cfg = MagicMock()
_ssot_mod.config = _ssot_cfg

# services.npu_client stub
_npu_mod = _make_module(
    "services.npu_client",
    generate_embedding_with_fallback=AsyncMock(return_value=[0.1] * 768),
)

for _name, _mod in [
    ("autobot_shared", _make_module("autobot_shared")),
    ("autobot_shared.redis_client", _redis_mod),
    ("autobot_shared.ssot_config", _ssot_mod),
    ("services", _make_module("services")),
    ("services.npu_client", _npu_mod),
]:
    sys.modules.setdefault(_name, _mod)

# Now safe to import the modules under test
from knowledge.memory_graph.hybrid_scorer import (  # noqa: E402
    HybridScorer,
    SearchResult,
    _entity_to_text,
    cosine_similarity,
)
from knowledge.memory_graph.query_processor import (  # noqa: E402
    MemoryGraphQueryProcessor,
    QueryIntent,
    _build_redis_query,
    _merge_filters,
    _parse_ft_results,
)

# ===========================================================================
# Fixtures
# ===========================================================================


def _make_entity(
    entity_id: str = "abc123",
    name: str = "System Status Bug",
    entity_type: str = "BUG",
    observations=None,
    status: str = "completed",
    created_at: int = 1_700_000_000_000,
) -> dict:
    return {
        "id": entity_id,
        "name": name,
        "type": entity_type,
        "observations": observations or ["Fixed broken endpoint", "Deployed fix"],
        "metadata": {"status": status},
        "created_at": created_at,
    }


def _make_embedding(dim: int = 768, value: float = 0.1) -> list:
    return [value] * dim


# ===========================================================================
# Tests: cosine_similarity
# ===========================================================================


class TestCosineSimilarity:
    def test_identical_vectors_return_one(self):
        vec = [1.0, 0.0, 0.0]
        assert cosine_similarity(vec, vec) == pytest.approx(1.0, abs=1e-6)

    def test_orthogonal_vectors_return_zero(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0, abs=1e-6)

    def test_opposite_vectors_clamped_to_zero(self):
        # cosine of 180° is -1; we clamp to 0
        assert cosine_similarity([1.0], [-1.0]) == 0.0

    def test_none_vector_returns_zero(self):
        assert cosine_similarity(None, [1.0, 0.0]) == 0.0
        assert cosine_similarity([1.0, 0.0], None) == 0.0

    def test_empty_vector_returns_zero(self):
        assert cosine_similarity([], [1.0]) == 0.0

    def test_dimension_mismatch_returns_zero(self):
        assert cosine_similarity([1.0, 0.0], [1.0]) == 0.0

    def test_zero_magnitude_returns_zero(self):
        assert cosine_similarity([0.0, 0.0], [1.0, 0.0]) == 0.0

    def test_partial_overlap(self):
        a = [1.0, 1.0, 0.0]
        b = [1.0, 0.0, 0.0]
        # cos(45°) ≈ 0.707
        result = cosine_similarity(a, b)
        assert 0.5 < result < 0.9

    def test_high_dimensional_vectors(self):
        dim = 768
        a = [1.0 / math.sqrt(dim)] * dim
        b = [1.0 / math.sqrt(dim)] * dim
        assert cosine_similarity(a, b) == pytest.approx(1.0, abs=1e-4)


# ===========================================================================
# Tests: HybridScorer.bm25_score
# ===========================================================================


class TestBM25Score:
    def setup_method(self):
        self.scorer = HybridScorer()

    def test_matching_keyword_returns_positive(self):
        score, matched = self.scorer.bm25_score(["bug"], "we fixed a bug in the system")
        assert score > 0.0
        assert "bug" in matched

    def test_no_keywords_returns_zero(self):
        score, matched = self.scorer.bm25_score([], "some text")
        assert score == 0.0
        assert matched == []

    def test_empty_document_returns_zero(self):
        score, matched = self.scorer.bm25_score(["bug"], "")
        assert score == 0.0

    def test_missing_keyword_not_in_matched(self):
        score, matched = self.scorer.bm25_score(["xyz"], "we fixed a bug")
        assert score == 0.0
        assert matched == []

    def test_multiple_keywords_accumulate(self):
        score_one, _ = self.scorer.bm25_score(["bug"], "we fixed a bug")
        score_two, _ = self.scorer.bm25_score(["bug", "fixed"], "we fixed a bug")
        assert score_two >= score_one

    def test_score_normalised_to_one(self):
        # Saturate: many occurrences of the single keyword
        doc = "bug " * 200
        score, matched = self.scorer.bm25_score(["bug"], doc)
        assert 0.0 <= score <= 1.0
        assert "bug" in matched

    def test_repeated_term_diminishing_returns(self):
        score_one, _ = self.scorer.bm25_score(["bug"], "bug")
        score_many, _ = self.scorer.bm25_score(["bug"], "bug " * 50)
        # BM25 saturates — many occurrences should be less than k1+1 times one
        assert score_many < 10 * score_one


# ===========================================================================
# Tests: _entity_to_text
# ===========================================================================


class TestEntityToText:
    def test_name_repeated_three_times(self):
        entity = {"name": "MyEntity", "type": "BUG", "observations": []}
        text = _entity_to_text(entity)
        assert text.lower().count("myentity") == 3

    def test_observations_included(self):
        entity = {
            "name": "E",
            "type": "BUG",
            "observations": ["Fixed endpoint"],
        }
        text = _entity_to_text(entity)
        assert "fixed endpoint" in text.lower()

    def test_json_string_observations_decoded(self):
        entity = {
            "name": "E",
            "type": "BUG",
            "observations": '["obs1", "obs2"]',
        }
        text = _entity_to_text(entity)
        assert "obs1" in text.lower()

    def test_empty_entity_returns_string(self):
        text = _entity_to_text({})
        assert isinstance(text, str)


# ===========================================================================
# Tests: QueryIntent intent extraction
# ===========================================================================


class TestIntentExtraction:
    def setup_method(self):
        redis_mock = AsyncMock()
        redis_mock.json = MagicMock(return_value=AsyncMock())
        redis_mock.get = AsyncMock(return_value=None)
        self.processor = MemoryGraphQueryProcessor(redis_client=redis_mock)

    def _extract(self, query: str) -> QueryIntent:
        return self.processor._extract_intent(query)

    def test_today_sets_time_range(self):
        intent = self._extract("What did we fix today?")
        assert intent.time_range is not None
        assert intent.time_range["start"] == datetime.now().date()

    def test_yesterday_sets_time_range(self):
        intent = self._extract("Show me bugs from yesterday")
        expected = (datetime.now() - timedelta(days=1)).date()
        assert intent.time_range is not None
        assert intent.time_range["start"] == expected

    def test_last_n_days_sets_time_range(self):
        intent = self._extract("tasks from last 7 days")
        expected = (datetime.now() - timedelta(days=7)).date()
        assert intent.time_range is not None
        assert intent.time_range["start"] == expected

    def test_bug_keyword_maps_entity_type(self):
        intent = self._extract("show me bug reports")
        assert "bug_fix" in intent.entity_types

    def test_fix_keyword_maps_entity_type(self):
        intent = self._extract("what fixes were deployed?")
        assert "bug_fix" in intent.entity_types

    def test_feature_keyword_maps_entity_type(self):
        intent = self._extract("new features this week")
        assert "feature" in intent.entity_types

    def test_completed_keyword_maps_status(self):
        intent = self._extract("tasks we completed")
        assert intent.status_filter == "completed"

    def test_no_filters_when_generic_query(self):
        intent = self._extract("tell me everything")
        assert intent.entity_types == []
        assert intent.time_range is None
        assert intent.status_filter is None

    def test_keywords_exclude_stopwords(self):
        intent = self._extract("what bugs did we fix today")
        assert "what" not in intent.keywords
        assert "did" not in intent.keywords
        assert "bugs" in intent.keywords

    def test_semantic_query_is_non_empty(self):
        intent = self._extract("What bugs did we fix?")
        assert intent.semantic_query


# ===========================================================================
# Tests: _build_redis_query
# ===========================================================================


class TestBuildRedisQuery:
    def _intent(self, **kwargs) -> QueryIntent:
        i = QueryIntent()
        for k, v in kwargs.items():
            setattr(i, k, v)
        return i

    def test_empty_intent_returns_star(self):
        assert _build_redis_query(QueryIntent()) == "*"

    def test_single_entity_type(self):
        intent = self._intent(entity_types=["BUG"])
        q = _build_redis_query(intent)
        assert "@type:(BUG)" in q

    def test_multiple_entity_types_pipe_separated(self):
        intent = self._intent(entity_types=["BUG", "FEATURE"])
        q = _build_redis_query(intent)
        assert "BUG|FEATURE" in q

    def test_status_filter(self):
        intent = self._intent(status_filter="completed")
        q = _build_redis_query(intent)
        assert "@status:{completed}" in q

    def test_time_range_filter(self):
        start = datetime.now().date()
        intent = self._intent(time_range={"start": start})
        q = _build_redis_query(intent)
        assert "@created_at:[" in q
        assert "+inf]" in q

    def test_combined_filters(self):
        intent = self._intent(
            entity_types=["BUG"],
            status_filter="completed",
        )
        q = _build_redis_query(intent)
        assert "@type:(BUG)" in q
        assert "@status:{completed}" in q


# ===========================================================================
# Tests: _merge_filters
# ===========================================================================


class TestMergeFilters:
    def test_merges_entity_types(self):
        intent = QueryIntent(entity_types=["BUG"])
        _merge_filters(intent, {"entity_types": ["FEATURE"]})
        assert "BUG" in intent.entity_types
        assert "FEATURE" in intent.entity_types

    def test_no_duplicate_entity_types(self):
        intent = QueryIntent(entity_types=["BUG"])
        _merge_filters(intent, {"entity_types": ["BUG"]})
        assert intent.entity_types.count("BUG") == 1

    def test_time_range_not_overwritten(self):
        existing = {"start": datetime.now().date()}
        intent = QueryIntent(time_range=existing)
        _merge_filters(intent, {"time_range": {"start": "other"}})
        assert intent.time_range == existing

    def test_status_not_overwritten(self):
        intent = QueryIntent(status_filter="completed")
        _merge_filters(intent, {"status": "pending"})
        assert intent.status_filter == "completed"


# ===========================================================================
# Tests: _parse_ft_results
# ===========================================================================


class TestParseFtResults:
    def test_empty_response_returns_empty(self):
        assert _parse_ft_results(None) == []
        assert _parse_ft_results([]) == []
        assert _parse_ft_results([0]) == []

    def test_single_result_with_fields(self):
        raw = [
            1,  # total count
            b"memory:entity:abc",
            [b"name", b"Test Entity", b"type", b"BUG"],
        ]
        results = _parse_ft_results(raw)
        assert len(results) == 1
        assert results[0]["name"] == "Test Entity"
        assert results[0]["type"] == "BUG"

    def test_json_field_decoded(self):
        obs_json = json.dumps(["obs1", "obs2"])
        raw = [
            1,
            b"memory:entity:x",
            [b"observations", obs_json.encode("utf-8")],
        ]
        results = _parse_ft_results(raw)
        assert results[0]["observations"] == ["obs1", "obs2"]

    def test_multiple_results(self):
        raw = [
            2,
            b"memory:entity:a",
            [b"name", b"Entity A"],
            b"memory:entity:b",
            [b"name", b"Entity B"],
        ]
        results = _parse_ft_results(raw)
        assert len(results) == 2


# ===========================================================================
# Tests: HybridScorer.score_and_rank (async)
# ===========================================================================


class TestScoreAndRank:
    def setup_method(self):
        self.scorer = HybridScorer()

    @pytest.mark.asyncio
    async def test_returns_top_k_results(self):
        entities = [_make_entity(entity_id=str(i), name=f"E{i}") for i in range(5)]
        intent = QueryIntent(keywords=["bug", "fixed"])
        q_embed = _make_embedding()

        with patch(
            "knowledge.memory_graph.hybrid_scorer._fetch_entity_embedding",
            new=AsyncMock(return_value=_make_embedding()),
        ):
            results = await self.scorer.score_and_rank(
                query="bug fix",
                intent=intent,
                candidates=entities,
                query_embedding=q_embed,
                limit=3,
            )

        assert len(results) == 3

    @pytest.mark.asyncio
    async def test_results_sorted_descending(self):
        entities = [_make_entity(entity_id=str(i), name=f"E{i}") for i in range(4)]
        intent = QueryIntent(keywords=["fixed"])
        q_embed = _make_embedding()

        with patch(
            "knowledge.memory_graph.hybrid_scorer._fetch_entity_embedding",
            new=AsyncMock(return_value=_make_embedding()),
        ):
            results = await self.scorer.score_and_rank("fixed", intent, entities, q_embed, limit=10)

        scores = [r.score for r in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_missing_embedding_degrades_to_keyword(self):
        entity = _make_entity(observations=["fixed the bug in endpoint"])
        intent = QueryIntent(keywords=["bug", "endpoint"])

        with patch(
            "knowledge.memory_graph.hybrid_scorer._fetch_entity_embedding",
            new=AsyncMock(return_value=None),
        ):
            results = await self.scorer.score_and_rank(
                "bug endpoint",
                intent,
                [entity],
                query_embedding=None,
                limit=5,
            )

        assert len(results) == 1
        assert results[0].semantic_score == 0.0
        assert results[0].keyword_score > 0.0

    @pytest.mark.asyncio
    async def test_empty_candidates_returns_empty(self):
        results = await self.scorer.score_and_rank("query", QueryIntent(), [], None, 5)
        assert results == []

    @pytest.mark.asyncio
    async def test_score_within_bounds(self):
        entity = _make_entity()
        intent = QueryIntent(keywords=["fixed"])
        q_embed = _make_embedding()

        with patch(
            "knowledge.memory_graph.hybrid_scorer._fetch_entity_embedding",
            new=AsyncMock(return_value=_make_embedding()),
        ):
            results = await self.scorer.score_and_rank("fixed", intent, [entity], q_embed, limit=1)

        r = results[0]
        assert 0.0 <= r.score <= 1.0
        assert 0.0 <= r.semantic_score <= 1.0
        assert 0.0 <= r.keyword_score <= 1.0


# ===========================================================================
# Tests: MemoryGraphQueryProcessor.process_query (async, integrated)
# ===========================================================================


class TestProcessQuery:
    def _make_processor(self, candidates=None, embedding=None):
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        redis_mock.setex = AsyncMock()
        redis_mock.execute_command = AsyncMock(return_value=_build_raw_ft_response(candidates or []))

        processor = MemoryGraphQueryProcessor(redis_client=redis_mock)

        embed_patch = patch(
            "knowledge.memory_graph.query_processor._generate_embedding",
            new=AsyncMock(return_value=embedding or _make_embedding()),
        )
        entity_embed_patch = patch(
            "knowledge.memory_graph.hybrid_scorer._fetch_entity_embedding",
            new=AsyncMock(return_value=_make_embedding()),
        )
        return processor, embed_patch, entity_embed_patch

    @pytest.mark.asyncio
    async def test_empty_query_returns_empty(self):
        processor, ep, eep = self._make_processor()
        with ep, eep:
            results = await processor.process_query("")
        assert results == []

    @pytest.mark.asyncio
    async def test_returns_list_of_search_results(self):
        candidates = [_make_entity(entity_id="1", name="Bug Fix")]
        processor, ep, eep = self._make_processor(candidates=candidates)
        with ep, eep:
            results = await processor.process_query("bug fix")
        assert isinstance(results, list)
        for r in results:
            assert isinstance(r, SearchResult)

    @pytest.mark.asyncio
    async def test_no_candidates_returns_empty(self):
        processor, ep, eep = self._make_processor(candidates=[])
        with ep, eep:
            results = await processor.process_query("some query")
        assert results == []

    @pytest.mark.asyncio
    async def test_respects_limit(self):
        candidates = [_make_entity(entity_id=str(i), name=f"E{i}") for i in range(10)]
        processor, ep, eep = self._make_processor(candidates=candidates)
        with ep, eep:
            results = await processor.process_query("fix bugs", limit=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_caller_filters_merged(self):
        processor, ep, eep = self._make_processor(candidates=[])
        intent_captured = []

        original_build = __import__(
            "knowledge.memory_graph.query_processor",
            fromlist=["_build_redis_query"],
        )._build_redis_query

        def capturing_build(intent):
            intent_captured.append(intent)
            return original_build(intent)

        with (
            ep,
            eep,
            patch(
                "knowledge.memory_graph.query_processor._build_redis_query",
                side_effect=capturing_build,
            ),
        ):
            await processor.process_query("query", filters={"entity_types": ["FEATURE"]})

        assert intent_captured
        assert "FEATURE" in intent_captured[0].entity_types


# ===========================================================================
# Tests: get_entity / get_related_entities
# ===========================================================================


class TestEntityRetrieval:
    @pytest.mark.asyncio
    async def test_get_entity_returns_doc(self):
        entity = _make_entity()
        redis_mock = AsyncMock()
        json_mock = AsyncMock()
        json_mock.get = AsyncMock(return_value=entity)
        redis_mock.json = MagicMock(return_value=json_mock)

        processor = MemoryGraphQueryProcessor(redis_client=redis_mock)
        result = await processor.get_entity("abc123")
        assert result == entity

    @pytest.mark.asyncio
    async def test_get_entity_returns_none_on_error(self):
        redis_mock = AsyncMock()
        json_mock = AsyncMock()
        json_mock.get = AsyncMock(side_effect=Exception("Redis error"))
        redis_mock.json = MagicMock(return_value=json_mock)

        processor = MemoryGraphQueryProcessor(redis_client=redis_mock)
        result = await processor.get_entity("bad-id")
        assert result is None

    @pytest.mark.asyncio
    async def test_get_related_entities_empty_when_no_key(self):
        """Returns [] when source entity not found by name."""
        redis_mock = AsyncMock()
        # get_entity_by_name uses FT.SEARCH — return empty response
        redis_mock.execute_command = AsyncMock(return_value=[0])

        processor = MemoryGraphQueryProcessor(redis_client=redis_mock)
        results = await processor.get_related_entities("NonExistent")
        assert results == []

    @pytest.mark.asyncio
    async def test_get_related_entities_follows_relations(self):
        source_entity = _make_entity(name="Source Entity")
        related_entity = _make_entity(name="Related Entity")
        relations_doc = {
            "entity_id": source_entity["id"],
            "relations": [{"to": "Related Entity", "type": "relates_to"}],
        }

        json_mock = AsyncMock()
        json_mock.get = AsyncMock(return_value=relations_doc)
        redis_mock = AsyncMock()
        redis_mock.json = MagicMock(return_value=json_mock)

        # First FT.SEARCH call → source entity; second → related entity
        redis_mock.execute_command = AsyncMock(
            side_effect=[
                _build_raw_ft_response([source_entity]),
                _build_raw_ft_response([related_entity]),
            ]
        )

        processor = MemoryGraphQueryProcessor(redis_client=redis_mock)
        results = await processor.get_related_entities("Source Entity")
        assert len(results) == 1


# ===========================================================================
# Helpers
# ===========================================================================


def _build_raw_ft_response(entities: list) -> list:
    """Build a minimal FT.SEARCH-style response for a list of entity dicts."""
    raw = [len(entities)]
    for i, entity in enumerate(entities):
        key = f"memory:entity:{entity.get('id', i)}".encode("utf-8")
        fields = []
        for fname, fval in entity.items():
            fields.append(fname.encode("utf-8"))
            if isinstance(fval, (dict, list)):
                fields.append(json.dumps(fval).encode("utf-8"))
            else:
                fields.append(str(fval).encode("utf-8"))
        raw.append(key)
        raw.append(fields)
    return raw
