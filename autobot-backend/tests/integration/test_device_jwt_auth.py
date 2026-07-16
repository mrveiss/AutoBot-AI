# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Integration tests for device JWT authentication and scoping (GH#9493).

Rewritten for the canonical contract (#11648): the MVA-3237-era
``DeviceTokenScope`` enum ("read-only"/"admin"), sync ``validate_device_jwt``
and ``type: device_token`` claim were replaced by GH#9493 —

- scopes are ``"read"`` / ``"write"`` (``services.device_jwt.VALID_SCOPES``)
- ``validate_device_jwt`` is async and enforces a device-existence
  (revocation) check plus an ``aud`` claim
- device JWTs authenticate ONLY on ``/api/devices/`` endpoints, and
  read-scoped tokens cannot use mutating HTTP methods
"""

import uuid
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from autobot_shared.auth.jwt_core import JWTDecodeError, JWTExpiredError, encode_jwt
from services.device_jwt import VALID_SCOPES, mint_device_jwt, validate_device_jwt

_DEVICE_SIGNING_KEY = "d" * 40  # deterministic test key ≥32 chars
_AUDIENCE = "autobot:device"


@pytest.fixture
def device_jwt_env(monkeypatch):
    """Set a stable device-JWT signing key for testing."""
    monkeypatch.setenv("DEVICE_JWT_SECRET", _DEVICE_SIGNING_KEY)
    return _DEVICE_SIGNING_KEY


@pytest.fixture
def device_exists(monkeypatch):
    """Pass the GH#9493 revocation check — device exists in the DB."""
    monkeypatch.setattr(
        "services.device_jwt._device_exists_cached",
        AsyncMock(return_value=True),
    )


def _bearer_request(token: str | None, path: str = "/api/devices/list", method: str = "GET") -> MagicMock:
    """Mock request carrying an optional Bearer token."""
    request = MagicMock(spec=Request)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request.headers.get = lambda k, d=None: headers.get(k, d)
    request.url.path = path
    request.method = method
    request.cookies = {}
    return request


class TestDeviceJWTGeneration:
    """Test device JWT generation during pairing."""

    @pytest.mark.asyncio
    async def test_mint_device_jwt_read_scope(self, device_jwt_env, device_exists):
        """JWT should carry the canonical claims for a read-scoped device."""
        device_id = str(uuid.uuid4())
        user_id = "user123"

        token = mint_device_jwt(device_id=device_id, user_id=user_id, scope="read")

        assert isinstance(token, str)
        assert token.count(".") == 2  # header.payload.signature

        claims = await validate_device_jwt(token)
        assert claims["device_id"] == device_id
        assert claims["user_id"] == user_id
        assert claims["scope"] == "read"
        assert claims["aud"] == _AUDIENCE
        assert "exp" in claims

    @pytest.mark.asyncio
    async def test_mint_device_jwt_write_scope(self, device_jwt_env, device_exists):
        """JWT should carry the write scope claim."""
        token = mint_device_jwt(device_id=str(uuid.uuid4()), user_id="user456", scope="write")

        claims = await validate_device_jwt(token)
        assert claims["scope"] == "write"

    def test_mint_device_jwt_rejects_unknown_scope(self, device_jwt_env):
        """Legacy MVA-3237 scopes ('read-only'/'admin') are no longer mintable."""
        assert VALID_SCOPES == frozenset({"read", "write"})
        for legacy_scope in ("read-only", "admin"):
            with pytest.raises(ValueError, match="Invalid scope"):
                mint_device_jwt(device_id=str(uuid.uuid4()), user_id="user123", scope=legacy_scope)

    def test_mint_device_jwt_defaults_to_read(self, device_jwt_env):
        """Least-privilege default: omitted scope mints a read token."""
        from autobot_shared.auth.jwt_core import decode_jwt

        token = mint_device_jwt(device_id=str(uuid.uuid4()), user_id="user789")
        claims = decode_jwt(token, _DEVICE_SIGNING_KEY, audience=_AUDIENCE)
        assert claims["scope"] == "read"


class TestDeviceJWTValidation:
    """Test device JWT validation (async, revocation-checked)."""

    @pytest.mark.asyncio
    async def test_validate_device_jwt_success(self, device_jwt_env, device_exists):
        """Valid JWT for an existing device should decode successfully."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id, "user789")

        claims = await validate_device_jwt(token)

        assert claims["device_id"] == device_id
        assert claims["user_id"] == "user789"
        assert claims["scope"] == "read"

    @pytest.mark.asyncio
    async def test_validate_device_jwt_rejects_unpaired_device(self, device_jwt_env, monkeypatch):
        """Tokens for deleted (unpaired) devices must be rejected."""
        monkeypatch.setattr(
            "services.device_jwt._device_exists_cached",
            AsyncMock(return_value=False),
        )
        token = mint_device_jwt(str(uuid.uuid4()), "user123")

        with pytest.raises(JWTDecodeError, match="unpaired"):
            await validate_device_jwt(token)

    @pytest.mark.asyncio
    async def test_validate_device_jwt_missing_device_id(self, device_jwt_env, device_exists):
        """JWT missing the device_id claim should be rejected."""
        token = encode_jwt(
            {"aud": _AUDIENCE, "user_id": "user123", "scope": "read"},
            secret=_DEVICE_SIGNING_KEY,
            expires_delta=timedelta(days=1),
        )

        with pytest.raises(JWTDecodeError, match="device_id"):
            await validate_device_jwt(token)

    @pytest.mark.asyncio
    async def test_validate_device_jwt_rejects_expired(self, device_jwt_env, device_exists):
        """JWT past its exp timestamp should raise JWTExpiredError."""
        token = encode_jwt(
            {"aud": _AUDIENCE, "device_id": str(uuid.uuid4()), "user_id": "u", "scope": "read"},
            secret=_DEVICE_SIGNING_KEY,
            expires_delta=timedelta(seconds=-1),
        )

        with pytest.raises(JWTExpiredError):
            await validate_device_jwt(token)

    @pytest.mark.asyncio
    async def test_validate_device_jwt_rejects_wrong_audience(self, device_jwt_env, device_exists):
        """JWT without the device audience claim should be rejected."""
        token = encode_jwt(
            {"aud": "autobot:other", "device_id": str(uuid.uuid4()), "user_id": "u", "scope": "read"},
            secret=_DEVICE_SIGNING_KEY,
            expires_delta=timedelta(days=1),
        )

        with pytest.raises(JWTDecodeError):
            await validate_device_jwt(token)


class TestDeviceJWTAuthentication:
    """Test device JWT extraction in the auth middleware fallback chain."""

    @staticmethod
    def _middleware(real_auth_middleware):
        cls = real_auth_middleware.AuthenticationMiddleware
        return cls.__new__(cls)

    @pytest.mark.asyncio
    async def test_extract_user_from_device_jwt(self, device_jwt_env, device_exists, real_auth_middleware):
        """Middleware should build a synthetic device user from a valid JWT."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id, "user123", scope="read")

        middleware = self._middleware(real_auth_middleware)
        user_data = await middleware._extract_user_from_device_jwt(_bearer_request(token))

        assert user_data is not None
        assert user_data["user_id"] == "user123"
        assert user_data["device_id"] == device_id
        assert user_data["scope"] == "read"
        assert user_data["auth_method"] == "device_jwt"
        assert user_data["role"] == "device"
        assert user_data["username"] == f"device:{device_id}"

    @pytest.mark.asyncio
    async def test_extract_user_from_device_jwt_no_bearer(self, device_jwt_env, real_auth_middleware):
        """Middleware should return None when no Bearer token is present."""
        middleware = self._middleware(real_auth_middleware)
        assert await middleware._extract_user_from_device_jwt(_bearer_request(None)) is None

    @pytest.mark.asyncio
    async def test_extract_user_from_device_jwt_invalid_token(self, device_jwt_env, real_auth_middleware):
        """Middleware should return None for invalid tokens."""
        middleware = self._middleware(real_auth_middleware)
        assert await middleware._extract_user_from_device_jwt(_bearer_request("invalid_token")) is None


class TestDeviceScopeEnforcement:
    """Test the GH#9493 path allow-list and scope enforcement in get_current_user."""

    @staticmethod
    def _patched(real_auth_middleware):
        cls = real_auth_middleware.AuthenticationMiddleware
        middleware = cls.__new__(cls)
        return (
            middleware,
            patch.object(real_auth_middleware, "get_auth_middleware", return_value=middleware),
            patch.object(middleware, "get_user_from_request", return_value=None),
        )

    @pytest.mark.asyncio
    async def test_device_jwt_rejected_outside_devices_prefix(
        self, device_jwt_env, device_exists, real_auth_middleware
    ):
        """A valid device JWT must not authenticate arbitrary REST endpoints."""
        token = mint_device_jwt(str(uuid.uuid4()), "user123", scope="write")
        request = _bearer_request(token, path="/api/conversations")

        middleware, p_factory, p_user = self._patched(real_auth_middleware)
        with p_factory, p_user:
            with pytest.raises(HTTPException) as exc_info:
                await real_auth_middleware.get_current_user(request)

        assert exc_info.value.status_code == 403
        assert "Device JWT not permitted" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_device_jwt_allowed_on_devices_prefix(self, device_jwt_env, device_exists, real_auth_middleware):
        """A valid read-scoped device JWT authenticates GETs under /api/devices/."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id, "user123", scope="read")
        request = _bearer_request(token, path="/api/devices/list", method="GET")

        middleware, p_factory, p_user = self._patched(real_auth_middleware)
        with p_factory, p_user:
            user = await real_auth_middleware.get_current_user(request)

        assert user["auth_method"] == "device_jwt"
        assert user["device_id"] == device_id

    @pytest.mark.asyncio
    async def test_read_scope_blocks_mutating_methods(self, device_jwt_env, device_exists, real_auth_middleware):
        """Read-scoped device JWTs cannot use mutating HTTP methods."""
        token = mint_device_jwt(str(uuid.uuid4()), "user123", scope="read")
        request = _bearer_request(token, path="/api/devices/pair", method="POST")

        middleware, p_factory, p_user = self._patched(real_auth_middleware)
        with p_factory, p_user:
            with pytest.raises(HTTPException) as exc_info:
                await real_auth_middleware.get_current_user(request)

        assert exc_info.value.status_code == 403
        assert "Read-only device JWT" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_write_scope_allows_mutating_methods(self, device_jwt_env, device_exists, real_auth_middleware):
        """Write-scoped device JWTs may use mutating HTTP methods on /api/devices/."""
        token = mint_device_jwt(str(uuid.uuid4()), "user123", scope="write")
        request = _bearer_request(token, path="/api/devices/pair", method="POST")

        middleware, p_factory, p_user = self._patched(real_auth_middleware)
        with p_factory, p_user:
            user = await real_auth_middleware.get_current_user(request)

        assert user["auth_method"] == "device_jwt"
        assert user["scope"] == "write"


class TestRequireDeviceJwtDependency:
    """require_device_jwt dependency factory — #11736 rot fix.

    The pre-fix implementation never awaited the async extraction (a truthy
    coroutine passed the guard, then ``.get()`` raised AttributeError) and
    enforced the retired MVA-3237 "read-only"/"admin" scopes. These tests pin
    the canonical GH#9493 behaviour.
    """

    @staticmethod
    def _patched_factory(real_auth_middleware):
        cls = real_auth_middleware.AuthenticationMiddleware
        middleware = cls.__new__(cls)
        return patch.object(real_auth_middleware, "get_auth_middleware", return_value=middleware)

    def test_factory_rejects_legacy_scopes(self, real_auth_middleware):
        """Retired MVA-3237 scopes fail fast at route-definition time."""
        for legacy_scope in ("read-only", "admin"):
            with pytest.raises(ValueError, match="Invalid min_scope"):
                real_auth_middleware.require_device_jwt(legacy_scope)

    @pytest.mark.asyncio
    async def test_valid_token_authenticates(self, device_jwt_env, device_exists, real_auth_middleware):
        """Await-rot regression: extraction is awaited and yields the device user."""
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id, "user123", scope="read")

        dependency = real_auth_middleware.require_device_jwt()
        with self._patched_factory(real_auth_middleware):
            user = await dependency(_bearer_request(token))

        assert user["device_id"] == device_id
        assert user["user_id"] == "user123"
        assert user["auth_method"] == "device_jwt"

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, device_jwt_env, real_auth_middleware):
        """No Bearer token → 401."""
        dependency = real_auth_middleware.require_device_jwt()
        with self._patched_factory(real_auth_middleware):
            with pytest.raises(HTTPException) as exc_info:
                await dependency(_bearer_request(None))
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, device_jwt_env, real_auth_middleware):
        """Garbage Bearer token → 401."""
        dependency = real_auth_middleware.require_device_jwt()
        with self._patched_factory(real_auth_middleware):
            with pytest.raises(HTTPException) as exc_info:
                await dependency(_bearer_request("not-a-jwt"))
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_revoked_device_returns_401(self, device_jwt_env, real_auth_middleware, monkeypatch):
        """Unpaired device fails the canonical revocation check → 401."""
        monkeypatch.setattr(
            "services.device_jwt._device_exists_cached",
            AsyncMock(return_value=False),
        )
        token = mint_device_jwt(str(uuid.uuid4()), "user123", scope="write")

        dependency = real_auth_middleware.require_device_jwt()
        with self._patched_factory(real_auth_middleware):
            with pytest.raises(HTTPException) as exc_info:
                await dependency(_bearer_request(token))
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_read_token_rejected_by_write_min_scope(self, device_jwt_env, device_exists, real_auth_middleware):
        """Canonical scope enforcement: read token on a write dependency → 403."""
        token = mint_device_jwt(str(uuid.uuid4()), "user123", scope="read")

        dependency = real_auth_middleware.require_device_jwt("write")
        with self._patched_factory(real_auth_middleware):
            with pytest.raises(HTTPException) as exc_info:
                await dependency(_bearer_request(token))

        assert exc_info.value.status_code == 403
        assert "write scope" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_write_token_passes_write_min_scope(self, device_jwt_env, device_exists, real_auth_middleware):
        """Write-scoped token satisfies min_scope='write'."""
        token = mint_device_jwt(str(uuid.uuid4()), "user123", scope="write")

        dependency = real_auth_middleware.require_device_jwt("write")
        with self._patched_factory(real_auth_middleware):
            user = await dependency(_bearer_request(token))

        assert user["scope"] == "write"


class TestRequireDeviceJwtHTTPWiring:
    """require_device_jwt exercised through real FastAPI routes (#11736)."""

    @pytest.fixture
    def http_client(self, real_auth_middleware):
        """TestClient for an app with read- and write-guarded device routes."""
        from fastapi import Depends, FastAPI
        from fastapi.testclient import TestClient

        app = FastAPI()
        read_dep = real_auth_middleware.require_device_jwt()
        write_dep = real_auth_middleware.require_device_jwt("write")

        @app.get("/device-read")
        async def device_read(user: dict = Depends(read_dep)):
            return {"device_id": user["device_id"], "scope": user["scope"]}

        @app.post("/device-write")
        async def device_write(user: dict = Depends(write_dep)):
            return {"device_id": user["device_id"], "scope": user["scope"]}

        cls = real_auth_middleware.AuthenticationMiddleware
        middleware = cls.__new__(cls)
        with patch.object(real_auth_middleware, "get_auth_middleware", return_value=middleware):
            yield TestClient(app)

    def test_401_without_token(self, device_jwt_env, http_client):
        response = http_client.get("/device-read")
        assert response.status_code == 401

    def test_401_with_user_style_garbage_token(self, device_jwt_env, http_client):
        response = http_client.get("/device-read", headers={"Authorization": "Bearer not-a-device-jwt"})
        assert response.status_code == 401

    def test_403_read_token_on_write_route(self, device_jwt_env, device_exists, http_client):
        token = mint_device_jwt(str(uuid.uuid4()), "user123", scope="read")
        response = http_client.post("/device-write", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 403

    def test_200_valid_read_token(self, device_jwt_env, device_exists, http_client):
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id, "user123", scope="read")
        response = http_client.get("/device-read", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json() == {"device_id": device_id, "scope": "read"}

    def test_200_valid_write_token_on_write_route(self, device_jwt_env, device_exists, http_client):
        device_id = str(uuid.uuid4())
        token = mint_device_jwt(device_id, "user123", scope="write")
        response = http_client.post("/device-write", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert response.json()["scope"] == "write"
