# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests — IntegrationRateLimiter and RateLimitState (Issue #4162)

All time-sensitive behaviour is tested via direct state manipulation so
there are no real sleeps.
"""

import asyncio
import time
from email.utils import formatdate

import pytest

from integrations.rate_limiter import IntegrationRateLimiter, RateLimitState

# ---------------------------------------------------------------------------
# RateLimitState: provider pause
# ---------------------------------------------------------------------------


def test_state_has_no_pause_by_default():
    assert RateLimitState().pending_wait(time.monotonic()) == 0.0


def test_state_retry_after_blocks():
    state = RateLimitState()
    now = time.monotonic()
    state.apply_retry_after(30.0, now)
    assert 28.0 < state.pending_wait(now + 1.0) <= 30.0


def test_state_keeps_the_longer_provider_pause():
    state = RateLimitState()
    now = time.monotonic()
    state.apply_retry_after(120.0, now)
    state.apply_retry_after(60.0, now)
    assert 118.0 < state.pending_wait(now + 1.0) <= 120.0


def test_state_retry_after_expires():
    state = RateLimitState()
    now = time.monotonic()
    state.apply_retry_after(10.0, now)
    assert state.pending_wait(now + 15.0) == 0.0


# ---------------------------------------------------------------------------
# IntegrationRateLimiter: window logic (delegated to LocalWindowCounter, #18087)
# ---------------------------------------------------------------------------


def test_limiter_blocks_when_minute_window_full():
    limiter = IntegrationRateLimiter(requests_per_minute=3, requests_per_hour=1000)
    for _ in range(3):
        limiter.record("tok")
    can, wait = limiter.check("tok")
    assert can is False
    assert 0.0 < wait <= 60.0


def test_limiter_blocks_when_hour_window_full():
    limiter = IntegrationRateLimiter(requests_per_minute=1000, requests_per_hour=3)
    for _ in range(3):
        limiter.record("tok")
    can, wait = limiter.check("tok")
    assert can is False
    assert 60.0 < wait <= 3600.0


def test_limiter_allows_after_minute_window_expires(monkeypatch):
    limiter = IntegrationRateLimiter(requests_per_minute=2, requests_per_hour=1000)
    real = time.time()
    monkeypatch.setattr("autobot_shared.rate_limiter_window.time.time", lambda: real - 65.0)
    limiter.record("tok")
    limiter.record("tok")
    monkeypatch.setattr("autobot_shared.rate_limiter_window.time.time", lambda: real)
    assert limiter.check("tok") == (True, 0.0)


def test_limiter_check_does_not_consume_a_slot():
    limiter = IntegrationRateLimiter(requests_per_minute=1, requests_per_hour=1000)
    assert limiter.check("tok")[0] is True
    assert limiter.check("tok")[0] is True


def test_limiter_provider_pause_wins_over_open_windows():
    limiter = IntegrationRateLimiter(requests_per_minute=1000, requests_per_hour=1000)
    limiter._get_state("tok").apply_retry_after(30.0, time.monotonic())
    can, wait = limiter.check("tok")
    assert can is False
    assert 28.0 < wait <= 30.0


# ---------------------------------------------------------------------------
# RateLimitState: GitHub header handling
# ---------------------------------------------------------------------------


def test_github_headers_zero_remaining_sets_retry_after():
    state = RateLimitState()
    mono, wall = time.monotonic(), time.time()
    state.apply_github_headers(
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(wall) + 60)},
        mono,
        wall,
    )
    assert 58.0 < state.pending_wait(mono) <= 61.0


def test_github_reset_epoch_through_the_entry_point_pauses_about_the_reset_delta():
    """#18087: the epoch is a wall-clock value; measured on the monotonic clock it paused ~1.7e9 s."""
    limiter = IntegrationRateLimiter(requests_per_minute=1000, requests_per_hour=5000)
    limiter.apply_response_headers(
        "tok",
        {"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": str(int(time.time()) + 60)},
        service="github",
    )
    can, wait = limiter.check("tok")
    assert can is False
    assert 58.0 < wait <= 61.0


def test_retry_after_http_date_is_a_wall_clock_delta():
    limiter = IntegrationRateLimiter(requests_per_minute=1000, requests_per_hour=5000)
    date = formatdate(time.time() + 45, usegmt=True)
    limiter.apply_response_headers("tok", {"Retry-After": date})
    can, wait = limiter.check("tok")
    assert can is False
    assert 43.0 < wait <= 46.0


def test_unparseable_retry_after_is_ignored():
    limiter = IntegrationRateLimiter(requests_per_minute=1000, requests_per_hour=5000)
    limiter.apply_response_headers("tok", {"Retry-After": "soon"})
    assert limiter.check("tok") == (True, 0.0)


def test_github_headers_nonzero_remaining_no_block():
    state = RateLimitState()
    now = time.monotonic()
    state.apply_github_headers(
        {"X-RateLimit-Remaining": "100", "X-RateLimit-Reset": str(int(time.time()) + 3600)},
        now,
        time.time(),
    )
    assert state.pending_wait(now) == 0.0


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
