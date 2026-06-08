# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for autobot_shared.rate_limit.IPRateLimiter (#7271).

This module replaces the per-file rate-limit tests that used to live in
``autobot-backend/api/openai_compat_test.py`` (#6588). The shared helper
is exercised here once; both consumers (``openai_compat._oai_limiter`` and
``a2a._a2a_limiter``) get their behavior covered by these tests through
the helper.

Tests cover:
  * Below-limit: no raise
  * At-limit: HTTPException 429
  * Pipeline: ZREMRANGEBYSCORE + ZADD + ZCARD + EXPIRE in correct order
  * Pipeline: per-instance key prefix is honored
  * Redis unavailable: in-process fallback (degraded mode)
  * Pipeline error: in-process fallback (degraded mode)
  * Limit re-read from env each call (dynamic config)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from autobot_shared.rate_limit import IPRateLimiter


class _FakePipeline:
    """Minimal async-context-manager pipeline mock for redis.pipeline()."""

    def __init__(self, zcard_result: int) -> None:
        self._zcard_result = zcard_result
        self.commands: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    def zremrangebyscore(self, *args, **kwargs):
        self.commands.append(("zremrangebyscore", args, kwargs))
        return self

    def zadd(self, *args, **kwargs):
        self.commands.append(("zadd", args, kwargs))
        return self

    def zcard(self, *args, **kwargs):
        self.commands.append(("zcard", args, kwargs))
        return self

    def expire(self, *args, **kwargs):
        self.commands.append(("expire", args, kwargs))
        return self

    async def execute(self):
        # ZREMRANGEBYSCORE → int dropped, ZADD → int added,
        # ZCARD → int count, EXPIRE → bool. Index 2 is the count.
        return [0, 1, self._zcard_result, True]


def _fake_redis(zcard_result: int) -> MagicMock:
    fake = MagicMock()
    fake.pipeline = MagicMock(return_value=_FakePipeline(zcard_result))
    return fake


def _make_limiter(prefix: str = "ratelimit:test", default_limit: int = 60) -> IPRateLimiter:
    return IPRateLimiter(
        key_prefix=prefix,
        limit_env="UNIT_TEST_RATE_LIMIT",
        default_limit=default_limit,
        window_seconds=60,
    )


class TestIPRateLimiterRedisPath:
    """Issue #7271: shared limiter — Redis pipeline + 429 enforcement."""

    @pytest.mark.asyncio
    async def test_below_limit_does_not_raise(self) -> None:
        limiter = _make_limiter(default_limit=60)
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=_fake_redis(zcard_result=10)),
        ):
            await limiter.check_or_429("1.2.3.4")  # no exception

    @pytest.mark.asyncio
    async def test_at_limit_raises_429(self) -> None:
        limiter = _make_limiter(default_limit=5)
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=_fake_redis(zcard_result=6)),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await limiter.check_or_429("9.9.9.9")
            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_pipeline_uses_correct_key_and_ops(self) -> None:
        """Pipeline must build (key, 4 ops) in the documented order."""
        fake_pipe = _FakePipeline(zcard_result=1)
        fake_redis = MagicMock()
        fake_redis.pipeline = MagicMock(return_value=fake_pipe)

        limiter = _make_limiter(prefix="ratelimit:oai")
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=fake_redis),
        ):
            await limiter.check_or_429("203.0.113.1")

        op_names = [c[0] for c in fake_pipe.commands]
        assert op_names == ["zremrangebyscore", "zadd", "zcard", "expire"]

        # Each op uses the per-instance key prefix.
        for _, args, _ in fake_pipe.commands:
            assert args[0] == "ratelimit:oai:203.0.113.1"

    @pytest.mark.asyncio
    async def test_per_instance_prefix_keeps_buckets_independent(self) -> None:
        """Two limiters with different prefixes must keep keys separate."""
        oai_pipe = _FakePipeline(zcard_result=1)
        a2a_pipe = _FakePipeline(zcard_result=1)
        oai_redis = MagicMock(pipeline=MagicMock(return_value=oai_pipe))
        a2a_redis = MagicMock(pipeline=MagicMock(return_value=a2a_pipe))

        oai = _make_limiter(prefix="ratelimit:oai")
        a2a = _make_limiter(prefix="ratelimit:a2a")

        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=oai_redis),
        ):
            await oai.check_or_429("8.8.8.8")
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=a2a_redis),
        ):
            await a2a.check_or_429("8.8.8.8")

        assert oai_pipe.commands[0][1][0] == "ratelimit:oai:8.8.8.8"
        assert a2a_pipe.commands[0][1][0] == "ratelimit:a2a:8.8.8.8"


class TestIPRateLimiterFallback:
    """Issue #7271: shared limiter — in-process fallback paths."""

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_to_inprocess(self, caplog) -> None:
        """Redis None → fallback to per-process bucket (degraded mode)."""
        import logging

        limiter = _make_limiter(prefix="ratelimit:fb1", default_limit=60)
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            with caplog.at_level(logging.WARNING, logger="autobot_shared.rate_limit"):
                await limiter.check_or_429("8.8.8.8")
        assert "8.8.8.8" in limiter._inprocess_buckets
        assert any("Redis unavailable" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_pipeline_error_falls_back_to_inprocess(self, caplog):
        """Redis pipeline raises → fallback to per-process bucket."""
        import logging

        class _BrokenPipeline:
            async def __aenter__(self) -> None:
                raise RuntimeError("redis down mid-pipeline")

            async def __aexit__(self, *a):
                return False

        broken = MagicMock()
        broken.pipeline = MagicMock(return_value=_BrokenPipeline())

        limiter = _make_limiter(prefix="ratelimit:fb2", default_limit=60)
        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=broken),
        ):
            with caplog.at_level(logging.WARNING, logger="autobot_shared.rate_limit"):
                await limiter.check_or_429("4.4.4.4")
        assert "4.4.4.4" in limiter._inprocess_buckets
        assert any("pipeline failed" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_inprocess_at_limit_raises_429(self) -> None:
        """In-process fallback respects the limit too."""
        limiter = _make_limiter(prefix="ratelimit:fb3", default_limit=2)
        # Pre-seed bucket so the next call exceeds the limit.
        import time as _time

        now = _time.time()
        limiter._inprocess_buckets["7.7.7.7"] = [now, now]  # already at limit

        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await limiter.check_or_429("7.7.7.7")
            assert exc_info.value.status_code == 429


class TestIPRateLimiterConfig:
    """Issue #7271: limit is read from env each call (dynamic config)."""

    def test_limit_property_reads_env(self, monkeypatch) -> None:
        limiter = _make_limiter(default_limit=60)
        monkeypatch.setenv("UNIT_TEST_RATE_LIMIT", "120")
        assert limiter.limit == 120
        monkeypatch.setenv("UNIT_TEST_RATE_LIMIT", "5")
        assert limiter.limit == 5

    def test_limit_falls_back_to_default_when_env_unparseable(self, monkeypatch) -> None:
        limiter = _make_limiter(default_limit=60)
        monkeypatch.setenv("UNIT_TEST_RATE_LIMIT", "not-a-number")
        assert limiter.limit == 60

    def test_limit_uses_default_when_env_unset(self, monkeypatch) -> None:
        monkeypatch.delenv("UNIT_TEST_RATE_LIMIT", raising=False)
        limiter = _make_limiter(default_limit=60)
        assert limiter.limit == 60
