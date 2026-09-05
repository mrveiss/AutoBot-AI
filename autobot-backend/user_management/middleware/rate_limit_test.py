# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Rate Limiting Middleware Tests

Tests for PasswordChangeRateLimiter - prevents brute force password change attempts.
Issues #635, #15743.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def mock_redis():
    """Mock Redis client for rate limiting."""
    mock = AsyncMock()
    mock.get = AsyncMock(return_value=None)
    mock.incr = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.ttl = AsyncMock(return_value=1800)
    mock.delete = AsyncMock(return_value=1)
    return mock


@pytest.mark.asyncio
async def test_check_rate_limit_allows_under_threshold(mock_redis):
    """Rate limiter allows requests under threshold."""
    from user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.get = AsyncMock(return_value="2")  # 2 attempts

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()
        is_allowed, remaining = await limiter.check_rate_limit(user_id)

    assert is_allowed is True
    assert remaining == 1  # 3 max - 2 current = 1 remaining


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_exceeded(mock_redis):
    """Rate limiter blocks when threshold exceeded."""
    from user_management.middleware.rate_limit import (
        PasswordChangeRateLimiter,
        RateLimitExceeded,
    )

    user_id = uuid.uuid4()
    mock_redis.get = AsyncMock(return_value="3")  # At max
    mock_redis.ttl = AsyncMock(return_value=1620)  # 27 minutes

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()

        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_rate_limit(user_id)

        assert "27 minutes" in str(exc_info.value)


@pytest.mark.asyncio
async def test_record_attempt_increments_on_failure(mock_redis):
    """Recording failed attempt increments counter."""
    from user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.incr = AsyncMock(return_value=2)
    mock_redis.expire = AsyncMock()

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()
        await limiter.record_attempt(user_id, success=False)

    key = f"password_change_attempts:{user_id}"
    mock_redis.incr.assert_called_once_with(key)
    mock_redis.expire.assert_called_once_with(key, 1800)


@pytest.mark.asyncio
async def test_record_attempt_clears_on_success(mock_redis):
    """Recording successful attempt clears counter."""
    from user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.delete = AsyncMock(return_value=1)

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()
        await limiter.record_attempt(user_id, success=True)

    key = f"password_change_attempts:{user_id}"
    mock_redis.delete.assert_called_once_with(key)


# ---------------------------------------------------------------------------
# Test: Per-Caller Keying (#15743)
#
# A target-only key constrains repeated attempts against one victim but not
# a caller walking many different target ids (the admin-reset path, where
# actor != target). These prove the caller's own key is also enforced.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_rate_limit_self_service_checks_single_key(mock_redis):
    """Self-service (actor == target) checks only the target key -- no
    redundant second lookup."""
    from user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.get = AsyncMock(return_value="1")

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()
        await limiter.check_rate_limit(user_id, actor_id=user_id)

    mock_redis.get.assert_called_once_with(f"password_change_attempts:{user_id}")


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_actor_walking_many_targets(mock_redis):
    """A caller's own counter trips even though the target it is currently
    pointed at is fresh -- closing the enumeration path a target-only key
    left open."""
    from user_management.middleware.rate_limit import (
        PasswordChangeRateLimiter,
        RateLimitExceeded,
    )

    target_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    actor_key = f"password_change_attempts:by-caller:{actor_id}"

    async def fake_get(key):
        return "3" if key == actor_key else None

    mock_redis.get = AsyncMock(side_effect=fake_get)
    mock_redis.ttl = AsyncMock(return_value=900)

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()

        with pytest.raises(RateLimitExceeded):
            await limiter.check_rate_limit(target_id, actor_id=actor_id)


@pytest.mark.asyncio
async def test_record_attempt_increments_both_keys_when_actor_differs(mock_redis):
    """An admin-reset (actor != target) increments both the target's and the
    caller's counters on a failed attempt."""
    from user_management.middleware.rate_limit import PasswordChangeRateLimiter

    target_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()
        await limiter.record_attempt(target_id, success=False, actor_id=actor_id)

    target_key = f"password_change_attempts:{target_id}"
    actor_key = f"password_change_attempts:by-caller:{actor_id}"
    assert mock_redis.incr.call_count == 2
    mock_redis.incr.assert_any_call(target_key)
    mock_redis.incr.assert_any_call(actor_key)


@pytest.mark.asyncio
async def test_record_attempt_clears_both_keys_when_actor_differs(mock_redis):
    """A successful admin-reset clears both the target's and the caller's
    counters."""
    from user_management.middleware.rate_limit import PasswordChangeRateLimiter

    target_id = uuid.uuid4()
    actor_id = uuid.uuid4()
    mock_redis.delete = AsyncMock(return_value=1)

    with patch(
        "user_management.middleware.rate_limit.get_async_redis_client",
        new=AsyncMock(return_value=mock_redis),
    ):
        limiter = PasswordChangeRateLimiter()
        await limiter.record_attempt(target_id, success=True, actor_id=actor_id)

    target_key = f"password_change_attempts:{target_id}"
    actor_key = f"password_change_attempts:by-caller:{actor_id}"
    assert mock_redis.delete.call_count == 2
    mock_redis.delete.assert_any_call(target_key)
    mock_redis.delete.assert_any_call(actor_key)
