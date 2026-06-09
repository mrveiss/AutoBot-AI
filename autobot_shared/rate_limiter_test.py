# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the shared sliding-window rate limiter (Issue #6337).

All Redis interactions are mocked — no live Redis connection is required.
Tests cover the dual sliding-window logic (per-minute + per-hour), the
graceful-degradation path when Redis is unavailable, and the Retry-After
helper.

Pattern: patch ``autobot_shared.rate_limiter.get_async_redis_client`` so the
module-under-test sees a controlled AsyncMock instead of a real client.
"""

from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure autobot_shared.redis_client is importable even without a live stack
# ---------------------------------------------------------------------------


def _install_redis_stub() -> None:
    mod_name = "autobot_shared.redis_client"
    if mod_name not in sys.modules:
        stub = types.ModuleType(mod_name)
        stub.get_async_redis_client = AsyncMock(return_value=None)  # type: ignore[attr-defined]
        sys.modules[mod_name] = stub


_install_redis_stub()

# ---------------------------------------------------------------------------
# Ensure autobot_shared.ssot_config is importable
# ---------------------------------------------------------------------------


def _install_ssot_stub() -> None:
    mod_name = "autobot_shared.ssot_config"
    if mod_name not in sys.modules:
        stub = types.ModuleType(mod_name)
        # Provide integer rate-limit attributes so _get_tier_defaults() returns
        # the correct int values rather than MagicMock objects.
        cfg = MagicMock()
        cfg.rate_limit_anon_rpm = 20
        cfg.rate_limit_anon_rph = 500
        cfg.rate_limit_auth_rpm = 60
        cfg.rate_limit_auth_rph = 2000
        cfg.rate_limit_priv_rpm = 300
        cfg.rate_limit_priv_rph = 10000
        stub.config = cfg  # type: ignore[attr-defined]
        sys.modules[mod_name] = stub


_install_ssot_stub()

from autobot_shared.rate_limiter import RateLimiter  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_PATCH_TARGET = "autobot_shared.rate_limiter.get_async_redis_client"


def _make_redis(*, minute_count: int = 0, hour_count: int = 0) -> AsyncMock:
    """Return an AsyncMock Redis client that reports given window counts.

    ``zcount`` is used for both minute and hour windows; we distinguish by
    the cutoff range. For simplicity, the mock always returns *minute_count*
    for the first ``zcount`` call and *hour_count* for the second.

    Note: ``record()`` calls ``pipe.zadd/zremrangebyscore/expire`` WITHOUT
    ``await`` (they enqueue on the pipeline sync), so those are plain
    MagicMock while ``pipe.execute`` is AsyncMock.
    """
    redis = AsyncMock()

    call_counts: dict[str, int] = {"zcount": 0}

    async def _zcount(key, min_score, max_score):
        call_counts["zcount"] += 1
        # First call → minute window; second call → hour window
        if call_counts["zcount"] == 1:
            return minute_count
        return hour_count

    redis.zcount = _zcount  # type: ignore[assignment]

    # pipeline used by record(): zadd/zremrangebyscore/expire are sync calls
    # on a pipeline object; only execute() is awaited.
    pipe = MagicMock()
    pipe.zadd = MagicMock()
    pipe.zremrangebyscore = MagicMock()
    pipe.expire = MagicMock()
    pipe.execute = AsyncMock(return_value=[1, 1, True])
    redis.pipeline = MagicMock(return_value=pipe)

    return redis


def _limiter(rpm: int = 5, rph: int = 20) -> RateLimiter:
    """Return a RateLimiter with known small limits."""
    return RateLimiter(
        scope_prefix="test",
        default_tier="authenticated",
        requests_per_minute=rpm,
        requests_per_hour=rph,
    )


# ---------------------------------------------------------------------------
# Tests — RateLimiter constructor
# ---------------------------------------------------------------------------


class TestRateLimiterConstructor:
    def test_valid_tier_accepted(self) -> None:
        lim = RateLimiter(scope_prefix="x", default_tier="authenticated")
        assert lim._rpm > 0
        assert lim._rph > 0

    def test_all_tiers_accepted(self) -> None:
        for tier in ("anonymous", "authenticated", "privileged"):
            lim = RateLimiter(scope_prefix="x", default_tier=tier)
            assert lim._rpm > 0

    def test_invalid_tier_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown tier"):
            RateLimiter(scope_prefix="x", default_tier="superuser")

    def test_rpm_override_applied(self) -> None:
        lim = RateLimiter(scope_prefix="x", requests_per_minute=7)
        assert lim._rpm == 7

    def test_rph_override_applied(self) -> None:
        lim = RateLimiter(scope_prefix="x", requests_per_hour=100)
        assert lim._rph == 100

    def test_redis_key_format(self) -> None:
        lim = RateLimiter(scope_prefix="user")
        assert lim._redis_key("abc", "hour") == "autobot:rl:user:abc:hour"
        assert lim._redis_key("abc", "minute") == "autobot:rl:user:abc:minute"


# ---------------------------------------------------------------------------
# Tests — is_allowed
# ---------------------------------------------------------------------------


class TestIsAllowed:
    def test_first_request_allowed(self) -> None:
        """Fresh key with zero counts → request must be allowed."""
        lim = _limiter(rpm=5, rph=20)
        redis = _make_redis(minute_count=0, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.is_allowed("user1"))
        assert result is True

    def test_allowed_when_at_limit_minus_one(self) -> None:
        """count == limit - 1 → still allowed."""
        lim = _limiter(rpm=5, rph=20)
        redis = _make_redis(minute_count=4, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.is_allowed("user1"))
        assert result is True

    def test_denied_when_per_minute_limit_reached(self) -> None:
        """minute_count >= rpm → denied."""
        lim = _limiter(rpm=5, rph=20)
        redis = _make_redis(minute_count=5, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.is_allowed("user1"))
        assert result is False

    def test_denied_when_per_minute_limit_exceeded(self) -> None:
        """minute_count > rpm → denied."""
        lim = _limiter(rpm=5, rph=20)
        redis = _make_redis(minute_count=10, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.is_allowed("user1"))
        assert result is False

    def test_denied_when_per_hour_limit_reached(self) -> None:
        """hour_count >= rph → denied even if minute window has capacity."""
        lim = _limiter(rpm=5, rph=20)
        redis = _make_redis(minute_count=0, hour_count=20)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.is_allowed("user1"))
        assert result is False

    def test_per_call_override_rpm_respected(self) -> None:
        """Explicit rpm override tightens the minute limit."""
        lim = _limiter(rpm=100, rph=1000)
        redis = _make_redis(minute_count=3, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            # Override to 3 → count == limit → denied
            result = asyncio.run(lim.is_allowed("user1", requests_per_minute=3))
        assert result is False

    def test_per_call_override_rph_respected(self) -> None:
        """Explicit rph override tightens the hour limit."""
        lim = _limiter(rpm=100, rph=1000)
        redis = _make_redis(minute_count=0, hour_count=10)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.is_allowed("user1", requests_per_hour=10))
        assert result is False

    def test_redis_unavailable_allows_request(self) -> None:
        """When Redis is None, is_allowed must return True (fail-open)."""
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            result = asyncio.run(lim.is_allowed("user1"))
        assert result is True

    def test_redis_exception_allows_request(self) -> None:
        """When Redis raises, is_allowed must still return True (fail-open)."""

        async def _raise(*a, **kw) -> None:
            raise ConnectionError("Redis unreachable")

        lim = _limiter()
        with patch(_PATCH_TARGET, _raise):
            result = asyncio.run(lim.is_allowed("user1"))
        assert result is True


# ---------------------------------------------------------------------------
# Tests — record
# ---------------------------------------------------------------------------


class TestRecord:
    def test_record_calls_pipeline_execute(self) -> None:
        """record() must use a pipeline and execute it."""
        lim = _limiter()
        redis = _make_redis()
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            asyncio.run(lim.record("user1"))
        redis.pipeline.return_value.execute.assert_called_once()

    def test_record_no_op_when_redis_none(self) -> None:
        """record() must not raise when Redis is unavailable."""
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            asyncio.run(lim.record("user1"))  # must not raise

    def test_record_no_op_on_redis_exception(self) -> None:
        """record() must swallow Redis errors gracefully."""
        redis = _make_redis()
        redis.pipeline.return_value.execute = AsyncMock(side_effect=ConnectionError("down"))
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            asyncio.run(lim.record("user1"))  # must not raise


# ---------------------------------------------------------------------------
# Tests — acquire (combined check + record)
# ---------------------------------------------------------------------------


class TestAcquire:
    def test_acquire_returns_true_and_records_when_allowed(self) -> None:
        """acquire() returns True and calls pipeline.execute() when under limit."""
        lim = _limiter(rpm=5, rph=20)
        redis = _make_redis(minute_count=0, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.acquire("user1"))
        assert result is True
        redis.pipeline.return_value.execute.assert_called_once()

    def test_acquire_returns_false_and_does_not_record_when_denied(self) -> None:
        """acquire() returns False and does NOT record when over limit."""
        lim = _limiter(rpm=5, rph=20)
        redis = _make_redis(minute_count=5, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.acquire("user1"))
        assert result is False
        redis.pipeline.return_value.execute.assert_not_called()

    def test_acquire_redis_unavailable_returns_true(self) -> None:
        """acquire() returns True (fail-open) when Redis is None."""
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            result = asyncio.run(lim.acquire("user1"))
        assert result is True


# ---------------------------------------------------------------------------
# Tests — get_retry_after_seconds
# ---------------------------------------------------------------------------


class TestGetRetryAfterSeconds:
    def _make_redis_for_retry(
        self,
        *,
        minute_count: int,
        hour_count: int,
        oldest_ts_offset: float = 10.0,
    ) -> AsyncMock:
        """Return a Redis mock suitable for get_retry_after_seconds tests.

        ``oldest_ts_offset`` controls how many seconds ago the oldest entry
        in the window was recorded.
        """
        import time

        redis = AsyncMock()
        now = time.time()
        oldest_ts = now - oldest_ts_offset

        async def _zcount(key, min_score, max_score):
            # Determine which window is being queried by the cutoff distance
            distance = now - float(min_score) if min_score != "-inf" else 99999
            if distance <= 61:  # minute window (cutoff = now - 60)
                return minute_count
            return hour_count

        redis.zcount = _zcount  # type: ignore[assignment]

        async def _zrangebyscore(key, min_score, max_score, start=0, num=1, withscores=False):
            return [(str(oldest_ts).encode(), oldest_ts)]

        redis.zrangebyscore = _zrangebyscore  # type: ignore[assignment]
        return redis

    def test_returns_small_value_when_under_both_limits(self) -> None:
        """No active limit → wait is 0.0; implementation returns max(0, int(0)+1)=1.

        The +1 safe-rounding means the function always returns at least 1
        even when no limit is active.  Callers should treat a return value
        of ≤1 as "no meaningful backoff required".
        """
        lim = _limiter(rpm=5, rph=20)
        redis = self._make_redis_for_retry(minute_count=0, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.get_retry_after_seconds("user1"))
        # wait=0.0 → max(0, 0+1)=1; no limit is active so result is small
        assert result <= 1

    def test_returns_positive_when_minute_limit_active(self) -> None:
        """Over minute limit → retry-after must be > 0."""
        lim = _limiter(rpm=5, rph=20)
        # oldest entry was 10 s ago; minute window = 60 s → ~50 s remaining
        redis = self._make_redis_for_retry(minute_count=5, hour_count=0, oldest_ts_offset=10.0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.get_retry_after_seconds("user1"))
        assert result > 0

    def test_returns_positive_when_hour_limit_active(self) -> None:
        """Over hour limit → retry-after must be > 0."""
        lim = _limiter(rpm=5, rph=20)
        # oldest entry was 100 s ago; hour window = 3600 s → ~3500 s remaining
        redis = self._make_redis_for_retry(minute_count=0, hour_count=20, oldest_ts_offset=100.0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.get_retry_after_seconds("user1"))
        assert result > 0

    def test_returns_zero_when_redis_unavailable(self) -> None:
        """Redis None → retry-after returns 0 (safest default)."""
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            result = asyncio.run(lim.get_retry_after_seconds("user1"))
        assert result == 0

    def test_returns_zero_on_redis_exception(self) -> None:
        """Redis error → retry-after returns 0 (fail-safe)."""

        async def _raise(*a, **kw) -> None:
            raise ConnectionError("Redis unreachable")

        lim = _limiter()
        with patch(_PATCH_TARGET, _raise):
            result = asyncio.run(lim.get_retry_after_seconds("user1"))
        assert result == 0

    def test_return_type_is_int(self) -> None:
        """get_retry_after_seconds must always return an int."""
        lim = _limiter(rpm=5, rph=20)
        redis = self._make_redis_for_retry(minute_count=5, hour_count=0)
        with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
            result = asyncio.run(lim.get_retry_after_seconds("user1"))
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Tests — window count helper
# ---------------------------------------------------------------------------


class TestWindowCount:
    def test_window_count_uses_zcount(self) -> None:
        """_window_count must query Redis with the correct cutoff."""
        import time

        lim = _limiter()
        redis = AsyncMock()
        redis.zcount = AsyncMock(return_value=3)

        result = asyncio.run(lim._window_count(redis, "user1", "minute", time.time(), 60))
        assert result == 3
        redis.zcount.assert_called_once()

    def test_window_count_returns_int(self) -> None:
        """_window_count must return an int regardless of Redis response type."""
        import time

        lim = _limiter()
        redis = AsyncMock()
        redis.zcount = AsyncMock(return_value="7")  # string from some Redis clients

        result = asyncio.run(lim._window_count(redis, "user1", "hour", time.time(), 3600))
        assert result == 7
        assert isinstance(result, int)


# ---------------------------------------------------------------------------
# Tests — graceful degradation (comprehensive)
# ---------------------------------------------------------------------------


class TestGracefulDegradation:
    """All public methods must allow/return-safe when Redis is unavailable."""

    def test_is_allowed_none_redis(self) -> None:
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            assert asyncio.run(lim.is_allowed("x")) is True

    def test_record_none_redis_no_raise(self) -> None:
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            asyncio.run(lim.record("x"))  # must not raise

    def test_acquire_none_redis(self) -> None:
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            assert asyncio.run(lim.acquire("x")) is True

    def test_get_retry_after_none_redis(self) -> None:
        lim = _limiter()
        with patch(_PATCH_TARGET, AsyncMock(return_value=None)):
            assert asyncio.run(lim.get_retry_after_seconds("x")) == 0
