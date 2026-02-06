# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Rate Limiting Middleware Tests

Tests for PasswordChangeRateLimiter - prevents brute force password change attempts.
Issue #635.
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
    from src.user_management.middleware.rate_limit import PasswordChangeRateLimiter

    user_id = uuid.uuid4()
    mock_redis.get = AsyncMock(return_value="2")  # 2 attempts

    with patch(
        "src.user_management.middleware.rate_limit.get_redis_client",
        return_value=mock_redis,
    ):
        limiter = PasswordChangeRateLimiter()
        is_allowed, remaining = await limiter.check_rate_limit(user_id)

    assert is_allowed is True
    assert remaining == 1  # 3 max - 2 current = 1 remaining


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_exceeded(mock_redis):
    """Rate limiter blocks when threshold exceeded."""
    from src.user_management.middleware.rate_limit import (
        PasswordChangeRateLimiter,
        RateLimitExceeded,
    )

    user_id = uuid.uuid4()
    mock_redis.get = AsyncMock(return_value="3")  # At max
    mock_redis.ttl = AsyncMock(return_value=1620)  # 27 minutes

    with patch(
        "src.user_management.middleware.rate_limit.get_redis_client",
        return_value=mock_redis,
    ):
        limiter = PasswordChangeRateLimiter()

        with pytest.raises(RateLimitExceeded) as exc_info:
            await limiter.check_rate_limit(user_id)

        assert "27 minutes" in str(exc_info.value)
