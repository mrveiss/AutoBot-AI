# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests for openai_compat._check_oai_rate_limit (Issue #6588).

Background: rate-limit state used to live in a per-process dict, so under
``backend_workers: 4`` the effective limit was 4× the configured value
(each worker tracked its own state). #6588 migrates the state to a Redis
sorted-set so all workers share enforcement.

Tests pin:
  * Redis path: ZREMRANGEBYSCORE + ZADD + ZCARD + EXPIRE pipelined
  * Below-limit: no 429
  * At-limit: HTTPException 429
  * Redis unavailable: falls back to in-process bucket (degraded mode)
  * Pipeline error: falls back to in-process bucket (degraded mode)
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api import openai_compat


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


class TestCheckOAIRateLimit:
    """Issue #6588: Redis-backed sliding window."""

    @pytest.mark.asyncio
    async def test_below_limit_does_not_raise(self):
        with (
            patch.object(
                openai_compat,
                "_OAI_RATE_LIMIT",
                60,
            ),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=_fake_redis(zcard_result=10)),
            ),
        ):
            # Under the limit, no exception.
            await openai_compat._check_oai_rate_limit("1.2.3.4")

    @pytest.mark.asyncio
    async def test_at_limit_raises_429(self):
        with (
            patch.object(
                openai_compat,
                "_OAI_RATE_LIMIT",
                5,
            ),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=_fake_redis(zcard_result=6)),
            ),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await openai_compat._check_oai_rate_limit("9.9.9.9")
            assert exc_info.value.status_code == 429
            assert "Rate limit exceeded" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_pipeline_uses_correct_key_and_ops(self):
        """Verify the pipeline is built with the right key + 4 ops."""
        fake_pipe = _FakePipeline(zcard_result=1)
        fake_redis = MagicMock()
        fake_redis.pipeline = MagicMock(return_value=fake_pipe)

        with patch(
            "autobot_shared.redis_client.get_async_redis_client",
            new=AsyncMock(return_value=fake_redis),
        ):
            await openai_compat._check_oai_rate_limit("203.0.113.1")

        # All 4 ops were enqueued in order.
        op_names = [c[0] for c in fake_pipe.commands]
        assert op_names == ["zremrangebyscore", "zadd", "zcard", "expire"]

        # Each op uses the per-IP key.
        for _, args, _ in fake_pipe.commands:
            assert args[0] == "ratelimit:oai:203.0.113.1"

    @pytest.mark.asyncio
    async def test_redis_unavailable_falls_back_to_inprocess(self, caplog):
        """Redis None → fallback to per-process bucket (degraded mode)."""
        import logging

        # Reset in-process bucket for clean state.
        openai_compat._oai_rate_buckets.clear()

        with (
            patch.object(openai_compat, "_OAI_RATE_LIMIT", 60),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=None),
            ),
        ):
            with caplog.at_level(logging.WARNING, logger="api.openai_compat"):
                await openai_compat._check_oai_rate_limit("8.8.8.8")
        # Bucket got the IP recorded in fallback path.
        assert "8.8.8.8" in openai_compat._oai_rate_buckets
        assert any("Redis unavailable" in r.getMessage() for r in caplog.records)

    @pytest.mark.asyncio
    async def test_pipeline_error_falls_back_to_inprocess(self, caplog):
        """Redis pipeline raises → fallback to per-process bucket."""
        import logging

        openai_compat._oai_rate_buckets.clear()

        class _BrokenPipeline:
            async def __aenter__(self):
                raise RuntimeError("redis down mid-pipeline")

            async def __aexit__(self, *a):
                return False

        broken = MagicMock()
        broken.pipeline = MagicMock(return_value=_BrokenPipeline())

        with (
            patch.object(openai_compat, "_OAI_RATE_LIMIT", 60),
            patch(
                "autobot_shared.redis_client.get_async_redis_client",
                new=AsyncMock(return_value=broken),
            ),
        ):
            with caplog.at_level(logging.WARNING, logger="api.openai_compat"):
                await openai_compat._check_oai_rate_limit("4.4.4.4")
        assert "4.4.4.4" in openai_compat._oai_rate_buckets
        assert any("pipeline failed" in r.getMessage() for r in caplog.records)
