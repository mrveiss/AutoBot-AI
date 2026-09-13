# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for GH#8502 rate-limit backoff / auto-resume module."""

from __future__ import annotations

import pytest

from llm_shared.models import LLMResponse
from llm_shared.optimization.rate_limiter import RateLimitError
from llm_shared.rate_limit_backoff import extract_rate_limit_info, raise_if_rate_limited


def _resp(error: str | None, provider: str = "openai", metadata: dict | None = None) -> LLMResponse:
    return LLMResponse(
        content="",
        model="gpt-4",
        provider=provider,
        processing_time=0.0,
        error=error,
        provider_metadata=metadata or {},
    )


# ---------------------------------------------------------------------------
# extract_rate_limit_info
# ---------------------------------------------------------------------------


class TestExtractRateLimitInfo:
    def test_no_error_returns_false(self):
        is_rl, retry_after = extract_rate_limit_info(_resp(None))
        assert not is_rl
        assert retry_after is None

    def test_unrelated_error_returns_false(self):
        is_rl, _ = extract_rate_limit_info(_resp("connection refused"))
        assert not is_rl

    @pytest.mark.parametrize(
        "msg",
        [
            "RateLimitError: too many requests",
            "429 Too Many Requests",
            "quota exceeded for this project",
            "resource_exhausted: quota",
            "requests per minute limit reached",
            "throttling applied by provider",
        ],
    )
    def test_known_patterns_detected(self, msg):
        is_rl, _ = extract_rate_limit_info(_resp(msg))
        assert is_rl

    def test_retry_after_parsed_from_error_string(self):
        is_rl, retry_after = extract_rate_limit_info(_resp("rate limit hit, retry after: 30 seconds"))
        assert is_rl
        assert retry_after == 30.0

    def test_retry_after_from_provider_metadata(self):
        is_rl, retry_after = extract_rate_limit_info(_resp("rate limit", metadata={"retry_after": "45"}))
        assert is_rl
        assert retry_after == 45.0

    def test_reset_timestamp_converted_to_delta(self, monkeypatch):
        import time as _time

        fake_now = 1_000_000.0
        monkeypatch.setattr(_time, "time", lambda: fake_now)
        future_epoch = fake_now + 60.0
        is_rl, retry_after = extract_rate_limit_info(
            _resp("429 rate limit", metadata={"x-ratelimit-reset": str(future_epoch)})
        )
        assert is_rl
        assert abs(retry_after - 60.0) < 1.0


# ---------------------------------------------------------------------------
# raise_if_rate_limited
# ---------------------------------------------------------------------------


class TestRaiseIfRateLimited:
    def test_ok_response_does_not_raise(self):
        raise_if_rate_limited(_resp(None))  # must not raise

    def test_rate_limit_response_raises(self):
        with pytest.raises(RateLimitError) as exc_info:
            raise_if_rate_limited(_resp("429 rate limit exceeded"))
        assert "openai" in str(exc_info.value)

    def test_raised_error_carries_retry_after(self):
        with pytest.raises(RateLimitError) as exc_info:
            raise_if_rate_limited(_resp("rate limit, retry after: 15"))
        assert exc_info.value.retry_after == 15.0

    def test_raised_error_carries_provider(self):
        with pytest.raises(RateLimitError) as exc_info:
            raise_if_rate_limited(_resp("429", provider="anthropic"))
        assert exc_info.value.provider == "anthropic"


# ---------------------------------------------------------------------------
# _persist_headroom_from_429 (#15026) — needs a running loop for
# fire_and_forget's asyncio.create_task, so these are async unlike the
# sync tests above (which exercise the RuntimeError-caught no-loop path).
# ---------------------------------------------------------------------------


class TestPersistHeadroomFrom429:
    @pytest.mark.asyncio
    async def test_429_records_zero_remaining(self):
        from llm_shared.quota_headroom import get_quota_headroom_store

        store = get_quota_headroom_store()
        store._local.clear()

        async def _raise():
            raise RuntimeError("Redis unavailable")

        store._get_redis = _raise  # type: ignore[method-assign]

        with pytest.raises(RateLimitError):
            raise_if_rate_limited(_resp("429 rate limit exceeded", provider="test-provider-429"))
        await _drain_fire_and_forget()

        entry = await store.get("test-provider-429", "requests")
        assert entry is not None
        assert entry.remaining == 0
        assert entry.source == "rate_limit_backoff:429"

    @pytest.mark.asyncio
    async def test_429_with_retry_after_sets_resets_at(self):
        import time as time_mod

        from llm_shared.quota_headroom import get_quota_headroom_store

        store = get_quota_headroom_store()
        store._local.clear()

        async def _raise():
            raise RuntimeError("Redis unavailable")

        store._get_redis = _raise  # type: ignore[method-assign]

        before = time_mod.time()
        with pytest.raises(RateLimitError):
            raise_if_rate_limited(_resp("rate limit, retry after: 30", provider="test-provider-retry"))
        await _drain_fire_and_forget()

        entry = await store.get("test-provider-retry", "requests")
        assert entry is not None
        assert entry.resets_at is not None
        assert entry.resets_at >= before + 30

    @pytest.mark.asyncio
    async def test_ok_response_persists_nothing(self):
        from llm_shared.quota_headroom import get_quota_headroom_store

        store = get_quota_headroom_store()
        store._local.clear()

        async def _raise():
            raise RuntimeError("Redis unavailable")

        store._get_redis = _raise  # type: ignore[method-assign]

        raise_if_rate_limited(_resp(None, provider="test-provider-ok"))
        await _drain_fire_and_forget()

        assert await store.get("test-provider-ok", "requests") is None

    @pytest.mark.asyncio
    async def test_no_provider_does_not_persist_or_raise_scheduling_error(self):
        with pytest.raises(RateLimitError):
            raise_if_rate_limited(_resp("429 rate limit exceeded", provider=""))
        await _drain_fire_and_forget()  # must not raise despite no provider to key on


async def _drain_fire_and_forget() -> None:
    """Yield control so a fire_and_forget-scheduled task gets to run and finish."""
    import asyncio

    await asyncio.sleep(0)
    await asyncio.sleep(0)
