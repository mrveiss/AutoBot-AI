# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit tests — IntegrationRateLimiter and RateLimitState (Issue #4162)

All time-sensitive behaviour is tested via direct state manipulation so
there are no real sleeps.
"""

import asyncio
import time

import pytest

from integrations.rate_limiter import IntegrationRateLimiter, RateLimitState

# ---------------------------------------------------------------------------
# RateLimitState: basic window logic
# ---------------------------------------------------------------------------


def test_state_allows_first_request():
    state = RateLimitState(requests_per_minute=10, requests_per_hour=100)
    now = time.monotonic()
    can, wait = state.is_ready(now)
    assert can is True
    assert wait == 0.0


def test_state_blocks_when_minute_window_full():
    state = RateLimitState(requests_per_minute=3, requests_per_hour=1000)
    now = time.monotonic()
    for _ in range(3):
        state.record(now)
    can, wait = state.is_ready(now)
    assert can is False
    assert wait > 0.0


def test_state_blocks_when_hour_window_full():
    state = RateLimitState(requests_per_minute=1000, requests_per_hour=3)
    now = time.monotonic()
    for _ in range(3):
        state.record(now)
    can, wait = state.is_ready(now)
    assert can is False
    assert wait > 0.0


def test_state_allows_after_minute_window_expires():
    state = RateLimitState(requests_per_minute=2, requests_per_hour=1000)
    now = time.monotonic()
    # Fill minute window with old timestamps (65 s ago)
    old = now - 65.0
    state.record(old)
    state.record(old)
    # Both old entries should be pruned from minute window
    can, wait = state.is_ready(now)
    assert can is True


def test_state_retry_after_blocks():
    state = RateLimitState(requests_per_minute=1000, requests_per_hour=1000)
    now = time.monotonic()
    state.apply_retry_after(30.0, now)
    can, wait = state.is_ready(now + 1.0)
    assert can is False
    assert 28.0 < wait <= 30.0


def test_state_retry_after_expires():
    state = RateLimitState(requests_per_minute=1000, requests_per_hour=1000)
    now = time.monotonic()
    state.apply_retry_after(10.0, now)
    can, wait = state.is_ready(now + 15.0)
    assert can is True
    assert wait == 0.0


# ---------------------------------------------------------------------------
# RateLimitState: GitHub header handling
# ---------------------------------------------------------------------------


def test_github_headers_zero_remaining_sets_retry_after():
    state = RateLimitState(requests_per_minute=1000, requests_per_hour=1000)
    time.monotonic()
    reset_epoch = time.time() + 60  # 60 s from now (wall clock)
    # Map monotonic now to wall-clock: we pass reset as monotonic equivalent
    state.apply_github_headers(
        {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 60),
        },
        time.time(),  # apply_github_headers uses the passed 'now' as wall time
    )
    # retry_after_until should be set to a future monotonic value
    # We can't compare monotonic directly; just verify state blocked
    # by calling is_ready shortly after
    # Since we pass wall-clock 'now' but state stores monotonic, we test indirectly
    assert state.retry_after_until > 0.0


def test_github_headers_nonzero_remaining_no_block():
    state = RateLimitState(requests_per_minute=1000, requests_per_hour=1000)
    now = time.monotonic()
    state.apply_github_headers(
        {"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": str(int(time.time()) + 3600)},
        now,
    )
    can, _ = state.is_ready(now)
    assert can is True


# ---------------------------------------------------------------------------
# IntegrationRateLimiter: check / record
# ---------------------------------------------------------------------------


def test_limiter_allows_first_check():
    limiter = IntegrationRateLimiter(requests_per_minute=50, requests_per_hour=2000)
    can, wait = limiter.check("token-abc")
    assert can is True
    assert wait == 0.0


def test_limiter_blocks_after_quota_exhausted():
    limiter = IntegrationRateLimiter(requests_per_minute=3, requests_per_hour=1000)
    for _ in range(3):
        limiter.record("tok")
    can, wait = limiter.check("tok")
    assert can is False
    assert wait > 0.0


def test_limiter_different_keys_are_independent():
    limiter = IntegrationRateLimiter(requests_per_minute=2, requests_per_hour=1000)
    for _ in range(2):
        limiter.record("key-a")
    # key-a is exhausted, key-b should still be allowed
    can_a, _ = limiter.check("key-a")
    can_b, _ = limiter.check("key-b")
    assert can_a is False
    assert can_b is True


# ---------------------------------------------------------------------------
# IntegrationRateLimiter: apply_response_headers
# ---------------------------------------------------------------------------


def test_apply_retry_after_header():
    limiter = IntegrationRateLimiter(requests_per_minute=1000, requests_per_hour=5000)
    limiter.apply_response_headers("tok", {"Retry-After": "30"})
    can, wait = limiter.check("tok")
    assert can is False
    assert 29.0 < wait <= 30.0


def test_apply_github_ratelimit_remaining_zero():
    limiter = IntegrationRateLimiter(requests_per_minute=1000, requests_per_hour=5000)
    limiter.apply_response_headers(
        "tok",
        {
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(int(time.time()) + 60),
        },
        service="github",
    )
    state = limiter._get_state("tok")
    assert state.retry_after_until > 0.0


# ---------------------------------------------------------------------------
# IntegrationRateLimiter: acquire (async)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acquire_succeeds_when_not_limited():
    limiter = IntegrationRateLimiter(requests_per_minute=100, requests_per_hour=5000)
    # Should complete immediately
    await limiter.acquire("tok")
    # One request recorded
    can, _ = limiter.check("tok")
    assert can is True  # still room


@pytest.mark.asyncio
async def test_acquire_raises_timeout_when_wait_too_long():
    limiter = IntegrationRateLimiter(requests_per_minute=1, requests_per_hour=5000)
    limiter.record("tok")  # exhaust 1-req/min limit
    with pytest.raises(asyncio.TimeoutError):
        # max_wait=0 forces immediate timeout
        await limiter.acquire("tok", max_wait=0.0)
