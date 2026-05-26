# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Unit tests for authenticate_websocket user_id forwarding (MVA-914 / MVA-801 gap).

Directly exercises auth_middleware.authenticate_websocket — the function that
commit 3d52aff50 extended with conditional user_id forwarding but left without
direct test coverage.

The existing smoke test (test_websocket_auth_smoke.py) patches
api.live_events._verify_token and never reaches authenticate_websocket.
These tests patch at the AuthenticationMiddleware level to cover the three
acceptance criteria from MVA-914:

  AC1: token WITH user_id in payload  → result contains "user_id"
  AC2: token WITHOUT user_id key      → result omits "user_id" (no KeyError)
  AC3: token with user_id=None        → result omits "user_id"

Loading strategy: conftest.py stubs auth_middleware to avoid the full
config/Redis import chain. We use spec_from_file_location to load the real
module with minimal stubs for its heavy deps, then patch at the object level
so the real function body is exercised.
"""

from __future__ import annotations

import importlib.util as _ilu
import logging as _stdlib_logging
import sys
import types as _types
from pathlib import Path
from unittest.mock import MagicMock, patch


_BACKEND = Path(__file__).resolve().parent.parent


def _load_real_auth_middleware():
    """Load the real auth_middleware module with its heavy deps pre-stubbed.

    conftest.py installs a lightweight stub for auth_middleware to avoid the
    config/Redis import chain.  Here we load the real source file via
    spec_from_file_location after providing minimal stubs for the three deps
    that would otherwise fail:
      - config.manager (circular import with config chain)
      - security_layer (not installed in dev venv)
      - utils.catalog_http_exceptions (depends on the same chain)
    """
    # Mirror conftest's get_logger patch so RotatingFileHandler isn't opened.
    try:
        import autobot_shared.logging_manager as _lm

        if not getattr(_lm, "_get_logger_patched_for_tests", False):
            _lm.get_logger = lambda name, *_a, **_k: _stdlib_logging.getLogger(name)
            _lm._get_logger_patched_for_tests = True
    except Exception:
        pass

    def _maybe_stub(name: str, **attrs):
        if name not in sys.modules:
            m = _types.ModuleType(name)
            m.__path__ = []
            m.__getattr__ = lambda attr: MagicMock()  # type: ignore[attr-defined]
            for k, v in attrs.items():
                setattr(m, k, v)
            sys.modules[name] = m

    _mock_cfg = MagicMock()
    _mock_cfg.get.return_value = {}
    _maybe_stub("config")
    _maybe_stub("config.manager", get_config_manager=MagicMock(return_value=_mock_cfg))
    _maybe_stub("security_layer", SecurityLayer=MagicMock)
    _maybe_stub("utils")
    _maybe_stub("utils.catalog_http_exceptions", raise_auth_error=MagicMock())

    # Temporarily remove the conftest stub so the real loader can register it.
    _saved_stub = sys.modules.pop("auth_middleware", None)
    spec = _ilu.spec_from_file_location("auth_middleware", str(_BACKEND / "auth_middleware.py"))
    real_mod = _ilu.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["auth_middleware"] = real_mod
    spec.loader.exec_module(real_mod)  # type: ignore[union-attr]

    # Restore the conftest stub for other tests, but inject the real symbols
    # so that cross-module patch targets (auth_middleware.AuthenticationMiddleware)
    # still work in our tests.
    if _saved_stub is not None:
        _saved_stub.authenticate_websocket = real_mod.authenticate_websocket
        _saved_stub.AuthenticationMiddleware = real_mod.AuthenticationMiddleware
        sys.modules["auth_middleware"] = _saved_stub

    return real_mod.authenticate_websocket, real_mod


# Load once at module collection time.
_authenticate_websocket, _auth_mod = _load_real_auth_middleware()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ws(token: str | None = "tok") -> MagicMock:
    """Minimal WebSocket mock with a configurable query-param token."""
    ws = MagicMock()
    ws.query_params.get.return_value = token
    return ws


def _patch_auth(token_data: dict | None):
    """Patch AuthenticationMiddleware on the real loaded module."""
    instance = MagicMock()
    instance.verify_jwt_token.return_value = token_data
    return patch.object(_auth_mod, "AuthenticationMiddleware", return_value=instance)


# ---------------------------------------------------------------------------
# AC1 — token WITH user_id → result includes "user_id"
# ---------------------------------------------------------------------------


class TestUserIdPresent:
    """Token payload carries user_id → forwarded verbatim into the result dict."""

    async def test_string_user_id_forwarded(self):
        token_data = {"username": "alice", "role": "user", "email": "a@x.com", "user_id": "u-abc123"}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())
        assert result is not None
        assert result["user_id"] == "u-abc123"

    async def test_integer_user_id_forwarded(self):
        token_data = {"username": "bob", "role": "admin", "email": "", "user_id": 42}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())
        assert result is not None
        assert result["user_id"] == 42

    async def test_non_user_id_fields_still_present(self):
        """Baseline fields must always be present alongside user_id."""
        token_data = {"username": "carol", "role": "user", "email": "c@x.com", "user_id": "u-xyz"}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())
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

    async def test_omitted_key_does_not_appear(self):
        token_data = {"username": "dave", "role": "user", "email": "d@x.com"}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())
        assert result is not None
        assert "user_id" not in result

    async def test_no_key_error_raised(self):
        """Regression guard: accessing missing key must not raise KeyError."""
        token_data = {"username": "eve", "role": "user"}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())  # must not raise
        assert result is not None

    async def test_baseline_fields_present_without_user_id(self):
        token_data = {"username": "frank", "role": "user", "email": "f@x.com"}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())
        assert result["username"] == "frank"
        assert result["role"] == "user"
        assert result["auth_method"] == "jwt_websocket"


# ---------------------------------------------------------------------------
# AC3 — token with user_id=None → result omits "user_id"
# ---------------------------------------------------------------------------


class TestUserIdNone:
    """Token payload has user_id=None → None must not be forwarded."""

    async def test_none_user_id_not_included(self):
        token_data = {"username": "grace", "role": "user", "email": "g@x.com", "user_id": None}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())
        assert result is not None
        assert "user_id" not in result

    async def test_none_user_id_does_not_set_key_to_none(self):
        """Key must be absent, not present with value None."""
        token_data = {"username": "hank", "role": "user", "user_id": None}
        with _patch_auth(token_data):
            result = await _authenticate_websocket(_ws())
        assert result.get("user_id", "MISSING") == "MISSING"
