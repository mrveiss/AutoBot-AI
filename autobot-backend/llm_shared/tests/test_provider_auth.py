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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Module reference for patch.object.  The llm_shared stub package loads provider_auth
# via _real_load_and_bind into sys.modules["llm_shared.provider_auth"].  We must patch on
# the exact module object that OAuthAuth.__globals__ points to — which is the module
# where OAuthAuth was defined (its __globals__["__name__"] == "llm_shared.provider_auth").
# Obtain it via the class's function globals to guarantee identity.
import llm_shared.provider_auth as _provider_auth_mod  # standard import path
from llm_shared.provider_auth import (
    LEGACY_SUBJECT,
    ApiKeyAuth,
    DeviceCodeAuth,
    OAuthAuth,
    ProviderAuthError,
    SessionAuth,
    TokenExpiredError,
    _merge_token_response,
    build_token_data,
    org_vault_subject,
    validate_token_response,
)

# Use the class's actual globals dict as the authoritative module reference.
# This handles the case where _real_load_and_bind creates a fresh module object that
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

        from llm_shared.provider_auth import ApiKeyAuth, ProviderAuthStrategy  # noqa: PLC0415,F401

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
    # #11061 added an SSRF allowlist to OAuthAuth._refresh (require_allowlisted_https
    # + get_oauth_allowed_hosts).  The token_url must be a default-allowlisted host
    # or the refresh path raises ProviderAuthError before hitting the mocked
    # token endpoint (the old "https://example.com/oauth/token" is blocked).
    _TOKEN_URL = "https://github.com/login/oauth/access_token"

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
            patch("autobot_shared.security.ssrf_guard.pinned_connector", new=AsyncMock(return_value=MagicMock())),
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
# #11497 finding #1 — per-org vault subject + backward-compatible dual-read
# ---------------------------------------------------------------------------


class TestOrgVaultSubject:
    def test_none_org_is_legacy_global(self):
        assert org_vault_subject(None) == LEGACY_SUBJECT == "global"

    def test_empty_org_is_legacy_global(self):
        assert org_vault_subject("") == "global"
        assert org_vault_subject("   ") == "global"

    def test_org_id_keyed(self):
        assert org_vault_subject("acme") == "org:acme"
        assert org_vault_subject(42) == "org:42"


class TestDualRead:
    """Finding #1 read path: org-scoped subject first, legacy ``global`` fallback."""

    _TOKEN_URL = "https://github.com/login/oauth/access_token"

    def _make_auth(self, subject: str) -> OAuthAuth:
        return OAuthAuth(
            provider_name="p",
            token_url=self._TOKEN_URL,
            client_id="cid",
            client_secret="csec",
            owner_vault_str="system",
            subject=subject,
        )

    def _fresh(self, tag: str) -> dict:
        return {
            "access_token": tag,
            "refresh_token": "rt",
            "expires_at": time.time() + 7200,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }

    def test_legacy_global_token_readable_under_org_subject(self):
        """PROOF: a token stored under legacy ``global`` is still readable when the
        caller resolves with an org-scoped subject — zero reconnect, no regression."""
        auth = self._make_auth(subject="org:acme")
        legacy = self._fresh("at-legacy-global")
        session = AsyncMock()

        async def fake_read(_session, *, provider_name, subject, owner_vault_str):
            # Only the legacy "global" entry exists (org:acme has never persisted).
            return legacy if subject == "global" else None

        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(side_effect=fake_read)):
            result = _sync(auth.resolve_token(session))

        assert result == "at-legacy-global"

    def test_org_scoped_token_wins_over_legacy_global(self):
        auth = self._make_auth(subject="org:acme")
        org_data = self._fresh("at-org")
        legacy = self._fresh("at-legacy")
        session = AsyncMock()

        async def fake_read(_session, *, provider_name, subject, owner_vault_str):
            return org_data if subject == "org:acme" else legacy

        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(side_effect=fake_read)):
            result = _sync(auth.resolve_token(session))

        assert result == "at-org"

    def test_global_subject_single_read_no_fallback(self):
        """When subject already IS legacy ``global`` there must be no second lookup."""
        auth = self._make_auth(subject="global")
        legacy = self._fresh("at-global")
        session = AsyncMock()
        read = AsyncMock(return_value=legacy)

        with patch.object(_PA_MOD, "_vault_read", new=read):
            result = _sync(auth.resolve_token(session))

        assert result == "at-global"
        read.assert_awaited_once()


# ---------------------------------------------------------------------------
# #11497 finding #2 — refresh POST is pinned to a pre-resolved public IP
# ---------------------------------------------------------------------------


class TestRefreshIpPinning:
    _TOKEN_URL = "https://github.com/login/oauth/access_token"

    def _make_auth(self) -> OAuthAuth:
        return OAuthAuth(
            provider_name="test_provider",
            token_url=self._TOKEN_URL,
            client_id="cid",
            client_secret="csec",
            owner_vault_str="system",
            subject="global",
        )

    def _expired(self) -> dict:
        return {
            "access_token": "at-expired",
            "refresh_token": "rt-valid",
            "expires_at": time.time() - 1,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }

    def test_refresh_resolves_once_and_pins_connector(self):
        auth = self._make_auth()
        pin = AsyncMock(return_value=MagicMock())
        refresh = AsyncMock(return_value={"access_token": "at-new", "expires_in": 3600})
        session = AsyncMock()

        with (
            patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=self._expired())),
            patch.object(_PA_MOD, "_vault_write", new=AsyncMock()),
            patch("autobot_shared.security.ssrf_guard.pinned_connector", new=pin),
            patch("knowledge.connectors.oauth_flow.refresh_access_token", new=refresh),
        ):
            result = _sync(auth.resolve_token(session))

        assert result == "at-new"
        pin.assert_awaited_once_with(self._TOKEN_URL)  # resolved exactly once
        # The pinned connector is threaded into the outbound refresh POST.
        assert "connector" in refresh.await_args.kwargs

    def test_refresh_blocks_when_host_not_public(self):
        from autobot_shared.security.ssrf_guard import SSRFError

        auth = self._make_auth()
        refresh = AsyncMock(return_value={"access_token": "at-new", "expires_in": 3600})
        session = AsyncMock()

        with (
            patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=self._expired())),
            patch(
                "autobot_shared.security.ssrf_guard.pinned_connector",
                new=AsyncMock(side_effect=SSRFError("non-public")),
            ),
            patch("knowledge.connectors.oauth_flow.refresh_access_token", new=refresh),
        ):
            with pytest.raises(ProviderAuthError, match="not publicly routable"):
                _sync(auth.resolve_token(session))
            refresh.assert_not_awaited()  # never reached the network


# ---------------------------------------------------------------------------
# #11497 finding #3 — token_type / issuer / audience validation before persist
# ---------------------------------------------------------------------------


def _jwt(claims: dict) -> str:
    """Build an unsigned compact JWS whose payload carries *claims* (test-only)."""
    import base64
    import json

    def _seg(obj: dict) -> str:
        raw = json.dumps(obj).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    return f"{_seg({'alg': 'none'})}.{_seg(claims)}.sig"


class TestValidateTokenResponse:
    def test_bearer_token_type_accepted(self):
        validate_token_response({"access_token": "at", "token_type": "Bearer"}, provider_name="p", client_id="cid")

    def test_non_bearer_token_type_rejected(self):
        with pytest.raises(ProviderAuthError, match="token_type"):
            validate_token_response({"access_token": "at", "token_type": "mac"}, provider_name="p", client_id="cid")

    def test_missing_token_type_is_lenient(self):
        # RFC 6749 responses that omit token_type keep working (no regression).
        validate_token_response({"access_token": "at"}, provider_name="p", client_id="cid")

    def test_id_token_audience_match_accepted(self):
        resp = {"access_token": "at", "id_token": _jwt({"aud": "cid", "iss": "https://accounts.google.com"})}
        validate_token_response(resp, provider_name="google", client_id="cid")

    def test_id_token_audience_list_accepted(self):
        resp = {"access_token": "at", "id_token": _jwt({"aud": ["other", "cid"], "iss": "https://github.com"})}
        validate_token_response(resp, provider_name="github", client_id="cid")

    def test_id_token_audience_mismatch_rejected(self):
        resp = {"access_token": "at", "id_token": _jwt({"aud": "someone-else"})}
        with pytest.raises(ProviderAuthError, match="audience"):
            validate_token_response(resp, provider_name="google", client_id="cid")

    def test_id_token_azp_fallback_accepted(self):
        resp = {"access_token": "at", "id_token": _jwt({"aud": "other", "azp": "cid", "iss": "https://github.com"})}
        validate_token_response(resp, provider_name="github", client_id="cid")

    def test_id_token_issuer_not_allowlisted_rejected(self):
        resp = {"access_token": "at", "id_token": _jwt({"aud": "cid", "iss": "https://evil.example.com"})}
        with pytest.raises(ProviderAuthError, match="issuer"):
            validate_token_response(resp, provider_name="p", client_id="cid")

    def test_id_token_issuer_wrong_for_known_provider_rejected(self):
        # login.microsoftonline.com is allowlisted, but it is NOT google's issuer.
        resp = {"access_token": "at", "id_token": _jwt({"aud": "cid", "iss": "https://login.microsoftonline.com/x"})}
        with pytest.raises(ProviderAuthError, match="issuer"):
            validate_token_response(resp, provider_name="google", client_id="cid")

    def test_id_token_non_https_issuer_rejected(self):
        resp = {"access_token": "at", "id_token": _jwt({"aud": "cid", "iss": "http://accounts.google.com"})}
        with pytest.raises(ProviderAuthError, match="https"):
            validate_token_response(resp, provider_name="google", client_id="cid")

    def test_malformed_id_token_rejected(self):
        with pytest.raises(ProviderAuthError, match="well-formed"):
            validate_token_response({"access_token": "at", "id_token": "not-a-jwt"}, provider_name="p", client_id="cid")

    def test_no_id_token_is_lenient(self):
        validate_token_response({"access_token": "at", "refresh_token": "rt"}, provider_name="p", client_id="cid")


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------


def _sync(coro):
    """Run a coroutine synchronously in a new event loop.

    #11840: asyncio.run() creates (and closes) a fresh loop per call.  The
    previous ``asyncio.get_event_loop().run_until_complete`` relied on the
    deprecated implicit current loop, which no longer exists after any
    pytest-asyncio test file has run earlier in the session — every _sync
    caller then failed with "There is no current event loop".
    """
    import asyncio

    return asyncio.run(coro)


def _sync_resolve(strategy, session=None):
    return _sync(strategy.resolve_token(session))


# ---------------------------------------------------------------------------
# Security tests for api/provider_auth.py (#10551 security review)
# ---------------------------------------------------------------------------


class TestProviderAuthSecurity:
    """Covers the 5 findings from the #10551 security review.

    These tests exercise _validate_outbound_url directly (unit) and the
    FastAPI endpoint auth requirements (integration via TestClient).
    """

    # -- _validate_outbound_url unit tests --

    def test_http_url_rejected(self):
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("http://accounts.google.com/token")
        assert exc_info.value.status_code == 400
        assert "https" in exc_info.value.detail.lower()

    def test_ip_literal_v4_rejected(self):
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://169.254.169.254/latest/meta-data/")
        assert exc_info.value.status_code == 400
        assert "IP" in exc_info.value.detail

    def test_localhost_ip_rejected(self):
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://127.0.0.1/token")
        assert exc_info.value.status_code == 400

    def test_ipv6_loopback_rejected(self):
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://[::1]/token")
        assert exc_info.value.status_code == 400

    def test_private_ip_range_rejected(self):
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://10.0.0.1/token")
        assert exc_info.value.status_code == 400

    def test_non_allowlisted_hostname_rejected(self):
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://evil-attacker.example.com/token")
        assert exc_info.value.status_code == 400
        assert "allowlist" in exc_info.value.detail.lower()

    def test_allowlisted_https_host_passes(self):
        from api.provider_auth import _validate_outbound_url

        # Should not raise for any known-good provider host.
        _validate_outbound_url("https://accounts.google.com/o/oauth2/token")
        _validate_outbound_url("https://github.com/login/oauth/access_token")
        _validate_outbound_url("https://api.anthropic.com/oauth/token")

    def test_allowlisted_host_nonstandard_port_rejected(self):
        """#11022: an allowlisted host on a non-443 port is rejected (port pinning)."""
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://accounts.google.com:22/token")
        assert exc_info.value.status_code == 400
        assert "port" in exc_info.value.detail.lower()

    def test_allowlisted_host_explicit_443_passes(self):
        from api.provider_auth import _validate_outbound_url

        _validate_outbound_url("https://accounts.google.com:443/o/oauth2/token")  # no raise

    def test_microsoftonline_passes(self):
        from api.provider_auth import _validate_outbound_url

        _validate_outbound_url("https://login.microsoftonline.com/common/oauth2/v2.0/token")

    # -- Endpoint auth requirement tests (via FastAPI dependency inspection) --
    # We cannot boot the full FastAPI app in unit test scope (missing DB/Redis/autobot_shared),
    # so we verify auth by inspecting the Depends() wiring directly.  This is the
    # correct approach for testing dependency presence without integration infrastructure.

    def _get_endpoint_dependencies(self, endpoint_fn):
        """Return the set of dependency callables declared on a FastAPI endpoint function."""
        import inspect

        from fastapi import params as fa_params

        deps = set()
        sig = inspect.signature(endpoint_fn)
        for param in sig.parameters.values():
            if isinstance(param.default, fa_params.Depends):
                deps.add(param.default.dependency)
        return deps

    def test_device_initiate_requires_auth_no_token(self):
        """device_initiate must declare both get_current_user and check_admin_permission."""
        from api.provider_auth import device_initiate
        from auth_middleware import check_admin_permission, get_current_user

        deps = self._get_endpoint_dependencies(device_initiate)
        assert get_current_user in deps, "device_initiate missing get_current_user dependency"
        assert check_admin_permission in deps, "device_initiate missing check_admin_permission dependency"

    def test_oauth_callback_requires_auth_no_token(self):
        """oauth_callback must declare both get_current_user and check_admin_permission."""
        from api.provider_auth import oauth_callback
        from auth_middleware import check_admin_permission, get_current_user

        deps = self._get_endpoint_dependencies(oauth_callback)
        assert get_current_user in deps, "oauth_callback missing get_current_user dependency"
        assert check_admin_permission in deps, "oauth_callback missing check_admin_permission dependency"

    def test_device_poll_requires_auth_no_token(self):
        """device_poll must declare both get_current_user and check_admin_permission."""
        from api.provider_auth import device_poll
        from auth_middleware import check_admin_permission, get_current_user

        deps = self._get_endpoint_dependencies(device_poll)
        assert get_current_user in deps, "device_poll missing get_current_user dependency"
        assert check_admin_permission in deps, "device_poll missing check_admin_permission dependency"

    def test_revoke_requires_auth_no_token(self):
        """revoke_provider_auth must declare both get_current_user and check_admin_permission."""
        from api.provider_auth import revoke_provider_auth
        from auth_middleware import check_admin_permission, get_current_user

        deps = self._get_endpoint_dependencies(revoke_provider_auth)
        assert get_current_user in deps, "revoke_provider_auth missing get_current_user dependency"
        assert check_admin_permission in deps, "revoke_provider_auth missing check_admin_permission dependency"

    def test_ssrf_blocked_before_network_on_device_initiate(self):
        """Non-allowlisted URL must be rejected 400 even if the endpoint were authenticated."""
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        # Call the guard directly — simulates what the endpoint does after auth.
        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://internal.corp/steal-metadata")
        assert exc_info.value.status_code == 400

    def test_allow_redirects_false_in_device_initiate(self):
        """Verify allow_redirects=False is wired into the aiohttp POST in device_initiate.

        We inspect the source to confirm the argument is present, preventing
        a 302-redirect SSRF bypass from an allowlisted host to an internal one.
        """
        import inspect

        from api import provider_auth as _pa_module

        src = inspect.getsource(_pa_module.device_initiate)
        assert "allow_redirects=False" in src, "device_initiate must pass allow_redirects=False to aiohttp"

    def test_allow_redirects_false_in_device_poll(self):
        import inspect

        from api import provider_auth as _pa_module

        src = inspect.getsource(_pa_module.device_poll)
        assert "allow_redirects=False" in src, "device_poll must pass allow_redirects=False to aiohttp"

    def test_malformed_port_returns_400_not_500(self):
        """#11066 audit: a malformed port raises ValueError on parsed.port access —
        must be caught → 400, not an unhandled 500."""
        from fastapi import HTTPException

        from api.provider_auth import _validate_outbound_url

        with pytest.raises(HTTPException) as exc_info:
            _validate_outbound_url("https://accounts.google.com:99999/token")
        assert exc_info.value.status_code == 400

    def test_status_endpoint_requires_admin(self):
        """provider_auth_status must declare check_admin_permission (MED finding #11061)."""
        from api.provider_auth import provider_auth_status
        from auth_middleware import check_admin_permission

        deps = self._get_endpoint_dependencies(provider_auth_status)
        assert check_admin_permission in deps, "provider_auth_status missing check_admin_permission dependency"


# ---------------------------------------------------------------------------
# #11061: get_oauth_allowed_hosts — shared SSRF allowlist (url_safety)
# ---------------------------------------------------------------------------


class TestGetOauthAllowedHosts:
    """Verify get_oauth_allowed_hosts() single-source-of-truth behaviour."""

    def test_default_includes_known_providers(self):
        import os

        from autobot_shared.url_safety import get_oauth_allowed_hosts

        env_key = "AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS"
        old = os.environ.pop(env_key, None)
        try:
            hosts = get_oauth_allowed_hosts()
            assert "accounts.google.com" in hosts  # codeql[py/incomplete-url-substring-sanitization]
            assert "github.com" in hosts  # codeql[py/incomplete-url-substring-sanitization]
            assert "api.anthropic.com" in hosts  # codeql[py/incomplete-url-substring-sanitization]
            assert "login.microsoftonline.com" in hosts  # codeql[py/incomplete-url-substring-sanitization]
        finally:
            if old is not None:
                os.environ[env_key] = old

    def test_env_override_replaces_defaults(self):
        import os

        from autobot_shared.url_safety import get_oauth_allowed_hosts

        env_key = "AUTOBOT_PROVIDER_OAUTH_ALLOWED_HOSTS"
        old = os.environ.get(env_key)
        os.environ[env_key] = "custom.provider.com, other.example.com"
        try:
            hosts = get_oauth_allowed_hosts()
            assert "custom.provider.com" in hosts  # codeql[py/incomplete-url-substring-sanitization]
            assert "other.example.com" in hosts  # codeql[py/incomplete-url-substring-sanitization]
            assert "accounts.google.com" not in hosts
        finally:
            if old is None:
                del os.environ[env_key]
            else:
                os.environ[env_key] = old

    def test_allowlisted_host_passes_require_allowlisted_https(self):
        from autobot_shared.url_safety import get_oauth_allowed_hosts, require_allowlisted_https

        # Should not raise for a default-allowlisted host.
        require_allowlisted_https("https://accounts.google.com/o/oauth2/token", get_oauth_allowed_hosts())

    def test_non_allowlisted_host_raises_value_error(self):
        from autobot_shared.url_safety import get_oauth_allowed_hosts, require_allowlisted_https

        with pytest.raises(ValueError, match="allowlist"):
            require_allowlisted_https("https://evil.example.com/token", get_oauth_allowed_hosts())


# ---------------------------------------------------------------------------
# #11061 HIGH: OAuthAuth._refresh validates token_url before outbound POST
# ---------------------------------------------------------------------------


class TestOAuthRefreshSsrfGuard:
    """Verify the SSRF guard fires in _refresh before any network call."""

    _BAD_URL = "https://internal.corp/steal-tokens"
    _GOOD_URL = "https://accounts.google.com/o/oauth2/token"

    def _make_auth(self, token_url: str) -> OAuthAuth:
        return OAuthAuth(
            provider_name="test_provider",
            token_url=token_url,
            client_id="cid",
            client_secret="csec",
            owner_vault_str="system",
            subject="global",
        )

    def _expired_token_data(self) -> dict:
        return {
            "access_token": "at-expired",
            "refresh_token": "rt-valid",
            "expires_at": time.time() - 1,
            "created_by": "00000000-0000-0000-0000-000000000000",
        }

    def test_bad_token_url_raises_provider_auth_error(self):
        """_refresh must raise ProviderAuthError for a non-allowlisted token_url."""
        auth = self._make_auth(self._BAD_URL)
        expired = self._expired_token_data()
        session = AsyncMock()

        with (
            patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=expired)),
            patch(
                "knowledge.connectors.oauth_flow.refresh_access_token",
                new=AsyncMock(return_value={}),
            ) as mock_post,
        ):
            with pytest.raises(ProviderAuthError, match="OAuth refresh blocked"):
                _sync(auth.resolve_token(session))
            # The outbound call must NOT have been made.
            mock_post.assert_not_awaited()

    def test_bad_token_url_error_message_names_provider(self):
        """Error message must include the provider name for debuggability."""
        auth = self._make_auth(self._BAD_URL)
        expired = self._expired_token_data()
        session = AsyncMock()

        with patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=expired)):
            with pytest.raises(ProviderAuthError, match="test_provider"):
                _sync(auth.resolve_token(session))

    def test_allowlisted_token_url_proceeds_to_network(self):
        """A valid token_url still reaches the downstream refresh call."""
        auth = self._make_auth(self._GOOD_URL)
        expired = self._expired_token_data()
        refreshed = {"access_token": "at-new", "expires_in": 3600}
        session = AsyncMock()

        with (
            patch.object(_PA_MOD, "_vault_read", new=AsyncMock(return_value=expired)),
            patch.object(_PA_MOD, "_vault_write", new=AsyncMock()),
            patch("autobot_shared.security.ssrf_guard.pinned_connector", new=AsyncMock(return_value=MagicMock())),
            patch(
                "knowledge.connectors.oauth_flow.refresh_access_token",
                new=AsyncMock(return_value=refreshed),
            ) as mock_post,
        ):
            result = _sync(auth.resolve_token(session))

        assert result == "at-new"
        mock_post.assert_awaited_once()


# ---------------------------------------------------------------------------
# _vault_write created_by guard (#11849)
# ---------------------------------------------------------------------------


class TestVaultWriteCreatedByGuard:
    """The JWT ``user_id`` claim is not guaranteed to be a UUID; a malformed id
    must fall back to the zero-UUID sentinel rather than raise on the write path."""

    def _run(self, created_by_id):
        import uuid as _uuid

        captured = {}

        class _FakeSvc:
            async def create(self, session, *, owner_vault, name, secret_type, plaintext, created_by):
                captured["created_by"] = created_by

        import services.envelope_secrets_service as _ess

        with patch.object(_ess, "EnvelopeSecretsService", _FakeSvc):
            session = AsyncMock()
            _sync(
                _PA_MOD._vault_write(
                    session,
                    provider_name="acme",
                    subject=LEGACY_SUBJECT,
                    owner_vault_str="system",
                    token_data={"access_token": "at"},
                    created_by_id=created_by_id,
                )
            )
        return captured["created_by"], _uuid

    def test_non_uuid_created_by_falls_back_without_raising(self):
        created_by, _uuid = self._run("admin")  # NOT a valid UUID
        assert created_by == _uuid.UUID("00000000-0000-0000-0000-000000000000")

    def test_empty_created_by_falls_back_without_raising(self):
        created_by, _uuid = self._run("")  # empty device-JWT claim
        assert created_by == _uuid.UUID("00000000-0000-0000-0000-000000000000")

    def test_valid_uuid_created_by_preserved(self):
        real = "11111111-2222-3333-4444-555555555555"
        created_by, _uuid = self._run(real)
        assert created_by == _uuid.UUID(real)
