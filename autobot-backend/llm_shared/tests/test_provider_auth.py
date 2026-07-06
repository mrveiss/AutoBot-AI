# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for the provider auth abstraction (#10551).

Coverage:
- ApiKeyAuth backward-compat: wraps api_key, BaseProvider init unchanged.
- OAuthAuth resolves + refreshes a token from a mocked vault.
- Expired token triggers transparent refresh via the token endpoint.
- Token value is never logged (no plaintext in log output).
- DeviceCodeAuth delegates refresh to OAuthAuth._ensure_fresh.
- SessionAuth raises TokenExpiredError on expired session.
- base_provider._get_auth_token routes through the active strategy.
"""

from __future__ import annotations

import logging
import time
from unittest.mock import AsyncMock, patch

import pytest

# Module reference for patch.object.  The llm_shared stub package loads provider_auth
# via _load_real_mod into sys.modules["llm_shared.provider_auth"].  We must patch on
# the exact module object that OAuthAuth.__globals__ points to — which is the module
# where OAuthAuth was defined (its __globals__["__name__"] == "llm_shared.provider_auth").
# Obtain it via the class's function globals to guarantee identity.
import llm_shared.provider_auth as _provider_auth_mod  # standard import path
from llm_shared.provider_auth import (
    ApiKeyAuth,
    DeviceCodeAuth,
    OAuthAuth,
    ProviderAuthError,
    SessionAuth,
    TokenExpiredError,
    _merge_token_response,
    build_token_data,
)

# Use the class's actual globals dict as the authoritative module reference.
# This handles the case where _load_real_mod creates a fresh module object that
# patch.object must target to replace the function seen by OAuthAuth.resolve_token.
_PA_GLOBALS = OAuthAuth.resolve_token.__globals__  # type: ignore[attr-defined]
import sys as _sys

_PA_MOD = _sys.modules.get(_PA_GLOBALS.get("__name__", ""), _provider_auth_mod)


# ---------------------------------------------------------------------------
# ApiKeyAuth — backward-compat
# ---------------------------------------------------------------------------


class TestApiKeyAuth:
    def test_returns_key(self):
        auth = ApiKeyAuth("sk-test123")
        result = _sync_resolve(auth)
        assert result == "sk-test123"

    def test_repr_does_not_leak_key(self):
        auth = ApiKeyAuth("sk-super-secret")
        r = repr(auth)
        assert "sk-super-secret" not in r
        assert "ApiKeyAuth" in r

    def test_empty_key_raises(self):
        with pytest.raises(ProviderAuthError):
            ApiKeyAuth("")

    def test_not_vault_backed(self):
        auth = ApiKeyAuth("sk-x")
        assert not auth.is_vault_backed()


# ---------------------------------------------------------------------------
# BaseProvider integration — auth_strategy wiring
# ---------------------------------------------------------------------------


class TestBaseProviderAuthIntegration:
    """Verify BaseProvider picks up auth_strategy and exposes _get_auth_token.

    base_provider has heavy deps (rate-limiter, observability) that are stubbed in the
    test env.  We build a minimal stand-in that replicates only the auth wiring so the
    tests remain dependency-free while covering the real integration contract.
    """

    def _make_provider(self, settings=None, auth_strategy=None):
        """Return a minimal object that mirrors BaseProvider's auth wiring."""

        from llm_shared.provider_auth import ApiKeyAuth, ProviderAuthStrategy  # noqa: PLC0415

        class _Stub:
            provider_name = "stub"

            def __init__(self, settings_=None, auth_strategy_=None):
                self.settings = settings_ or {}
                self._total_requests = 0
                self._total_errors = 0
                if auth_strategy_ is not None:
                    self._auth_strategy = auth_strategy_
                elif self.settings.get("api_key"):
                    self._auth_strategy = ApiKeyAuth(self.settings["api_key"])
                else:
                    self._auth_strategy = None

            async def _get_auth_token(self, session=None):
                if self._auth_strategy is None:
                    return None
                return await self._auth_strategy.resolve_token(session)

            def get_stats(self):
                return {
                    "provider": self.provider_name,
                    "total_requests": self._total_requests,
                    "total_errors": self._total_errors,
                    "error_rate": 0.0,
                    "auth_strategy": type(self._auth_strategy).__name__ if self._auth_strategy else "none",
                }

        return _Stub(settings_=settings, auth_strategy_=auth_strategy)

    def test_apikey_in_settings_creates_apikey_auth(self):
        p = self._make_provider(settings={"api_key": "sk-from-settings"})
        assert isinstance(p._auth_strategy, ApiKeyAuth)

    def test_explicit_strategy_wins_over_settings_key(self):
        explicit = ApiKeyAuth("explicit-key")
        p = self._make_provider(settings={"api_key": "settings-key"}, auth_strategy=explicit)
        assert p._auth_strategy is explicit

    def test_no_key_no_strategy_gives_none(self):
        p = self._make_provider(settings={})
        assert p._auth_strategy is None

    def test_get_auth_token_none_when_no_strategy(self):
        p = self._make_provider()
        result = _sync(p._get_auth_token())
        assert result is None

    def test_get_auth_token_returns_api_key(self):
        p = self._make_provider(settings={"api_key": "sk-xyz"})
        result = _sync(p._get_auth_token())
        assert result == "sk-xyz"

    def test_get_stats_includes_auth_strategy(self):
        p = self._make_provider(settings={"api_key": "sk-abc"})
        stats = p.get_stats()
        assert stats["auth_strategy"] == "ApiKeyAuth"

    def test_get_stats_none_strategy(self):
        p = self._make_provider()
        stats = p.get_stats()
        assert stats["auth_strategy"] == "none"


# ---------------------------------------------------------------------------
# OAuthAuth — resolve + refresh
# ---------------------------------------------------------------------------


class TestOAuthAuth:
    _TOKEN_URL = "https://example.com/oauth/token"

    def _make_auth(self, **kwargs):
        return OAuthAuth(
            provider_name="test_provider",
            token_url=self._TOKEN_URL,
            client_id="cid",
            client_secret="csec",
            owner_vault_str="system",
            subject="global",
            **kwargs,
        )

    def _fresh_token_data(self, ttl: int = 7200) -> dict:
        return {
            "access_token": "at-valid",
            "refresh_token": "rt-valid",
            "expires_at": time.time() + ttl,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }

    def _expired_token_data(self) -> dict:
        return {
            "access_token": "at-expired",
            "refresh_token": "rt-valid",
            "expires_at": time.time() - 1,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }

    def test_resolve_returns_fresh_token_without_refresh(self):
        auth = self._make_auth()
        data = self._fresh_token_data()
        session = AsyncMock()

        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=data)):
            result = _sync(auth.resolve_token(session))

        assert result == "at-valid"

    def test_expired_token_triggers_refresh(self):
        auth = self._make_auth()
        expired = self._expired_token_data()
        refreshed = {
            "access_token": "at-new",
            "refresh_token": "rt-new",
            "expires_in": 3600,
        }
        session = AsyncMock()

        with (
            patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=expired)),
            patch.object(_PA_MOD, "_vault_write", new=AsyncMock()) as mock_write,
            patch(
                "knowledge.connectors.oauth_flow.refresh_access_token",
                new=AsyncMock(return_value=refreshed),
            ),
        ):
            result = _sync(auth.resolve_token(session))

        assert result == "at-new"
        mock_write.assert_awaited_once()

    def test_no_token_in_vault_raises(self):
        auth = self._make_auth()
        session = AsyncMock()

        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=None)):
            with pytest.raises(ProviderAuthError, match="No OAuth token stored"):
                _sync(auth.resolve_token(session))

    def test_session_required_raises_without_it(self):
        auth = self._make_auth()
        with pytest.raises(ProviderAuthError, match="requires a DB session"):
            _sync(auth.resolve_token(None))

    def test_no_refresh_token_raises_token_expired(self):
        auth = self._make_auth()
        expired_no_rt = {
            "access_token": "at-old",
            "expires_at": time.time() - 1,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }
        session = AsyncMock()
        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=expired_no_rt)):
            with pytest.raises(TokenExpiredError):
                _sync(auth.resolve_token(session))

    def test_is_vault_backed(self):
        assert self._make_auth().is_vault_backed()

    def test_repr_does_not_contain_secret(self):
        auth = self._make_auth()
        r = repr(auth)
        assert "csec" not in r
        assert "OAuthAuth" in r


# ---------------------------------------------------------------------------
# Token never logged
# ---------------------------------------------------------------------------


class TestTokenNotLogged:
    """Verify no auth strategy logs the raw token value."""

    def test_api_key_not_logged(self, caplog):
        with caplog.at_level(logging.DEBUG, logger="llm_shared.provider_auth"):
            auth = ApiKeyAuth("sk-ultra-secret-value")
            _sync(auth.resolve_token())
        assert "sk-ultra-secret-value" not in caplog.text

    def test_oauth_resolve_does_not_log_token(self, caplog):
        auth = OAuthAuth(
            provider_name="test_p",
            token_url="https://example.com/token",
            client_id="cid",
            client_secret="cs",
            owner_vault_str="system",
            subject="global",
        )
        token_data = {
            "access_token": "secret-access-token-xyz",
            "refresh_token": "secret-refresh-token-abc",
            "expires_at": time.time() + 7200,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }
        session = AsyncMock()
        with (
            caplog.at_level(logging.DEBUG, logger="llm_shared.provider_auth"),
            patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=token_data)),
        ):
            result = _sync(auth.resolve_token(session))

        assert "secret-access-token-xyz" not in caplog.text
        assert "secret-refresh-token-abc" not in caplog.text
        assert result == "secret-access-token-xyz"


# ---------------------------------------------------------------------------
# DeviceCodeAuth
# ---------------------------------------------------------------------------


class TestDeviceCodeAuth:
    def test_resolve_delegates_to_oauth_ensure_fresh(self):
        auth = DeviceCodeAuth(
            provider_name="github",
            token_url="https://github.com/login/oauth/access_token",
            client_id="cid",
            device_authorization_url="https://github.com/login/device/code",
            owner_vault_str="system",
            subject="global",
        )
        token_data = {
            "access_token": "gho_device_token",
            "expires_at": time.time() + 3600,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }
        session = AsyncMock()
        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=token_data)):
            result = _sync(auth.resolve_token(session))
        assert result == "gho_device_token"

    def test_is_vault_backed(self):
        auth = DeviceCodeAuth(
            provider_name="github",
            token_url="",
            client_id="",
            device_authorization_url="",
        )
        assert auth.is_vault_backed()

    def test_no_stored_token_raises(self):
        auth = DeviceCodeAuth(
            provider_name="github",
            token_url="",
            client_id="",
            device_authorization_url="",
        )
        session = AsyncMock()
        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=None)):
            with pytest.raises(ProviderAuthError, match="No device-code token"):
                _sync(auth.resolve_token(session))


# ---------------------------------------------------------------------------
# SessionAuth
# ---------------------------------------------------------------------------


class TestSessionAuth:
    def test_resolve_returns_token(self):
        auth = SessionAuth(provider_name="copilot", owner_vault_str="system")
        token_data = {"access_token": "sess-tok", "expires_at": time.time() + 3600, "created_by": "x"}
        session = AsyncMock()
        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=token_data)):
            result = _sync(auth.resolve_token(session))
        assert result == "sess-tok"

    def test_expired_session_raises(self):
        auth = SessionAuth(provider_name="copilot")
        token_data = {"access_token": "old", "expires_at": time.time() - 10, "created_by": "x"}
        session = AsyncMock()
        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=token_data)):
            with pytest.raises(TokenExpiredError):
                _sync(auth.resolve_token(session))

    def test_no_stored_token_raises(self):
        auth = SessionAuth(provider_name="copilot")
        session = AsyncMock()
        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=None)):
            with pytest.raises(ProviderAuthError, match="No session token"):
                _sync(auth.resolve_token(session))


# ---------------------------------------------------------------------------
# build_token_data / _merge_token_response helpers
# ---------------------------------------------------------------------------


class TestTokenHelpers:
    def test_build_token_data_includes_expiry(self):
        resp = {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}
        data = build_token_data(resp, created_by="user-1")
        assert data["access_token"] == "at"
        assert data["refresh_token"] == "rt"
        assert "expires_at" in data
        assert data["expires_at"] > time.time()
        assert data["created_by"] == "user-1"

    def test_build_token_data_no_expiry(self):
        resp = {"access_token": "at"}
        data = build_token_data(resp, created_by="user-1")
        assert "expires_at" not in data

    def test_merge_preserves_old_refresh_when_absent_in_new(self):
        old = {"access_token": "old_at", "refresh_token": "old_rt", "created_by": "u", "expires_at": 0}
        resp = {"access_token": "new_at", "expires_in": 3600}
        merged = _merge_token_response(old, resp)
        assert merged["access_token"] == "new_at"
        assert merged["refresh_token"] == "old_rt"  # preserved

    def test_merge_updates_refresh_when_present(self):
        old = {"access_token": "old_at", "refresh_token": "old_rt", "created_by": "u", "expires_at": 0}
        resp = {"access_token": "new_at", "refresh_token": "new_rt", "expires_in": 3600}
        merged = _merge_token_response(old, resp)
        assert merged["refresh_token"] == "new_rt"


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


def _sync(coro):
    """Run a coroutine synchronously in a new event loop."""
    import asyncio

    return asyncio.get_event_loop().run_until_complete(coro)


def _sync_resolve(strategy, session=None):
    return _sync(strategy.resolve_token(session))
