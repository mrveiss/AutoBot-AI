# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for authenticate_websocket user_id forwarding (MVA-914 / MVA-801 gap).

Directly exercises auth_middleware.authenticate_websocket — the function that
commit 3d52aff50 extended with conditional user_id forwarding but left without
direct test coverage.

The smoke test (test_websocket_auth_smoke.py) patches the
authenticate_websocket seam itself and never exercises its body. These tests
run the REAL function via the shared ``real_auth_middleware`` fixture
(tests/conftest.py — alias-key load, #11648/#11791) and patch the
``get_auth_middleware()`` singleton accessor: authenticate_websocket resolves
the middleware through the lazy singleton, so patching the class would be
inert (#11791). Three acceptance criteria from MVA-914:

  AC1: token WITH user_id in payload  → result contains "user_id"
  AC2: token WITHOUT user_id key      → result omits "user_id" (no KeyError)
  AC3: token with user_id=None        → result omits "user_id"
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ws(token: str | None = "tok") -> MagicMock:
    """Minimal WebSocket mock with a configurable query-param token."""
    ws = MagicMock()
    ws.query_params.get.return_value = token
    return ws


def _patch_auth(auth_mod, token_data: dict | None):
    """Patch the get_auth_middleware() singleton accessor on the real module.

    authenticate_websocket resolves the middleware via the module-level
    ``get_auth_middleware`` lazy singleton (never by instantiating the class),
    so the seam is the accessor, not ``AuthenticationMiddleware`` (#11791).
    """
    instance = MagicMock()
    instance.verify_jwt_token.return_value = token_data
    return patch.object(auth_mod, "get_auth_middleware", return_value=instance)


# ---------------------------------------------------------------------------
# AC1 — token WITH user_id → result includes "user_id"
# ---------------------------------------------------------------------------


class TestUserIdPresent:
    """Token payload carries user_id → forwarded verbatim into the result dict."""

    async def test_string_user_id_forwarded(self, real_auth_middleware):
        token_data = {"username": "alice", "role": "user", "email": "a@x.com", "user_id": "u-abc123"}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())
        assert result is not None
        assert result["user_id"] == "u-abc123"

    async def test_integer_user_id_forwarded(self, real_auth_middleware):
        token_data = {"username": "bob", "role": "admin", "email": "", "user_id": 42}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())
        assert result is not None
        assert result["user_id"] == 42

    async def test_non_user_id_fields_still_present(self, real_auth_middleware):
        """Baseline fields must always be present alongside user_id."""
        token_data = {"username": "carol", "role": "user", "email": "c@x.com", "user_id": "u-xyz"}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())
        assert result is not None
        assert result["username"] == "carol"
        assert result["role"] == "user"
        assert result["auth_method"] == "jwt_websocket"
        assert "user_id" in result


# ---------------------------------------------------------------------------
# AC2 — token WITHOUT user_id key → result omits "user_id" (no KeyError)
# ---------------------------------------------------------------------------


class TestUserIdAbsent:
    """Token payload has no user_id key → key must not appear in result."""

    async def test_omitted_key_does_not_appear(self, real_auth_middleware):
        token_data = {"username": "dave", "role": "user", "email": "d@x.com"}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())
        assert result is not None
        assert "user_id" not in result

    async def test_no_key_error_raised(self, real_auth_middleware):
        """Regression guard: accessing missing key must not raise KeyError."""
        token_data = {"username": "eve", "role": "user"}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())  # must not raise
        assert result is not None

    async def test_baseline_fields_present_without_user_id(self, real_auth_middleware):
        token_data = {"username": "frank", "role": "user", "email": "f@x.com"}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())
        assert result["username"] == "frank"
        assert result["role"] == "user"
        assert result["auth_method"] == "jwt_websocket"


# ---------------------------------------------------------------------------
# AC3 — token with user_id=None → result omits "user_id"
# ---------------------------------------------------------------------------


class TestUserIdNone:
    """Token payload has user_id=None → None must not be forwarded."""

    async def test_none_user_id_not_included(self, real_auth_middleware):
        token_data = {"username": "grace", "role": "user", "email": "g@x.com", "user_id": None}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())
        assert result is not None
        assert "user_id" not in result

    async def test_none_user_id_does_not_set_key_to_none(self, real_auth_middleware):
        """Key must be absent, not present with value None."""
        token_data = {"username": "hank", "role": "user", "user_id": None}
        with _patch_auth(real_auth_middleware, token_data):
            result = await real_auth_middleware.authenticate_websocket(_ws())
        assert result.get("user_id", "MISSING") == "MISSING"
