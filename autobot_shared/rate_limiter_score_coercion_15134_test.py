# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Sorted-set scores reaching arithmetic are coerced, not assumed (#15134).

``get_retry_after_seconds`` subtracts a ``ZRANGEBYSCORE ... WITHSCORES`` score
from a timestamp. redis-py types the member/score pair loosely, so a checker
that can see the real package rejects the subtraction -- and the rejection is
pointing at something true: nothing in the client contract guarantees the
score arrives already numeric, and a string one would raise ``TypeError``
inside the very helper whose job is to answer "how long until you may retry".

These live in their own module because ``rate_limiter_test.py`` sits exactly on
its recorded 618-line ceiling, which the size ratchet enforces in both
directions; appending there would fail the gate.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, patch

import pytest

from autobot_shared.rate_limiter import RateLimiter

_PATCH_TARGET = "autobot_shared.rate_limiter.get_async_redis_client"

#: Every score representation a Redis client may hand back for the same instant.
#: Empty would make the parametrised assertions below vacuous, so it is asserted.
SCORE_SPELLINGS = ("float", "str", "bytes")

assert SCORE_SPELLINGS, "score spellings must not be empty -- an empty case asserts nothing"


def _redis_reporting(oldest_offset: float, score_spelling: str) -> AsyncMock:
    """A client whose window is full and whose oldest entry is *oldest_offset* old."""
    oldest = time.time() - oldest_offset
    raw: float | str | bytes = oldest
    if score_spelling == "str":
        raw = str(oldest)
    elif score_spelling == "bytes":
        raw = str(oldest).encode("utf-8")

    redis = AsyncMock()
    # Above the per-minute allowance and below the per-hour one, so only the
    # minute branch contributes and the expected value is unambiguous.
    redis.zcount = AsyncMock(return_value=10)
    redis.zrangebyscore = AsyncMock(return_value=[("member", raw)])
    return redis


@pytest.mark.asyncio
@pytest.mark.parametrize("score_spelling", SCORE_SPELLINGS)
async def test_retry_after_is_computed_whatever_spelling_the_score_arrives_in(score_spelling):
    """The same instant yields the same answer whether the score is a float or a string."""
    limiter = RateLimiter("t15134", requests_per_minute=1, requests_per_hour=1000)
    redis = _redis_reporting(oldest_offset=10.0, score_spelling=score_spelling)

    with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
        retry_after = await limiter.get_retry_after_seconds("caller")

    # 60s window, oldest entry 10s old -> just under 50s left, floored, +1 rounding.
    assert retry_after == 50


@pytest.mark.asyncio
async def test_retry_after_string_score_does_not_fall_into_the_error_path():
    """A string score must produce the real answer, not the swallowed-exception default.

    ``get_retry_after_seconds`` catches broadly and returns 0 on failure -- "no
    wait" -- so a ``TypeError`` from the subtraction does not surface as an
    error, it surfaces as a client being told to retry immediately while the
    limiter is still refusing it. Pinning the exact value is what tells the two
    apart.
    """
    limiter = RateLimiter("t15134", requests_per_minute=1, requests_per_hour=1000)
    redis = _redis_reporting(oldest_offset=45.0, score_spelling="str")

    with patch(_PATCH_TARGET, AsyncMock(return_value=redis)):
        assert await limiter.get_retry_after_seconds("caller") == 15
