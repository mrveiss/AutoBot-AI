# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for device JWT service (GH#9493)."""

import os
import time
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, decode_jwt
from services.device_jwt import (
    VALID_SCOPES,
    invalidate_device_cache,
    mint_device_jwt,
    validate_device_jwt,
)


@pytest.fixture
def mock_redis():
    """Mock Redis client for cache operations."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.setex = AsyncMock()
    redis.delete = AsyncMock()
    with patch("services.device_jwt.get_async_redis_client", return_value=redis):
        yield redis


@pytest.fixture
def mock_db_session():
    """Mock database session for device existence checks."""
    result = MagicMock()
    result.scalar_one_or_none = MagicMock()

    async def mock_get_async_session():
        session = AsyncMock()
        session.execute = AsyncMock(return_value=result)
        yield session

    with patch("user_management.database.get_async_session", side_effect=mock_get_async_session):
        yield result


@pytest.fixture
def test_device():
    """Test device data."""
    return {
        "device_id": str(uuid.uuid4()),
        "user_id": "test-user-123",
    }


@pytest.fixture(autouse=True)
def set_jwt_secret():
    """Set required JWT secret for all tests."""
    os.environ["DEVICE_JWT_SECRET"] = "test-secret-32-chars-minimum-len"
    yield
    os.environ.pop("DEVICE_JWT_SECRET", None)


class TestMintDeviceJWT:
    """Tests for mint_device_jwt function."""

    def test_mint_with_read_scope(self, test_device):
        """Should mint a valid JWT with read scope."""
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
            scope="read",
        )
        assert isinstance(token, str)
        assert len(token) > 0

        # Decode and verify claims
        claims = decode_jwt(token, os.environ["DEVICE_JWT_SECRET"])
        assert claims["device_id"] == test_device["device_id"]
        assert claims["user_id"] == test_device["user_id"]
        assert claims["scope"] == "read"
        assert claims["aud"] == "autobot:device"

    def test_mint_with_write_scope(self, test_device):
        """Should mint a valid JWT with write scope."""
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
            scope="write",
        )
        claims = decode_jwt(token, os.environ["DEVICE_JWT_SECRET"])
        assert claims["scope"] == "write"

    def test_mint_defaults_to_read_scope(self, test_device):
        """Should default to read scope when not specified (GH#9493 least-privilege)."""
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
        )
        claims = decode_jwt(token, os.environ["DEVICE_JWT_SECRET"])
        assert claims["scope"] == "read"

    def test_mint_rejects_invalid_scope(self, test_device):
        """Should reject scopes not in VALID_SCOPES."""
        with pytest.raises(ValueError, match="Invalid scope"):
            mint_device_jwt(
                device_id=test_device["device_id"],
                user_id=test_device["user_id"],
                scope="admin",
            )

    def test_valid_scopes_are_frozen(self):
        """VALID_SCOPES should be immutable."""
        assert isinstance(VALID_SCOPES, frozenset)
        assert "read" in VALID_SCOPES
        assert "write" in VALID_SCOPES


class TestValidateDeviceJWT:
    """Tests for validate_device_jwt function."""

    @pytest.mark.asyncio
    async def test_validate_success_with_cache_hit(self, test_device, mock_redis, mock_db_session):
        """Should validate successfully when device exists (cache hit)."""
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
            scope="read",
        )

        # Mock cache hit — device exists
        mock_redis.get.return_value = b"1"

        claims = await validate_device_jwt(token)
        assert claims["device_id"] == test_device["device_id"]
        assert claims["user_id"] == test_device["user_id"]
        assert claims["scope"] == "read"

        # Should not hit database on cache hit
        mock_db_session.scalar_one_or_none.assert_not_called()

    @pytest.mark.asyncio
    async def test_validate_success_with_cache_miss(self, test_device, mock_redis, mock_db_session):
        """Should validate successfully when device exists (cache miss, DB hit)."""
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
            scope="read",
        )

        # Mock cache miss, DB returns device exists
        mock_redis.get.return_value = None
        mock_db_session.scalar_one_or_none.return_value = test_device["device_id"]

        claims = await validate_device_jwt(token)
        assert claims["device_id"] == test_device["device_id"]

        # Should write to cache after DB query
        mock_redis.setex.assert_called_once()

    @pytest.mark.asyncio
    async def test_validate_fails_when_device_deleted(self, test_device, mock_redis, mock_db_session):
        """Should fail validation when device has been deleted (GH#9493 revocation)."""
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
            scope="read",
        )

        # Mock device does not exist in DB
        mock_redis.get.return_value = None
        mock_db_session.scalar_one_or_none.return_value = None

        with pytest.raises(JWTDecodeError, match="has been unpaired or does not exist"):
            await validate_device_jwt(token)

    @pytest.mark.asyncio
    async def test_validate_fails_on_expired_token(self, test_device):
        """Should fail validation on expired token."""
        # Set very short TTL
        os.environ["DEVICE_JWT_TTL_DAYS"] = "0"
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
        )
        os.environ.pop("DEVICE_JWT_TTL_DAYS")

        with pytest.raises(JWTExpiredError):
            await validate_device_jwt(token)

    @pytest.mark.asyncio
    async def test_validate_fails_on_invalid_signature(self, test_device, mock_redis, mock_db_session):
        """Should fail validation on tampered token."""
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
        )

        # Change the secret to simulate tampered token
        os.environ["DEVICE_JWT_SECRET"] = "different-secret-32-chars-min"

        with pytest.raises(JWTDecodeError):
            await validate_device_jwt(token)

    @pytest.mark.asyncio
    async def test_validate_fails_on_missing_device_id_claim(self, test_device):
        """Should fail validation when device_id claim is missing."""
        # Manually craft a token without device_id
        from datetime import timedelta

        from autobot_shared.auth.jwt_core import encode_jwt

        payload = {"user_id": test_device["user_id"], "scope": "read", "aud": "autobot:device"}
        token = encode_jwt(payload, os.environ["DEVICE_JWT_SECRET"], expires_delta=timedelta(days=1))

        with pytest.raises(JWTDecodeError, match="missing device_id claim"):
            await validate_device_jwt(token)


class TestInvalidateDeviceCache:
    """Tests for invalidate_device_cache function."""

    @pytest.mark.asyncio
    async def test_invalidate_cache(self, test_device, mock_redis):
        """Should delete cache key for device."""
        await invalidate_device_cache(test_device["device_id"])
        mock_redis.delete.assert_called_once()
        call_args = mock_redis.delete.call_args[0][0]
        assert test_device["device_id"] in call_args

    @pytest.mark.asyncio
    async def test_invalidate_cache_handles_redis_none(self, test_device):
        """Should handle Redis unavailable gracefully."""
        with patch("services.device_jwt.get_async_redis_client", return_value=None):
            # Should not raise
            await invalidate_device_cache(test_device["device_id"])


class TestConfigurationDefaults:
    """Tests for configuration defaults and env var handling.

    The ``exp`` claim is a whole-second integer: ``floor(mint_time) + ttl``.
    Bounding it by the whole seconds read either side of the mint call is
    therefore exact, and needs no tolerance. The previous
    ``abs(exp - time.time() - ttl) < 1`` compared a truncated int against a
    float and failed (``1.000488 < 1``) whenever the mint landed late enough
    in a second -- a threshold that was never true with margin (#13399).
    """

    def test_default_ttl_is_90_days(self, test_device, monkeypatch):
        """Should default to 90-day TTL."""
        default_ttl_seconds = 90 * 24 * 3600
        monkeypatch.delenv("DEVICE_JWT_TTL_DAYS", raising=False)
        before = int(time.time())
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
        )
        after = int(time.time())
        claims = decode_jwt(token, os.environ["DEVICE_JWT_SECRET"])
        assert before + default_ttl_seconds <= claims["exp"] <= after + default_ttl_seconds

    def test_custom_ttl_from_env(self, test_device, monkeypatch):
        """Should use custom TTL from DEVICE_JWT_TTL_DAYS.

        ``monkeypatch`` (not a trailing ``os.environ.pop``) restores the var:
        the old cleanup never ran when the assertion failed, leaking a 30-day
        TTL into every later test in the session (#13399).
        """
        custom_ttl_seconds = 30 * 24 * 3600
        monkeypatch.setenv("DEVICE_JWT_TTL_DAYS", "30")
        before = int(time.time())
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
        )
        after = int(time.time())
        claims = decode_jwt(token, os.environ["DEVICE_JWT_SECRET"])
        assert before + custom_ttl_seconds <= claims["exp"] <= after + custom_ttl_seconds

    def test_default_audience(self, test_device):
        """Should default to 'autobot:device' audience."""
        os.environ.pop("DEVICE_JWT_AUDIENCE", None)
        token = mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
        )
        claims = decode_jwt(token, os.environ["DEVICE_JWT_SECRET"])
        assert claims["aud"] == "autobot:device"
