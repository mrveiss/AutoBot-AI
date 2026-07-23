# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression tests for #12135.

``GET /api/auth/me`` 500'd with ``KeyError: 'username'`` for a
structurally-valid, signature-verified JWT that simply carries the identity
in a different claim (e.g. tokens minted by autobot-slm-backend use ``sub``,
not ``username`` — see autobot-slm-backend/services/auth.py). Two hard
``[...]`` accesses were involved:

- ``AuthenticationMiddleware._extract_user_from_jwt`` (auth_middleware.py):
  ``token_data["username"]`` / ``token_data["role"]``.
- ``get_current_user_info`` (api/auth.py): ``user_data["username"]`` /
  ``user_data["role"]``.

Both must degrade gracefully (fallback to ``sub``/``user_id``, or a safe
default role) rather than raise, and a token with NO identity claim at all
must be rejected cleanly (401), never a 500.
"""

from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, Request

from autobot_shared.auth.jwt_core import encode_jwt

_HS256_SECRET = "s" * 40  # deterministic test secret >=32 chars


def _bearer_request(token: str) -> MagicMock:
    request = MagicMock(spec=Request)
    headers = {"Authorization": f"Bearer {token}"}
    request.headers.get = lambda k, d=None: headers.get(k, d)
    return request


class TestExtractUserFromJwtMissingUsername:
    """AuthenticationMiddleware._extract_user_from_jwt claim-fallback (#12135)."""

    @staticmethod
    def _middleware(real_auth_middleware, secret=_HS256_SECRET):
        cls = real_auth_middleware.AuthenticationMiddleware
        middleware = cls.__new__(cls)
        middleware.jwt_secret = secret
        middleware.jwt_public_key = None
        middleware.failed_attempts = {}
        return middleware

    def test_sub_only_token_falls_back_to_sub_as_username(self, real_auth_middleware):
        """A token with 'sub' but no 'username' (e.g. SLM-minted) must not crash."""
        token = encode_jwt({"sub": "alice"}, secret=_HS256_SECRET, expiry_hours=1)
        middleware = self._middleware(real_auth_middleware)

        user = middleware._extract_user_from_jwt(_bearer_request(token))

        assert user is not None
        assert user["username"] == "alice"
        assert user["role"] == "user"  # safe default when role claim is absent

    def test_user_id_only_token_falls_back_to_user_id(self, real_auth_middleware):
        """A token with only 'user_id' still resolves an identity, not a crash."""
        token = encode_jwt({"user_id": "u-42"}, secret=_HS256_SECRET, expiry_hours=1)
        middleware = self._middleware(real_auth_middleware)

        user = middleware._extract_user_from_jwt(_bearer_request(token))

        assert user is not None
        assert user["username"] == "u-42"

    def test_token_with_no_identity_claim_is_rejected_not_crashed(self, real_auth_middleware):
        """No username/sub/user_id at all -> clean None (caller 401s), never a KeyError."""
        token = encode_jwt({"role": "admin"}, secret=_HS256_SECRET, expiry_hours=1)
        middleware = self._middleware(real_auth_middleware)

        assert middleware._extract_user_from_jwt(_bearer_request(token)) is None

    def test_full_claims_token_still_works(self, real_auth_middleware):
        """Happy path: a normal username+role token is unaffected."""
        token = encode_jwt({"username": "bob", "role": "admin"}, secret=_HS256_SECRET, expiry_hours=1)
        middleware = self._middleware(real_auth_middleware)

        user = middleware._extract_user_from_jwt(_bearer_request(token))

        assert user["username"] == "bob"
        assert user["role"] == "admin"


class TestGetCurrentUserInfoMissingUsername:
    """GET /api/auth/me handler (api/auth.py) — defensive claim access (#12135)."""

    @pytest.fixture
    def auth_module(self):
        import api.auth as auth_module

        return auth_module

    async def _call_me(self, auth_module, monkeypatch, user_data):
        auth_mw = MagicMock()
        auth_mw.get_user_from_request.return_value = user_data
        monkeypatch.setattr(auth_module, "get_auth_middleware", lambda: auth_mw)

        request = MagicMock(spec=Request)
        return await auth_module.get_current_user_info(request)

    @pytest.mark.asyncio
    async def test_user_record_missing_username_returns_200_with_fallback(self, auth_module, monkeypatch):
        """A valid user record lacking 'username' (only 'sub') must 200, not 500."""
        response = await self._call_me(auth_module, monkeypatch, {"sub": "carol", "role": "operator"})

        assert response["username"] == "carol"
        assert response["role"] == "operator"
        assert response["authenticated"] is True

    @pytest.mark.asyncio
    async def test_user_record_missing_role_defaults_safely(self, auth_module, monkeypatch):
        """A valid user record lacking 'role' must 200 with a safe default, not 500."""
        response = await self._call_me(auth_module, monkeypatch, {"username": "dave"})

        assert response["username"] == "dave"
        assert response["role"] == "user"

    @pytest.mark.asyncio
    async def test_no_authenticated_user_is_clean_401(self, auth_module, monkeypatch):
        """No user_data at all -> clean 401, not a 500."""
        with pytest.raises(HTTPException) as exc_info:
            await self._call_me(auth_module, monkeypatch, None)

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_full_claims_user_still_works(self, auth_module, monkeypatch):
        """Happy path: a normal username+role user record is unaffected."""
        response = await self._call_me(
            auth_module, monkeypatch, {"username": "erin", "role": "admin", "email": "erin@example.com"}
        )

        assert response["username"] == "erin"
        assert response["role"] == "admin"
        assert response["email"] == "erin@example.com"
