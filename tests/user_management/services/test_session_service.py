# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Session Service Tests

Tests for session management and JWT token invalidation.
Issue #635.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from src.user_management.services.session_service import SessionService


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = AsyncMock()
    mock.sadd = AsyncMock(return_value=1)
    mock.expire = AsyncMock(return_value=True)
    mock.sismember = AsyncMock(return_value=False)
    return mock


@pytest.mark.asyncio
async def test_hash_token_creates_sha256():
    """Token hashing produces consistent SHA256 hashes."""
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    hash1 = SessionService.hash_token(token)
    hash2 = SessionService.hash_token(token)

    assert hash1 == hash2  # Deterministic
    assert len(hash1) == 64  # SHA256 hex length
    assert hash1.isalnum()  # Hex string


@pytest.mark.asyncio
async def test_add_token_to_blacklist(mock_redis):
    """Adding token to blacklist stores hash in Redis set."""
    user_id = uuid.uuid4()
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    with patch(
        "src.user_management.services.session_service.get_redis_client",
        return_value=mock_redis,
    ):
        service = SessionService()
        await service.add_token_to_blacklist(user_id, token, ttl=86400)

    expected_key = f"session:blacklist:{user_id}"
    expected_hash = SessionService.hash_token(token)

    mock_redis.sadd.assert_called_once_with(expected_key, expected_hash)
    mock_redis.expire.assert_called_once_with(expected_key, 86400)


@pytest.mark.asyncio
async def test_is_token_blacklisted(mock_redis):
    """Checking blacklisted token returns True when token exists in set."""
    user_id = uuid.uuid4()
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.test"

    # Mock sismember to return True (token is blacklisted)
    mock_redis.sismember = AsyncMock(return_value=True)

    with patch(
        "src.user_management.services.session_service.get_redis_client",
        return_value=mock_redis,
    ):
        service = SessionService()
        result = await service.is_token_blacklisted(user_id, token)

    expected_key = f"session:blacklist:{user_id}"
    expected_hash = SessionService.hash_token(token)

    mock_redis.sismember.assert_called_once_with(expected_key, expected_hash)
    assert result is True


@pytest.mark.asyncio
async def test_invalidate_user_sessions_except_current(mock_redis):
    """Invalidate all user sessions except the current token."""
    user_id = uuid.uuid4()
    current_token = "current.token.here"

    # Mock existing tokens in Redis
    existing_tokens = ["old.token.1", "old.token.2", current_token]
    mock_redis.smembers = AsyncMock(
        return_value={SessionService.hash_token(t) for t in existing_tokens}
    )
    mock_redis.sadd = AsyncMock()
    mock_redis.expire = AsyncMock()

    with patch(
        "src.user_management.services.session_service.get_redis_client",
        return_value=mock_redis,
    ):
        service = SessionService()
        count = await service.invalidate_user_sessions(
            user_id, except_token=current_token
        )

    # Should invalidate 2 tokens (excluding current)
    assert count == 2

    # Verify current token hash NOT added to blacklist
    current_hash = SessionService.hash_token(current_token)
    calls = mock_redis.sadd.call_args_list
    for call in calls:
        assert current_hash not in call[0][1]  # Not in added tokens
