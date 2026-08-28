# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for device JWT service (GH#9493)."""

import logging
import os
import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

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
    """Mock database session for device state checks.

    ``scalar_one_or_none`` remains how a test says *the row exists* (its value
    being the device id) or *it does not* (``None``). That is the contract the
    tests in this file were written against and it is deliberately unchanged.

    #14964 made the state read select ``(id, revoked_at)`` and consume it with
    ``result.first()``: existence and revocation are two different answers, and
    one scalar cannot carry both without conflating "deleted" with "revoked".
    A bare ``MagicMock`` answers ``first()`` with a truthy mock, so a fixture
    that models only ``scalar_one_or_none`` makes every device look revoked --
    which is exactly what it did before this was written. ``first()`` is
    therefore derived here from the same value, leaving every existing
    assertion untouched.

    ``revoked_at`` defaults to ``None`` (present, not revoked); a test models a
    revoked row by assigning a real ``datetime``. A string is not accepted by
    the real column, so it must not be accepted here either.
    """
    result = MagicMock()
    result.scalar_one_or_none = MagicMock()
    #: Assigned by a test to model a row that exists AND carries a revocation.
    result.revoked_at = None

    def _first():
        # Read the configured value rather than calling scalar_one_or_none, so
        # `scalar_one_or_none.assert_not_called()` still means what it says.
        identity = result.scalar_one_or_none.return_value
        if identity is None or isinstance(identity, MagicMock):
            # No row was configured -> no row exists -> unpaired, never revoked.
            return None
        assert result.revoked_at is None or isinstance(
            result.revoked_at, datetime
        ), "revoked_at must be a datetime -- the real column rejects a string"
        return SimpleNamespace(id=identity, revoked_at=result.revoked_at)

    result.first = MagicMock(side_effect=_first)

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


class TestRefusalsStayDistinguishable:
    """Three ways a credential is refused, and none may swallow another (#14964).

    Revocation was added on top of an existing "unpaired or does not exist"
    refusal. Both raise ``JWTDecodeError`` and both close the caller's socket
    the same way, so the *only* thing separating them is the message and the
    logged reason -- which makes asserting the separation mandatory rather than
    decorative. The vacuous version of this suite checks that each case raises;
    this one checks that each case raises **something the other two do not**.

    ``TestValidateDeviceJWT`` already pins the deleted-device message. What was
    missing, and is added here, is the proof that "revoked" does not report as
    "unpaired" and that "unpaired" does not report as "revoked".
    """

    def _token(self, test_device):
        return mint_device_jwt(
            device_id=test_device["device_id"],
            user_id=test_device["user_id"],
            scope="read",
        )

    @pytest.mark.asyncio
    async def test_a_revoked_device_is_refused_as_revoked(self, test_device, mock_redis, mock_db_session):
        mock_redis.get.return_value = None
        mock_db_session.scalar_one_or_none.return_value = test_device["device_id"]
        mock_db_session.revoked_at = datetime(2026, 8, 24, tzinfo=timezone.utc)

        with pytest.raises(JWTDecodeError, match="has been revoked"):
            await validate_device_jwt(self._token(test_device))

    @pytest.mark.asyncio
    async def test_a_present_unrevoked_device_still_validates(self, test_device, mock_redis, mock_db_session):
        """Non-vacuity: the revocation check must not refuse a live device.

        Without this, every assertion above would still pass if the check had
        simply become "always refuse" -- which is precisely the regression that
        reached CI (a fixture that never modelled ``revoked_at`` made a bare
        mock read as revoked for every device).
        """
        mock_redis.get.return_value = None
        mock_db_session.scalar_one_or_none.return_value = test_device["device_id"]
        mock_db_session.revoked_at = None

        claims = await validate_device_jwt(self._token(test_device))
        assert claims["device_id"] == test_device["device_id"]

    @pytest.mark.asyncio
    async def test_deleted_and_revoked_carry_different_messages_and_reasons(
        self, test_device, mock_redis, mock_db_session, caplog
    ):
        """The load-bearing one: a deleted device must never report as revoked.

        Existence is decided before revocation in ``_read_device_state``. If
        that order is inverted -- or if the absent case stops being reachable,
        as it did under the unmodelled fixture -- the newer refusal swallows
        the older one and an operator reads "revoked" for a device somebody
        simply unpaired.
        """
        token = self._token(test_device)

        mock_redis.get.return_value = None
        mock_db_session.scalar_one_or_none.return_value = None  # no row at all
        with caplog.at_level(logging.WARNING, logger="services.device_jwt"):
            with pytest.raises(JWTDecodeError) as deleted:
                await validate_device_jwt(token)
            deleted_logs = [r.getMessage() for r in caplog.records]

        caplog.clear()
        mock_redis.get.return_value = None
        mock_db_session.scalar_one_or_none.return_value = test_device["device_id"]
        mock_db_session.revoked_at = datetime(2026, 8, 24, tzinfo=timezone.utc)
        with caplog.at_level(logging.WARNING, logger="services.device_jwt"):
            with pytest.raises(JWTDecodeError) as revoked:
                await validate_device_jwt(token)
            revoked_logs = [r.getMessage() for r in caplog.records]

        deleted_msg, revoked_msg = str(deleted.value), str(revoked.value)

        assert "has been unpaired or does not exist" in deleted_msg
        assert "has been revoked" not in deleted_msg, "a deleted device is being reported as revoked"

        assert "has been revoked" in revoked_msg
        assert "has been unpaired or does not exist" not in revoked_msg

        assert any("reason=unpaired" in m for m in deleted_logs)
        assert not any("reason=revoked" in m for m in deleted_logs)
        assert any("reason=revoked" in m for m in revoked_logs)
        assert not any("reason=unpaired" in m for m in revoked_logs)

    @pytest.mark.asyncio
    async def test_an_unreadable_state_is_not_reported_as_unpaired(self, test_device, mock_redis, mock_db_session):
        """A database that cannot answer is not a fleet of unpaired devices.

        The most plausible cause is a deployment whose schema predates
        migration ``20260824_084``, so ``revoked_at`` does not exist and the
        state read raises. That must deny -- but reporting it as "unpaired"
        would tell an operator every device had been individually removed,
        pointing the investigation away from the missing migration.
        """
        mock_redis.get.return_value = None
        mock_db_session.first.side_effect = OperationalError("SELECT revoked_at", {}, Exception("no such column"))

        with pytest.raises(JWTDecodeError) as exc:
            await validate_device_jwt(self._token(test_device))

        message = str(exc.value)
        assert "state could not be read" in message
        assert "has been unpaired or does not exist" not in message
        assert "has been revoked" not in message

    @pytest.mark.asyncio
    async def test_an_unreadable_state_is_never_cached(self, test_device, mock_redis, mock_db_session):
        """A transient outage must not be frozen into the cache for its whole TTL."""
        mock_redis.get.return_value = None
        mock_db_session.first.side_effect = OperationalError("SELECT revoked_at", {}, Exception("no such column"))

        with pytest.raises(JWTDecodeError):
            await validate_device_jwt(self._token(test_device))

        mock_redis.setex.assert_not_called()
