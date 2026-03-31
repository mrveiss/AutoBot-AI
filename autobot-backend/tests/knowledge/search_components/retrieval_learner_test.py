# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for RetrievalLearner — closed-loop RAG feedback loop. Issue #2095."""

import json
import time
from unittest.mock import AsyncMock

import pytest

from knowledge.search_components.retrieval_learner import (
    RetrievalLearner,
    RetrievalPattern,
    _compute_pattern_hash,
    _extract_categories,
    _jaccard_similarity,
    get_retrieval_learner,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock() -> AsyncMock:
    """Return a Redis mock with sensible defaults."""
    redis = AsyncMock()
    redis.xrange = AsyncMock(return_value=[])
    redis.hgetall = AsyncMock(return_value={})
    redis.hset = AsyncMock()
    redis.expire = AsyncMock()
    redis.delete = AsyncMock()
    redis.scan = AsyncMock(return_value=(0, []))
    return redis


def _make_learner(redis: AsyncMock) -> RetrievalLearner:
    learner = RetrievalLearner(redis=redis)
    learner._cursors_loaded = True  # skip Redis cursor load in tests
    return learner


def _make_feedback_fields(
    retrieved: list, ranked: list, complexity: str = "simple"
) -> dict:
    return {
        "retrieved_chunk_ids": json.dumps(retrieved),
        "final_ranked_ids": json.dumps(ranked),
        "complexity": complexity,
        "timestamp": str(time.time()),
    }


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


class TestComputePatternHash:
    def test_same_inputs_give_same_hash(self):
        h1 = _compute_pattern_hash("simple", ["system_knowledge"])
        h2 = _compute_pattern_hash("simple", ["system_knowledge"])
        assert h1 == h2

    def test_different_complexity_different_hash(self):
        h1 = _compute_pattern_hash("simple", ["cat_a"])
        h2 = _compute_pattern_hash("complex", ["cat_a"])
        assert h1 != h2

    def test_category_order_invariant(self):
        h1 = _compute_pattern_hash("moderate", ["b", "a"])
        h2 = _compute_pattern_hash("moderate", ["a", "b"])
        assert h1 == h2

    def test_hash_length_is_12(self):
        assert len(_compute_pattern_hash("simple", [])) == 12


class TestExtractCategories:
    def test_extracts_prefix_before_slash(self):
        cats = _extract_categories(["system_knowledge/uuid-1", "commands/uuid-2"])
        assert "system_knowledge" in cats
        assert "commands" in cats

    def test_no_slash_yields_empty(self):
        cats = _extract_categories(["plain-id", "another"])
        assert cats == []

    def test_deduplicates(self):
        cats = _extract_categories(["sys/a", "sys/b", "other/c"])
        assert cats.count("sys") == 1


class TestJaccardSimilarity:
    def test_identical_lists(self):
        assert _jaccard_similarity(["a", "b"], ["a", "b"]) == 1.0

    def test_disjoint_lists(self):
        assert _jaccard_similarity(["a"], ["b"]) == 0.0

    def test_partial_overlap(self):
        sim = _jaccard_similarity(["a", "b"], ["b", "c"])
        assert abs(sim - 1 / 3) < 1e-9

    def test_both_empty(self):
        assert _jaccard_similarity([], []) == 1.0


# ---------------------------------------------------------------------------
# RetrievalPattern serialisation
# ---------------------------------------------------------------------------


class TestRetrievalPatternRoundTrip:
    def test_to_and_from_redis_mapping(self):
        original = RetrievalPattern(
            pattern_hash="abc123",
            query_type="complex",
            chunk_categories=["cat_a", "cat_b"],
            strategy_hints={"enable_reranking": "true"},
            success_rate=0.85,
            usage_count=7,
        )
        mapping = original.to_redis_mapping()
        restored = RetrievalPattern.from_redis_mapping(mapping)

        assert restored.pattern_hash == original.pattern_hash
        assert restored.query_type == original.query_type
        assert restored.chunk_categories == original.chunk_categories
        assert restored.strategy_hints == original.strategy_hints
        assert abs(restored.success_rate - original.success_rate) < 1e-9
        assert restored.usage_count == original.usage_count

    def test_from_mapping_with_bytes_keys(self):
        mapping = {
            b"pattern_hash": b"deadbeef1234",
            b"query_type": b"simple",
            b"chunk_categories": b'["x"]',
            b"strategy_hints": b"{}",
            b"success_rate": b"0.5",
            b"usage_count": b"2",
            b"last_seen": b"0.0",
        }
        p = RetrievalPattern.from_redis_mapping(mapping)
        assert p.pattern_hash == "deadbeef1234"
        assert p.chunk_categories == ["x"]


# ---------------------------------------------------------------------------
# _score_trajectory
# ---------------------------------------------------------------------------


class TestScoreTrajectory:
    def test_identical_lists_not_successful(self):
        ids = ["a", "b", "c"]
        assert RetrievalLearner._score_trajectory(ids, ids) is False

    def test_empty_inputs_not_successful(self):
        assert RetrievalLearner._score_trajectory([], []) is False
        assert RetrievalLearner._score_trajectory(["a"], []) is False

    def test_reranking_promoted_majority(self):
        # Retrieved order: a b c d e  → ranked order: d e f a b
        # Top-5 retrieved: {a,b,c,d,e}  Top-5 ranked: {d,e,f,a,b}
        # Promoted (in ranked not in retrieved top-5): {f} → 1/5 = 0.2 < 0.6 → False
        retrieved = ["a", "b", "c", "d", "e"]
        ranked = ["d", "e", "f", "a", "b"]
        assert RetrievalLearner._score_trajectory(retrieved, ranked) is False

    def test_reranking_promoted_three_of_five(self):
        # Top-5 retrieved: {a,b,c,d,e}  Top-5 ranked: {x,y,z,a,b}
        # Promoted: {x,y,z} → 3/5 = 0.6 → True
        retrieved = ["a", "b", "c", "d", "e"]
        ranked = ["x", "y", "z", "a", "b"]
        assert RetrievalLearner._score_trajectory(retrieved, ranked) is True


# ---------------------------------------------------------------------------
# consume_feedback_stream
# ---------------------------------------------------------------------------


class TestConsumeFeedbackStream:
    @pytest.mark.asyncio
    async def test_empty_stream_returns_zero(self):
        redis = _make_redis_mock()
        learner = _make_learner(redis)
        count = await learner.consume_feedback_stream("2026-01-01")
        assert count == 0

    @pytest.mark.asyncio
    async def test_processes_successful_events_and_writes_pattern(self):
        redis = _make_redis_mock()

        # Build an event where reranking promotes 3 of 5 chunks (success=True).
        fields = _make_feedback_fields(
            retrieved=["a", "b", "c", "d", "e"],
            ranked=["x", "y", "z", "a", "b"],
            complexity="complex",
        )
        redis.xrange = AsyncMock(
            side_effect=[
                [("1000-0", fields)],  # first batch
                [],  # second batch → stop
            ]
        )
        # Simulate no existing pattern in Redis.
        redis.hgetall = AsyncMock(return_value={})

        learner = _make_learner(redis)
        count = await learner.consume_feedback_stream("2026-01-01")

        assert count == 1
        # hset should have been called to persist a new pattern.
        assert redis.hset.called

    @pytest.mark.asyncio
    async def test_neutral_event_not_distilled(self):
        """Identical retrieved and ranked IDs → not successful → no hset call."""
        redis = _make_redis_mock()
        ids = ["a", "b", "c"]
        fields = _make_feedback_fields(retrieved=ids, ranked=ids, complexity="simple")
        redis.xrange = AsyncMock(side_effect=[[("1000-0", fields)], []])

        learner = _make_learner(redis)
        await learner.consume_feedback_stream("2026-01-01")

        assert not redis.hset.called

    @pytest.mark.asyncio
    async def test_cursor_advances_after_processing(self):
        redis = _make_redis_mock()
        fields = _make_feedback_fields(
            retrieved=["a", "b", "c", "d", "e"],
            ranked=["x", "y", "z", "a", "b"],
        )
        redis.xrange = AsyncMock(side_effect=[[("2000-3", fields)], []])
        redis.hgetall = AsyncMock(return_value={})

        learner = _make_learner(redis)
        await learner.consume_feedback_stream("2026-01-15")

        stream_key = "rag:feedback:2026-01-15"
        assert learner._cursors.get(stream_key) == "2000-4"


# ---------------------------------------------------------------------------
# get_matching_pattern
# ---------------------------------------------------------------------------


class TestGetMatchingPattern:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_pattern_exists(self):
        redis = _make_redis_mock()
        redis.hgetall = AsyncMock(return_value={})
        learner = _make_learner(redis)
        result = await learner.get_matching_pattern(
            "how does X work?", complexity="moderate"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_pattern_meeting_confidence_threshold(self):
        redis = _make_redis_mock()
        pattern = RetrievalPattern(
            pattern_hash="aabbccddee11",
            query_type="complex",
            chunk_categories=["sys"],
            strategy_hints={"enable_reranking": "true"},
            success_rate=0.8,
            usage_count=5,
        )
        redis.hgetall = AsyncMock(return_value=pattern.to_redis_mapping())
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(
            "", complexity="complex", categories=["sys"]
        )
        assert result is not None
        assert result.success_rate == 0.8

    @pytest.mark.asyncio
    async def test_skips_pattern_below_usage_threshold(self):
        """Patterns with usage_count < 3 are ignored regardless of success_rate."""
        redis = _make_redis_mock()
        pattern = RetrievalPattern(
            pattern_hash="lowusage00001",
            query_type="simple",
            chunk_categories=[],
            strategy_hints={},
            success_rate=0.99,
            usage_count=2,
        )
        redis.hgetall = AsyncMock(return_value=pattern.to_redis_mapping())
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern("", complexity="simple")
        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_complexity_only_hash(self):
        """When no exact (complexity+categories) match, try complexity-only key."""
        redis = _make_redis_mock()
        # Exact match key returns empty; complexity-only returns valid pattern.
        exact_hash = _compute_pattern_hash("moderate", ["sys"])
        fallback_hash = _compute_pattern_hash("moderate", [])
        pattern = RetrievalPattern(
            pattern_hash=fallback_hash,
            query_type="moderate",
            chunk_categories=[],
            strategy_hints={},
            success_rate=0.7,
            usage_count=4,
        )

        async def fake_hgetall(key):
            if key.endswith(fallback_hash):
                return pattern.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(
            "", complexity="moderate", categories=["sys"]
        )
        assert result is not None
        assert result.pattern_hash == fallback_hash


# ---------------------------------------------------------------------------
# record_pattern_outcome
# ---------------------------------------------------------------------------


class TestRecordPatternOutcome:
    @pytest.mark.asyncio
    async def test_success_increases_success_rate(self):
        redis = _make_redis_mock()
        pattern = RetrievalPattern(
            pattern_hash="ph1",
            query_type="simple",
            chunk_categories=[],
            strategy_hints={},
            success_rate=0.5,
            usage_count=5,
        )
        redis.hgetall = AsyncMock(return_value=pattern.to_redis_mapping())

        learner = _make_learner(redis)
        await learner.record_pattern_outcome("ph1", success=True)

        # Verify hset was called with an updated success_rate: 0.5*0.9 + 1.0*0.1 = 0.55
        assert redis.hset.called
        call_kwargs = redis.hset.call_args[1]
        mapping = call_kwargs.get("mapping", {})
        assert float(mapping["success_rate"]) == pytest.approx(0.55, abs=1e-9)

    @pytest.mark.asyncio
    async def test_failure_decreases_success_rate(self):
        redis = _make_redis_mock()
        pattern = RetrievalPattern(
            pattern_hash="ph2",
            query_type="simple",
            chunk_categories=[],
            strategy_hints={},
            success_rate=0.8,
            usage_count=10,
        )
        redis.hgetall = AsyncMock(return_value=pattern.to_redis_mapping())

        learner = _make_learner(redis)
        await learner.record_pattern_outcome("ph2", success=False)

        call_kwargs = redis.hset.call_args[1]
        mapping = call_kwargs.get("mapping", {})
        # 0.8*0.9 + 0.0*0.1 = 0.72
        assert float(mapping["success_rate"]) == pytest.approx(0.72, abs=1e-9)

    @pytest.mark.asyncio
    async def test_noop_when_pattern_not_found(self):
        redis = _make_redis_mock()
        redis.hgetall = AsyncMock(return_value={})
        learner = _make_learner(redis)
        await learner.record_pattern_outcome("nonexistent", success=True)
        assert not redis.hset.called


# ---------------------------------------------------------------------------
# consolidate — dedup + prune
# ---------------------------------------------------------------------------


class TestConsolidate:
    def _make_pattern(self, ph, qt, cats, usage, last_seen=None):
        return RetrievalPattern(
            pattern_hash=ph,
            query_type=qt,
            chunk_categories=cats,
            strategy_hints={},
            success_rate=0.7,
            usage_count=usage,
            last_seen=last_seen or time.time(),
        )

    @pytest.mark.asyncio
    async def test_dedup_removes_lower_usage_duplicate(self):
        redis = _make_redis_mock()
        # Two patterns: same query_type, identical categories → Jaccard=1.0 → dedup.
        p1 = self._make_pattern("hash_a", "simple", ["cat"], usage=10)
        p2 = self._make_pattern("hash_b", "simple", ["cat"], usage=3)

        # SCAN returns both keys.
        redis.scan = AsyncMock(
            return_value=(
                0,
                ["rag:retrieval_patterns:hash_a", "rag:retrieval_patterns:hash_b"],
            )
        )

        async def fake_hgetall(key):
            if key.endswith("hash_a"):
                return p1.to_redis_mapping()
            if key.endswith("hash_b"):
                return p2.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)
        deduped, pruned = await learner.consolidate()

        assert deduped == 1
        assert pruned == 0
        # The lower-usage pattern (hash_b) should have been deleted.
        redis.delete.assert_called_once_with("rag:retrieval_patterns:hash_b")

    @pytest.mark.asyncio
    async def test_prune_removes_old_low_usage_pattern(self):
        redis = _make_redis_mock()
        # Pattern older than 30 days with usage < 3.
        old_ts = time.time() - (31 * 24 * 3600)
        p = self._make_pattern("stale_hash", "simple", [], usage=1, last_seen=old_ts)

        redis.scan = AsyncMock(return_value=(0, ["rag:retrieval_patterns:stale_hash"]))
        redis.hgetall = AsyncMock(return_value=p.to_redis_mapping())

        learner = _make_learner(redis)
        deduped, pruned = await learner.consolidate()

        assert pruned == 1
        assert deduped == 0
        redis.delete.assert_called_once_with("rag:retrieval_patterns:stale_hash")

    @pytest.mark.asyncio
    async def test_prune_keeps_well_used_old_pattern(self):
        redis = _make_redis_mock()
        old_ts = time.time() - (31 * 24 * 3600)
        p = self._make_pattern("kept_hash", "simple", [], usage=5, last_seen=old_ts)

        redis.scan = AsyncMock(return_value=(0, ["rag:retrieval_patterns:kept_hash"]))
        redis.hgetall = AsyncMock(return_value=p.to_redis_mapping())

        learner = _make_learner(redis)
        _, pruned = await learner.consolidate()

        assert pruned == 0
        assert not redis.delete.called


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------


class TestSingleton:
    def test_get_retrieval_learner_returns_same_instance(self):
        a = get_retrieval_learner()
        b = get_retrieval_learner()
        assert a is b

    def test_singleton_is_retrieval_learner_instance(self):
        assert isinstance(get_retrieval_learner(), RetrievalLearner)
