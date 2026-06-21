# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
TDD tests for POST /api/auth/logout.

Tests the logout business logic helpers directly (FastAPI decorator machinery
is a MagicMock in this test environment — see conftest; we test the pure
Python helpers and the integration points that are callable).

Covers:
- _build_end_session_url: returns URL from provider config
- _build_end_session_url: returns None when no end_session_endpoint
- _build_end_session_url: appends post_logout_redirect_uri and id_token_hint
- revoke_jti called with sane TTL when token is valid HS256
- SSO link lookup returns None for unlinked users
"""

import importlib.util
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_BACKEND = Path(__file__).parent.parent.parent
_ROOT = _BACKEND.parent
sys.path.insert(0, str(_BACKEND))
sys.path.insert(0, str(_ROOT))

# ---------------------------------------------------------------------------
# Module stubs — config first so auth.py loads with the right secret key
# ---------------------------------------------------------------------------
_SECRET_KEY = "test-logout-secret-key-32characters"
_EXPIRE_MINUTES = 30

_cfg_mod = MagicMock()
_cfg_mod.settings = MagicMock()
_cfg_mod.settings.secret_key = _SECRET_KEY
_cfg_mod.settings.access_token_expire_minutes = _EXPIRE_MINUTES
_cfg_mod.settings.trusted_proxies = []
sys.modules["config"] = _cfg_mod

for _mod_name in [
    "models.schemas",
    "user_management",
    "user_management.models",
    "user_management.models.user",
    "user_management.models.sso",
    "user_management.services",
    "user_management.database",
    "services.jwks_verifier",
    "services.database",
    "autobot_shared.proxy_utils",
    "fastapi",
    "fastapi.security",
    "sqlalchemy",
    "sqlalchemy.ext",
    "sqlalchemy.ext.asyncio",
    "sqlalchemy.orm",
    "models",
    "models.database",
    "api.security",
]:
    if _mod_name not in sys.modules:
        sys.modules[_mod_name] = MagicMock()

# Ensure real jwt_core is reachable (decode_jwt_no_verify_exp used in logout impl)
from autobot_shared.auth.jwt_core import decode_jwt_or_none  # noqa: E402

# ---------------------------------------------------------------------------
# Load real token_denylist
# ---------------------------------------------------------------------------
_DENYLIST_PY = _BACKEND / "services" / "token_denylist.py"
_dl_spec = importlib.util.spec_from_file_location("services.token_denylist", _DENYLIST_PY)
_dl_mod = importlib.util.module_from_spec(_dl_spec)  # type: ignore[arg-type]
_dl_spec.loader.exec_module(_dl_mod)  # type: ignore[union-attr]
sys.modules["services.token_denylist"] = _dl_mod  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Load real auth service (auth.py)
# ---------------------------------------------------------------------------
_AUTH_PY = _BACKEND / "services" / "auth.py"
_auth_spec = importlib.util.spec_from_file_location("services.auth", _AUTH_PY)
_auth_mod = importlib.util.module_from_spec(_auth_spec)  # type: ignore[arg-type]
_auth_spec.loader.exec_module(_auth_mod)  # type: ignore[union-attr]
sys.modules["services.auth"] = _auth_mod  # type: ignore[assignment]

# ---------------------------------------------------------------------------
# Load api/auth.py — router.post is a MagicMock so 'logout' is overwritten.
# We extract the helpers before decoration by loading the raw source
# via exec into a fresh namespace.
# ---------------------------------------------------------------------------
_AUTH_ROUTER_PY = _BACKEND / "api" / "auth.py"
_router_ns: dict = {
    "__name__": "api.auth_under_test",
    "__file__": str(_AUTH_ROUTER_PY),
}
# Inject the real helpers this module needs before exec
_router_ns.update(
    {
        "revoke_jti": _dl_mod.revoke_jti,
        "is_jti_revoked": _dl_mod.is_jti_revoked,
    }
)

# Execute the source so helper functions are defined in _router_ns
_router_src = _AUTH_ROUTER_PY.read_text(encoding="utf-8")
exec(compile(_router_src, str(_AUTH_ROUTER_PY), "exec"), _router_ns)  # nosec B102

_build_end_session_url = _router_ns["_build_end_session_url"]
_get_user_sso_link = _router_ns["_get_user_sso_link"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mint_token(username: str = "testuser") -> str:
    svc = _auth_mod.AuthService()
    return svc.create_access_token(data={"sub": username, "admin": False, "role": "user"})


def _mock_sso_link(end_session: str | None = None, post_logout: str | None = None, id_token: str | None = None):
    provider = MagicMock()
    provider.config = {}
    if end_session:
        provider.config["end_session_endpoint"] = end_session
    if post_logout:
        provider.config["post_logout_redirect_uri"] = post_logout
    link = MagicMock()
    link.provider = provider
    link.sso_metadata = {"id_token": id_token} if id_token else {}
    return link


# ---------------------------------------------------------------------------
# _build_end_session_url tests
# ---------------------------------------------------------------------------


class TestBuildEndSessionUrl:
    def test_returns_url_when_configured(self):
        link = _mock_sso_link(end_session="https://idp.example.com/logout")
        result = _build_end_session_url(link)
        assert result == "https://idp.example.com/logout"

    def test_returns_none_when_no_endpoint(self):
        link = _mock_sso_link()
        assert _build_end_session_url(link) is None

    def test_returns_none_when_link_is_none(self):
        assert _build_end_session_url(None) is None

    def test_appends_post_logout_redirect_uri(self):
        link = _mock_sso_link(
            end_session="https://idp.example.com/logout",
            post_logout="https://app.example.com/loggedout",
        )
        result = _build_end_session_url(link)
        assert result is not None
        # urlencode percent-encodes the value; check the key is present and value is encoded
        assert "post_logout_redirect_uri=" in result
        assert "app.example.com" in result

    def test_appends_id_token_hint_when_present(self):
        link = _mock_sso_link(
            end_session="https://idp.example.com/logout",
            id_token="eyJhbGciOiJSUzI1NiJ9.test",
        )
        result = _build_end_session_url(link)
        assert result is not None
        assert "id_token_hint=eyJhbGciOiJSUzI1NiJ9.test" in result

    def test_separator_is_ampersand_when_question_already_present(self):
        link = _mock_sso_link(
            end_session="https://idp.example.com/logout?client_id=abc",
            post_logout="https://app.example.com/done",
        )
        result = _build_end_session_url(link)
        assert result is not None
        assert "&post_logout_redirect_uri=" in result

    def test_post_logout_uri_with_special_chars_is_percent_encoded(self):
        """A post_logout_redirect_uri containing '&' and '=' must be percent-encoded."""
        link = _mock_sso_link(
            end_session="https://idp.example.com/logout",
            post_logout="https://app.example.com/done?foo=bar&baz=qux",
        )
        result = _build_end_session_url(link)
        assert result is not None
        # Raw '&' and '=' from the redirect URI must NOT appear unencoded in params
        assert "post_logout_redirect_uri=https%3A" in result
        assert "foo%3D" in result or "%26" in result


# ---------------------------------------------------------------------------
# _get_user_sso_link test (async DB mock)
# ---------------------------------------------------------------------------


class TestGetUserSsoLink:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_link(self):
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.scalar_one_or_none = MagicMock(return_value=None)
        mock_db.execute = AsyncMock(return_value=mock_row)

        result = await _get_user_sso_link(mock_db, "nolink_user")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_link_when_found(self):
        fake_link = MagicMock()
        mock_db = MagicMock()
        mock_row = MagicMock()
        mock_row.scalar_one_or_none = MagicMock(return_value=fake_link)
        mock_db.execute = AsyncMock(return_value=mock_row)

        result = await _get_user_sso_link(mock_db, "linked_user")
        assert result is fake_link


# ---------------------------------------------------------------------------
# revoke_jti integration: TTL derived from token exp
# ---------------------------------------------------------------------------


class TestRevokeTtlFromToken:
    @pytest.mark.asyncio
    async def test_revoke_called_with_positive_ttl(self):
        """revoke_jti must be called with ttl_seconds >= 1 for a fresh token."""
        token = _mint_token("alice")
        claims = decode_jwt_or_none(token, secret=_SECRET_KEY)
        assert claims is not None
        jti = claims["jti"]
        exp = int(claims["exp"])
        expected_ttl = max(1, exp - int(time.time()))

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock(return_value=True)
        get_client = AsyncMock(return_value=redis_mock)

        with patch.object(_dl_mod, "get_redis_client", get_client):
            await _dl_mod.revoke_jti(jti, ttl_seconds=expected_ttl)

        get_client.assert_called_once_with(async_client=True)
        redis_mock.set.assert_awaited_once()
        _, kwargs = redis_mock.set.call_args
        assert kwargs["ex"] >= 1
