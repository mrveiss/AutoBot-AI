# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Fast-fail Redis guard tests for RetrievalLearner (#10980).

Verifies three guarantees:
(a) _get_redis() returns None quickly (within the timeout) when get_redis_client
    hangs or raises, and sets _redis_unavailable.
(b) Hot-path methods (consume_feedback_stream, get_matching_pattern,
    record_pattern_outcome, consolidate) degrade to no-op / default return
    values when Redis is unavailable — they never raise.
(c) Once _redis_unavailable is cached, _get_redis() returns None WITHOUT
    calling get_redis_client again (no retry on the second call).
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from knowledge.search_components.retrieval_learner import (
    _REDIS_ACQUIRE_TIMEOUT,
    RetrievalLearner,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_learner_no_redis() -> RetrievalLearner:
    """Return a fresh learner with no pre-injected Redis client."""
    learner = RetrievalLearner()
    learner._cursors_loaded = True  # skip cursor-load I/O in tests
    return learner


# ---------------------------------------------------------------------------
# (a) _get_redis() fast-fail: returns None quickly on hang / error
# ---------------------------------------------------------------------------


class TestGetRedisFastFail:
    @pytest.mark.asyncio
    async def test_returns_none_when_get_redis_client_hangs(self):
        """_get_redis() must complete within the timeout even if the factory hangs.

        We mock get_redis_client to sleep for 10 s (far exceeding the 1.5 s
        default), wrap the call itself in a tight outer asyncio.wait_for so the
        test cannot block CI, and assert the result is None.
        """
        learner = _make_learner_no_redis()

        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)

        with patch(
            "knowledge.search_components.retrieval_learner.get_redis_client",
            new=_hang,
        ):
            # Allow up to (timeout + 0.5 s) for the call to complete.
            result = await asyncio.wait_for(
                learner._get_redis(),
                timeout=_REDIS_ACQUIRE_TIMEOUT + 0.5,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_sets_redis_unavailable_on_hang(self):
        """After a hang, _redis_unavailable must be True."""
        learner = _make_learner_no_redis()

        async def _hang(*args, **kwargs):
            await asyncio.sleep(10)

        with patch(
            "knowledge.search_components.retrieval_learner.get_redis_client",
            new=_hang,
        ):
            await asyncio.wait_for(
                learner._get_redis(),
                timeout=_REDIS_ACQUIRE_TIMEOUT + 0.5,
            )

        assert learner._redis_unavailable is True

    @pytest.mark.asyncio
    async def test_returns_none_when_get_redis_client_raises(self):
        """_get_redis() returns None (does not raise) when the factory raises."""
        learner = _make_learner_no_redis()

        async def _raise(*args, **kwargs):
            raise ConnectionRefusedError("Redis is down")

        with patch(
            "knowledge.search_components.retrieval_learner.get_redis_client",
            new=_raise,
        ):
            result = await learner._get_redis()

        assert result is None
        assert learner._redis_unavailable is True

    @pytest.mark.asyncio
    async def test_returns_injected_redis_immediately(self):
        """When a Redis client was injected at construction, _get_redis() returns it
        without ever calling get_redis_client (no I/O on the hot path)."""
        mock_redis = MagicMock()
        learner = RetrievalLearner(redis=mock_redis)

        with patch(
            "knowledge.search_components.retrieval_learner.get_redis_client",
            side_effect=AssertionError("should not be called"),
        ):
            result = await learner._get_redis()

        assert result is mock_redis


# ---------------------------------------------------------------------------
# (b) Hot-path methods degrade to no-op when Redis is unavailable
# ---------------------------------------------------------------------------


class TestNoOpDegradationWhenUnavailable:
    def _make_unavailable_learner(self) -> RetrievalLearner:
        """Return a learner whose Redis is pre-marked unavailable."""
        learner = _make_learner_no_redis()
        learner._redis_unavailable = True
        return learner

    @pytest.mark.asyncio
    async def test_consume_feedback_stream_returns_zero(self):
        """consume_feedback_stream() returns 0 without raising when Redis is out."""
        learner = self._make_unavailable_learner()
        result = await learner.consume_feedback_stream("2026-01-01")
        assert result == 0

    @pytest.mark.asyncio
    async def test_get_matching_pattern_returns_none(self):
        """get_matching_pattern() returns None without raising when Redis is out."""
        learner = self._make_unavailable_learner()
        result = await learner.get_matching_pattern("any query", complexity="simple")
        assert result is None

    @pytest.mark.asyncio
    async def test_record_pattern_outcome_noop(self):
        """record_pattern_outcome() returns None without raising when Redis is out."""
        learner = self._make_unavailable_learner()
        # Must not raise — return value is None (no explicit return).
        result = await learner.record_pattern_outcome("somehash", success=True)
        assert result is None

    @pytest.mark.asyncio
    async def test_consolidate_returns_zero_counts(self):
        """consolidate() returns (0, 0) without raising when Redis is out."""
        learner = self._make_unavailable_learner()
        deduped, pruned = await learner.consolidate()
        assert deduped == 0
        assert pruned == 0

    @pytest.mark.asyncio
    async def test_distil_pattern_noop(self):
        """_distil_pattern() returns without raising when Redis is out."""
        learner = self._make_unavailable_learner()
        result = await learner._distil_pattern("simple", [], {})
        assert result is None

    @pytest.mark.asyncio
    async def test_load_cursors_marks_loaded_and_noop(self):
        """_load_cursors() marks _cursors_loaded=True and returns without raising."""
        learner = self._make_unavailable_learner()
        learner._cursors_loaded = False
        await learner._load_cursors()
        assert learner._cursors_loaded is True

    @pytest.mark.asyncio
    async def test_save_cursor_noop(self):
        """_save_cursor() returns without raising when Redis is out."""
        learner = self._make_unavailable_learner()
        result = await learner._save_cursor("rag:feedback:__global__:2026-01-01", "100-0")
        assert result is None


# ---------------------------------------------------------------------------
# (c) Once cached, _redis_unavailable short-circuits without re-calling factory
# ---------------------------------------------------------------------------


class TestUnavailableCaching:
    @pytest.mark.asyncio
    async def test_get_redis_does_not_retry_after_unavailable_set(self):
        """_get_redis() must not call get_redis_client a second time after the
        flag is set — the cached None is returned immediately."""
        learner = _make_learner_no_redis()
        call_count = 0

        async def _raise(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ConnectionRefusedError("Redis is down")

        with patch(
            "knowledge.search_components.retrieval_learner.get_redis_client",
            new=_raise,
        ):
            # First call: triggers the factory, sets flag, returns None.
            r1 = await learner._get_redis()
            # Second call: flag is set, must return None without touching factory.
            r2 = await learner._get_redis()

        assert r1 is None
        assert r2 is None
        # Factory must have been called exactly once.
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_unavailable_flag_set_before_first_call_prevents_factory(self):
        """When _redis_unavailable is pre-set, get_redis_client is never called."""
        learner = _make_learner_no_redis()
        learner._redis_unavailable = True

        with patch(
            "knowledge.search_components.retrieval_learner.get_redis_client",
            side_effect=AssertionError("should not be called"),
        ):
            result = await learner._get_redis()

        assert result is None


# ---------------------------------------------------------------------------
# Env-var timeout constant is present and positive
# ---------------------------------------------------------------------------


class TestTimeoutConstant:
    def test_redis_acquire_timeout_is_positive(self):
        """_REDIS_ACQUIRE_TIMEOUT must be a positive float (env-backed constant)."""
        assert isinstance(_REDIS_ACQUIRE_TIMEOUT, float)
        assert _REDIS_ACQUIRE_TIMEOUT > 0
