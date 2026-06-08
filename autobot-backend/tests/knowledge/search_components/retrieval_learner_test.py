# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
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
    _ucb1_score,
    get_retrieval_learner,
)
from tests.fixtures import make_async_redis

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_redis_mock() -> AsyncMock:
    # Migrated to canonical ``make_async_redis()`` (#7280 round 5).
    # ``hgetall``, ``hset``, ``expire``, ``delete`` are canonical defaults;
    # ``xrange=[]`` and ``scan=(0, [])`` flow through ``**extra_methods``.
    return make_async_redis(xrange=[], scan=(0, []))


def _make_learner(redis: AsyncMock) -> RetrievalLearner:
    learner = RetrievalLearner(redis=redis)
    learner._cursors_loaded = True  # skip Redis cursor load in tests
    return learner


def _make_feedback_fields(retrieved: list, ranked: list, complexity: str = "simple") -> dict:
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
        """Identical retrieved and ranked IDs → not successful → no PATTERN hset.

        #7386: production legitimately calls ``redis.hset(_CURSOR_HASH_KEY, ...)``
        after processing any event — cursor advance is required for correctness
        so the next ``consume_feedback_stream`` call doesn't re-process the
        same events. The original assertion ``not redis.hset.called`` was too
        coarse — it caught the cursor-save call as well as the (absent)
        pattern hset. Assert specifically that no hset hit the
        ``rag:retrieval:pattern:*`` namespace.
        """
        redis = _make_redis_mock()
        ids = ["a", "b", "c"]
        fields = _make_feedback_fields(retrieved=ids, ranked=ids, complexity="simple")
        redis.xrange = AsyncMock(side_effect=[[("1000-0", fields)], []])

        learner = _make_learner(redis)
        await learner.consume_feedback_stream("2026-01-01")

        # Cursor save (`rag:rl:cursors`) is allowed; pattern persistence
        # (`rag:retrieval:pattern:*`) is what neutral events MUST NOT trigger.
        pattern_hset_calls = [
            call
            for call in redis.hset.call_args_list
            if call.args and isinstance(call.args[0], str) and call.args[0].startswith("rag:retrieval:pattern:")
        ]
        assert not pattern_hset_calls, (
            f"#7386: neutral event triggered pattern persistence — "
            f"unexpected hset calls to pattern keys: {pattern_hset_calls}"
        )

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
        # Issue #3240: no user_id → uses __global__ sentinel in stream key.
        await learner.consume_feedback_stream("2026-01-15")

        stream_key = "rag:feedback:__global__:2026-01-15"
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
        result = await learner.get_matching_pattern("how does X work?", complexity="moderate")
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

        result = await learner.get_matching_pattern("", complexity="complex", categories=["sys"])
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
        _compute_pattern_hash("moderate", ["sys"])
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

        result = await learner.get_matching_pattern("", complexity="moderate", categories=["sys"])
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


# ---------------------------------------------------------------------------
# UCB1 score helper (Issue #4674)
# ---------------------------------------------------------------------------


import math as _math


class TestUcb1Score:
    def test_zero_usage_returns_inf(self):
        """Unexplored patterns always score highest."""
        score = _ucb1_score(0.5, usage_count=0, total_queries=10, exploration_constant=_math.sqrt(2))
        assert score == float("inf")

    def test_zero_total_queries_returns_success_rate(self):
        """When total_queries is 0, fall back to success_rate alone."""
        score = _ucb1_score(0.7, usage_count=5, total_queries=0, exploration_constant=_math.sqrt(2))
        assert score == pytest.approx(0.7)

    def test_higher_usage_gives_lower_bonus(self):
        """The exploration bonus shrinks as usage_count grows."""
        total = 100
        score_low = _ucb1_score(0.8, usage_count=5, total_queries=total, exploration_constant=_math.sqrt(2))
        score_high = _ucb1_score(0.8, usage_count=50, total_queries=total, exploration_constant=_math.sqrt(2))
        assert score_low > score_high

    def test_equal_success_rates_prefer_low_usage(self):
        """With equal success_rate, the lower-usage pattern has a higher UCB1 score."""
        total = 20
        score_a = _ucb1_score(0.75, usage_count=4, total_queries=total, exploration_constant=_math.sqrt(2))
        score_b = _ucb1_score(0.75, usage_count=16, total_queries=total, exploration_constant=_math.sqrt(2))
        assert score_a > score_b

    def test_exploration_constant_scales_bonus(self):
        """Larger C increases the exploration bonus proportionally."""
        s_low_c = _ucb1_score(0.5, usage_count=3, total_queries=30, exploration_constant=0.5)
        s_high_c = _ucb1_score(0.5, usage_count=3, total_queries=30, exploration_constant=2.0)
        assert s_high_c > s_low_c


# ---------------------------------------------------------------------------
# get_matching_pattern — UCB1 ranking (Issue #4674)
# ---------------------------------------------------------------------------


class TestGetMatchingPatternUCB1:
    def _make_pattern(self, ph, success_rate, usage_count, query_type="simple"):
        return RetrievalPattern(
            pattern_hash=ph,
            query_type=query_type,
            chunk_categories=[],
            strategy_hints={},
            success_rate=success_rate,
            usage_count=usage_count,
        )

    @pytest.mark.asyncio
    async def test_equal_success_rates_prefer_low_usage(self):
        """With equal success_rates, UCB1 should prefer the less-used pattern."""
        redis = _make_redis_mock()

        p_high_usage = self._make_pattern("hash_high", success_rate=0.8, usage_count=50)
        p_low_usage = self._make_pattern("hash_low", success_rate=0.8, usage_count=3)

        # Both patterns match the same complexity-only key — we wire exact key → high,
        # complexity-only key → low so both qualify for comparison.
        _compute_pattern_hash("simple", [])
        _compute_pattern_hash("simple", [])
        # exact_hash == complexity_hash when categories=[] → only one lookup happens
        # so instead we use categories to split them.
        exact_hash_with_cat = _compute_pattern_hash("simple", ["cat"])
        complexity_only_hash = _compute_pattern_hash("simple", [])

        from knowledge.search_components.retrieval_learner import _PATTERN_KEY_PREFIX, GLOBAL_USER

        key_exact = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{exact_hash_with_cat}"
        key_complexity = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{complexity_only_hash}"

        # Assign patterns to keys.
        async def fake_hgetall(key):
            if key == key_exact:
                return p_high_usage.to_redis_mapping()
            if key == key_complexity:
                return p_low_usage.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(
            "",
            complexity="simple",
            categories=["cat"],
            exploration_constant=_math.sqrt(2),
        )
        # UCB1 should select the low-usage pattern (higher exploration bonus).
        assert result is not None
        assert result.pattern_hash == "hash_low"

    @pytest.mark.asyncio
    async def test_greedy_fallback_when_all_usage_equal(self):
        """When all usage counts are equal, UCB1 degrades to selecting highest success_rate."""
        redis = _make_redis_mock()

        p_low_rate = self._make_pattern("hash_low_rate", success_rate=0.65, usage_count=5)
        p_high_rate = self._make_pattern("hash_high_rate", success_rate=0.90, usage_count=5)

        exact_hash_with_cat = _compute_pattern_hash("simple", ["cat"])
        complexity_only_hash = _compute_pattern_hash("simple", [])

        from knowledge.search_components.retrieval_learner import _PATTERN_KEY_PREFIX, GLOBAL_USER

        key_exact = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{exact_hash_with_cat}"
        key_complexity = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{complexity_only_hash}"

        async def fake_hgetall(key):
            if key == key_exact:
                return p_low_rate.to_redis_mapping()
            if key == key_complexity:
                return p_high_rate.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(
            "",
            complexity="simple",
            categories=["cat"],
            exploration_constant=_math.sqrt(2),
        )
        # Equal usage → exploration bonuses cancel → highest success_rate wins.
        assert result is not None
        assert result.pattern_hash == "hash_high_rate"


# ---------------------------------------------------------------------------
# Issue #4676 — benchmark → feedback → pattern round-trip
# ---------------------------------------------------------------------------


class TestBenchmarkFeedbackRoundTrip:
    """Verify that benchmark results flow through publish_feedback_events into
    the RetrievalLearner feedback stream and ultimately update global patterns.

    The test is fully in-memory: no Redis, no ChromaDB service required.
    """

    @pytest.mark.asyncio
    async def test_publish_feedback_events_writes_xadd_per_positive_result(self):
        """publish_feedback_events() calls xadd once per result with precision_at_k > 0."""
        from unittest.mock import AsyncMock

        from knowledge.rag_benchmarks import BenchmarkResult, publish_feedback_events

        redis = AsyncMock()
        redis.xadd = AsyncMock()
        redis.expire = AsyncMock()

        results = [
            BenchmarkResult(
                query="Python list comprehensions",
                retrieved_ids=["python_02", "python_04", "python_01"],
                ranked_ids=["python_02", "python_04", "python_01"],
                precision_at_k=0.4,
                complexity="moderate",
            ),
            BenchmarkResult(
                query="unknown topic query",
                retrieved_ids=["net_01"],
                ranked_ids=["net_01"],
                precision_at_k=0.0,  # zero precision — should NOT be published
                complexity="moderate",
            ),
        ]

        published = await publish_feedback_events(redis, results)

        # Only the positive-precision result should be published.
        assert published == 1
        assert redis.xadd.call_count == 1
        # expire should be called once to set TTL on the stream key.
        assert redis.expire.call_count == 1

    @pytest.mark.asyncio
    async def test_publish_feedback_events_writes_correct_schema(self):
        """Each published entry must include all fields expected by RetrievalLearner."""
        import json
        from unittest.mock import AsyncMock

        from knowledge.rag_benchmarks import BenchmarkResult, publish_feedback_events

        redis = AsyncMock()
        redis.xadd = AsyncMock()
        redis.expire = AsyncMock()

        result = BenchmarkResult(
            query="RAG retrieval augmented generation",
            retrieved_ids=["ml_02", "ml_09", "ml_01"],
            ranked_ids=["ml_02", "ml_09", "ml_01"],
            precision_at_k=0.4,
            complexity="moderate",
        )

        await publish_feedback_events(redis, [result])

        assert redis.xadd.call_count == 1
        _stream_key, entry = redis.xadd.call_args[0]
        assert "retrieved_chunk_ids" in entry
        assert "final_ranked_ids" in entry
        assert "complexity" in entry
        assert "timestamp" in entry
        # Verify JSON round-trip of retrieved_chunk_ids
        assert json.loads(entry["retrieved_chunk_ids"]) == result.retrieved_ids

    @pytest.mark.asyncio
    async def test_publish_feedback_events_uses_global_user_namespace(self):
        """Stream key must use '__global__' sentinel so all users benefit."""
        from unittest.mock import AsyncMock

        from knowledge.rag_benchmarks import BenchmarkResult, publish_feedback_events

        redis = AsyncMock()
        redis.xadd = AsyncMock()
        redis.expire = AsyncMock()

        result = BenchmarkResult(
            query="cosine similarity evaluation",
            retrieved_ids=["ml_04", "ml_05"],
            ranked_ids=["ml_04", "ml_05"],
            precision_at_k=0.4,
        )

        await publish_feedback_events(redis, [result])

        stream_key = redis.xadd.call_args[0][0]
        assert stream_key.startswith("rag:feedback:__global__:")

    @pytest.mark.asyncio
    async def test_learner_processes_benchmark_generated_events(self):
        """RetrievalLearner.consume_feedback_stream() processes benchmark events and writes pattern."""

        from knowledge.rag_benchmarks import _BENCHMARK_USER

        redis = _make_redis_mock()

        # Simulate a benchmark event where reranking promoted 3 of 5 chunks.
        # retrieved=[a,b,c,d,e], ranked=[x,y,z,a,b] → promoted={x,y,z} → 3/5=0.6 → success.
        fields = _make_feedback_fields(
            retrieved=["a", "b", "c", "d", "e"],
            ranked=["x", "y", "z", "a", "b"],
            complexity="moderate",
        )
        # Benchmark events may include extra fields — learner must tolerate them.
        fields["annotation"] = "benchmark"
        fields["precision_at_k"] = "0.4"

        redis.xrange = AsyncMock(side_effect=[[("5000-0", fields)], []])
        redis.hgetall = AsyncMock(return_value={})

        learner = _make_learner(redis)
        count = await learner.consume_feedback_stream(
            date_key="2026-01-01",
            user_id=_BENCHMARK_USER,
        )

        assert count == 1
        # Pattern must be distilled for the global namespace.
        # redis.hset is called twice: once for the pattern key, once for the cursor.
        # The pattern key contains '__global__'; cursor key is 'rag:rl:cursors'.
        assert redis.hset.called
        all_hset_keys = [call[0][0] for call in redis.hset.call_args_list]
        assert any(
            "__global__" in k for k in all_hset_keys
        ), f"Expected a pattern key containing '__global__' in hset calls; got {all_hset_keys}"

    @pytest.mark.asyncio
    async def test_publish_feedback_events_no_publish_when_all_zero_precision(self):
        """When all results have precision_at_k == 0, nothing is written to Redis."""
        from unittest.mock import AsyncMock

        from knowledge.rag_benchmarks import BenchmarkResult, publish_feedback_events

        redis = AsyncMock()
        redis.xadd = AsyncMock()
        redis.expire = AsyncMock()

        results = [
            BenchmarkResult("q1", ["doc1"], ["doc1"], precision_at_k=0.0),
            BenchmarkResult("q2", ["doc2"], ["doc2"], precision_at_k=0.0),
        ]

        published = await publish_feedback_events(redis, results)

        assert published == 0
        assert not redis.xadd.called
        assert not redis.expire.called
