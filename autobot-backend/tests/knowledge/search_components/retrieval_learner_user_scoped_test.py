# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Copyright (c) mrveiss. All rights reserved.
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for per-user annotation signals in RetrievalLearner (Issue #3240).

Covers:
- consume_feedback_stream writes to user-namespaced stream key
- _distil_pattern writes to user-namespaced Redis key
- get_matching_pattern returns user-scoped pattern when present
- get_matching_pattern falls back to global pattern when no user pattern
- get_matching_pattern returns None when neither user nor global pattern exist
- record_pattern_outcome updates the user-namespaced key
"""

import json
import time
from unittest.mock import AsyncMock

import pytest

from knowledge.search_components.retrieval_learner import (
    _PATTERN_KEY_PREFIX,
    GLOBAL_USER,
    RetrievalLearner,
    RetrievalPattern,
    _compute_pattern_hash,
)
from tests.fixtures import make_async_redis

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_USER_A = "user-alice-123"
_USER_B = "user-bob-456"


def _make_redis_mock() -> AsyncMock:
    # Migrated to canonical ``make_async_redis()`` (#7280 round 5).
    # ``hgetall``, ``hset``, ``expire``, ``delete`` are canonical defaults;
    # ``xrange=[]``, ``xadd`` (no-op), and ``scan=(0, [])`` flow through
    # ``**extra_methods``.
    return make_async_redis(xrange=[], xadd=None, scan=(0, []))


def _make_learner(redis: AsyncMock) -> RetrievalLearner:
    learner = RetrievalLearner(redis=redis)
    learner._cursors_loaded = True
    return learner


def _make_pattern(
    pattern_hash: str,
    query_type: str = "simple",
    success_rate: float = 0.8,
    usage_count: int = 5,
) -> RetrievalPattern:
    return RetrievalPattern(
        pattern_hash=pattern_hash,
        query_type=query_type,
        chunk_categories=[],
        strategy_hints={},
        success_rate=success_rate,
        usage_count=usage_count,
    )


def _make_feedback_fields(retrieved: list, ranked: list, complexity: str = "simple") -> dict:
    return {
        "retrieved_chunk_ids": json.dumps(retrieved),
        "final_ranked_ids": json.dumps(ranked),
        "complexity": complexity,
        "timestamp": str(time.time()),
    }


# ---------------------------------------------------------------------------
# Stream key namespacing (Issue #3240)
# ---------------------------------------------------------------------------


class TestFeedbackStreamKeyNamespacing:
    @pytest.mark.asyncio
    async def test_user_stream_key_includes_user_id(self):
        """consume_feedback_stream reads from rag:feedback:{user_id}:{date}."""
        redis = _make_redis_mock()
        learner = _make_learner(redis)

        await learner.consume_feedback_stream(date_key="2026-01-01", user_id=_USER_A)

        called_key = redis.xrange.call_args[0][0]
        assert called_key == f"rag:feedback:{_USER_A}:2026-01-01"

    @pytest.mark.asyncio
    async def test_global_stream_key_when_no_user_id(self):
        """consume_feedback_stream uses __global__ sentinel when user_id is None."""
        redis = _make_redis_mock()
        learner = _make_learner(redis)

        await learner.consume_feedback_stream(date_key="2026-01-01", user_id=None)

        called_key = redis.xrange.call_args[0][0]
        assert called_key == f"rag:feedback:{GLOBAL_USER}:2026-01-01"

    @pytest.mark.asyncio
    async def test_different_users_read_different_streams(self):
        """Two separate calls for different users read different stream keys."""
        redis_a = _make_redis_mock()
        redis_b = _make_redis_mock()
        learner_a = _make_learner(redis_a)
        learner_b = _make_learner(redis_b)

        await learner_a.consume_feedback_stream(date_key="2026-01-01", user_id=_USER_A)
        await learner_b.consume_feedback_stream(date_key="2026-01-01", user_id=_USER_B)

        key_a = redis_a.xrange.call_args[0][0]
        key_b = redis_b.xrange.call_args[0][0]
        assert key_a != key_b
        assert _USER_A in key_a
        assert _USER_B in key_b


# ---------------------------------------------------------------------------
# Pattern key namespacing (Issue #3240)
# ---------------------------------------------------------------------------


class TestPatternKeyNamespacing:
    @pytest.mark.asyncio
    async def test_distil_pattern_writes_to_user_scoped_key(self):
        """_distil_pattern writes pattern to rag:retrieval_patterns:{user_id}:{hash}."""
        redis = _make_redis_mock()
        redis.hgetall = AsyncMock(return_value={})
        learner = _make_learner(redis)

        await learner._distil_pattern(
            query_type="simple",
            categories=[],
            strategy_hints={},
            user_id=_USER_A,
        )

        ph = _compute_pattern_hash("simple", [])
        expected_key = f"{_PATTERN_KEY_PREFIX}{_USER_A}:{ph}"
        redis.hset.assert_called_once_with(expected_key, mapping=redis.hset.call_args[1]["mapping"])

    @pytest.mark.asyncio
    async def test_distil_pattern_uses_global_key_when_no_user(self):
        """_distil_pattern uses __global__ when user_id is not provided."""
        redis = _make_redis_mock()
        redis.hgetall = AsyncMock(return_value={})
        learner = _make_learner(redis)

        await learner._distil_pattern(
            query_type="simple",
            categories=[],
            strategy_hints={},
        )

        ph = _compute_pattern_hash("simple", [])
        expected_key = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{ph}"
        redis.hset.assert_called_once_with(expected_key, mapping=redis.hset.call_args[1]["mapping"])


# ---------------------------------------------------------------------------
# get_matching_pattern — user-scoped lookup with global fallback (Issue #3240)
# ---------------------------------------------------------------------------


class TestGetMatchingPatternUserScoped:
    @pytest.mark.asyncio
    async def test_returns_user_scoped_pattern_when_present(self):
        """Returns the user-scoped pattern when it meets confidence thresholds."""
        redis = _make_redis_mock()
        ph = _compute_pattern_hash("simple", [])
        user_key = f"{_PATTERN_KEY_PREFIX}{_USER_A}:{ph}"
        pattern = _make_pattern(ph, success_rate=0.9, usage_count=6)

        async def fake_hgetall(key):
            if key == user_key:
                return pattern.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(query="test", complexity="simple", user_id=_USER_A)

        assert result is not None
        assert result.pattern_hash == ph

    @pytest.mark.asyncio
    async def test_falls_back_to_global_when_no_user_pattern(self):
        """Falls back to __global__ pattern when user has no qualifying patterns."""
        redis = _make_redis_mock()
        ph = _compute_pattern_hash("simple", [])
        global_key = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{ph}"
        global_pattern = _make_pattern(ph, success_rate=0.75, usage_count=4)

        async def fake_hgetall(key):
            if key == global_key:
                return global_pattern.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(query="test", complexity="simple", user_id=_USER_A)

        assert result is not None
        assert result.pattern_hash == ph

    @pytest.mark.asyncio
    async def test_prefers_user_pattern_over_global(self):
        """User-scoped pattern is returned before global even when both exist."""
        redis = _make_redis_mock()
        ph = _compute_pattern_hash("simple", [])
        user_key = f"{_PATTERN_KEY_PREFIX}{_USER_A}:{ph}"
        global_key = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{ph}"

        user_pattern = _make_pattern(ph, success_rate=0.65, usage_count=3)
        global_pattern = _make_pattern(ph, success_rate=0.99, usage_count=100)

        async def fake_hgetall(key):
            if key == user_key:
                return user_pattern.to_redis_mapping()
            if key == global_key:
                return global_pattern.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(query="test", complexity="simple", user_id=_USER_A)

        # Should return the user-scoped pattern even though global has higher rate.
        assert result is not None
        assert result.success_rate == pytest.approx(0.65)

    @pytest.mark.asyncio
    async def test_returns_none_when_neither_user_nor_global_pattern_exists(self):
        """Returns None when neither user nor global patterns exist."""
        redis = _make_redis_mock()
        redis.hgetall = AsyncMock(return_value={})
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(query="test", complexity="simple", user_id=_USER_A)

        assert result is None

    @pytest.mark.asyncio
    async def test_global_scope_only_checks_global_keys(self):
        """When user_id is None, only global keys are checked (no duplicate lookups)."""
        redis = _make_redis_mock()
        redis.hgetall = AsyncMock(return_value={})
        learner = _make_learner(redis)

        await learner.get_matching_pattern(query="test", complexity="simple", user_id=None)

        # With no user_id, only 2 candidates (exact + complexity-only under __global__).
        assert redis.hgetall.call_count == 2
        for call in redis.hgetall.call_args_list:
            key = call[0][0]
            assert f":{GLOBAL_USER}:" in key

    @pytest.mark.asyncio
    async def test_user_lookup_skips_low_confidence_patterns(self):
        """User-scoped pattern with usage_count < 3 is skipped; global is checked next."""
        redis = _make_redis_mock()
        ph = _compute_pattern_hash("moderate", [])
        user_key = f"{_PATTERN_KEY_PREFIX}{_USER_A}:{ph}"
        global_key = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{ph}"

        # User pattern has insufficient usage; global meets threshold.
        low_usage_pattern = _make_pattern(ph, success_rate=0.99, usage_count=2)
        global_pattern = _make_pattern(ph, success_rate=0.7, usage_count=10)

        async def fake_hgetall(key):
            if key == user_key:
                return low_usage_pattern.to_redis_mapping()
            if key == global_key:
                return global_pattern.to_redis_mapping()
            return {}

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        learner = _make_learner(redis)

        result = await learner.get_matching_pattern(query="", complexity="moderate", user_id=_USER_A)

        # Should fall back to the global pattern.
        assert result is not None
        assert result.usage_count == 10


# ---------------------------------------------------------------------------
# record_pattern_outcome — user-namespaced key (Issue #3240)
# ---------------------------------------------------------------------------


class TestRecordPatternOutcomeUserScoped:
    @pytest.mark.asyncio
    async def test_updates_user_scoped_key(self):
        """record_pattern_outcome modifies the user-namespaced Redis key."""
        redis = _make_redis_mock()
        ph = "abc123def456"
        user_key = f"{_PATTERN_KEY_PREFIX}{_USER_A}:{ph}"
        pattern = _make_pattern(ph, success_rate=0.5, usage_count=5)
        redis.hgetall = AsyncMock(return_value=pattern.to_redis_mapping())

        learner = _make_learner(redis)
        await learner.record_pattern_outcome(ph, success=True, user_id=_USER_A)

        redis.hgetall.assert_called_once_with(user_key)
        assert redis.hset.called

    @pytest.mark.asyncio
    async def test_updates_global_key_when_no_user(self):
        """record_pattern_outcome uses __global__ scope when user_id is None."""
        redis = _make_redis_mock()
        ph = "deadbeef1234"
        global_key = f"{_PATTERN_KEY_PREFIX}{GLOBAL_USER}:{ph}"
        pattern = _make_pattern(ph)
        redis.hgetall = AsyncMock(return_value=pattern.to_redis_mapping())

        learner = _make_learner(redis)
        await learner.record_pattern_outcome(ph, success=False, user_id=None)

        redis.hgetall.assert_called_once_with(global_key)

    @pytest.mark.asyncio
    async def test_noop_when_pattern_not_found_for_user(self):
        """No hset call when user-scoped key is absent in Redis."""
        redis = _make_redis_mock()
        redis.hgetall = AsyncMock(return_value={})
        learner = _make_learner(redis)

        await learner.record_pattern_outcome("missing_hash", success=True, user_id=_USER_A)

        assert not redis.hset.called


# ---------------------------------------------------------------------------
# End-to-end: consume → distil → lookup (Issue #3240)
# ---------------------------------------------------------------------------


class TestEndToEndUserScopedLearning:
    @pytest.mark.asyncio
    async def test_user_feedback_creates_user_pattern_consumed_at_query_time(self):
        """Full loop: consume stream → distil pattern → lookup returns user pattern."""
        redis = _make_redis_mock()

        # Build a successful feedback event for user A.
        fields = _make_feedback_fields(
            retrieved=["a", "b", "c", "d", "e"],
            ranked=["x", "y", "z", "a", "b"],
            complexity="complex",
        )
        redis.xrange = AsyncMock(side_effect=[[("1000-0", fields)], []])

        # Simulate that hgetall returns {} on write (no existing pattern),
        # then returns the written pattern on read.
        written: dict = {}

        async def fake_hgetall(key):
            return written.get(key, {})

        async def fake_hset(key, mapping):
            written[key] = mapping

        redis.hgetall = AsyncMock(side_effect=fake_hgetall)
        redis.hset = AsyncMock(side_effect=fake_hset)

        learner = _make_learner(redis)

        # Step 1: consume stream for user A.
        count = await learner.consume_feedback_stream(date_key="2026-01-01", user_id=_USER_A)
        assert count == 1

        # Manually set usage_count and success_rate so the pattern passes thresholds.
        ph = _compute_pattern_hash("complex", [])
        user_key = f"{_PATTERN_KEY_PREFIX}{_USER_A}:{ph}"
        if user_key in written:
            mapping = written[user_key]
            mapping["usage_count"] = "3"
            mapping["success_rate"] = "0.8"

        # Step 2: query-time lookup for user A returns the distilled pattern.
        result = await learner.get_matching_pattern(query="complex query", complexity="complex", user_id=_USER_A)

        assert result is not None
        assert result.query_type == "complex"
