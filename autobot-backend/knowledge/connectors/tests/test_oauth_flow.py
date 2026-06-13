# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for the generic connector OAuth flow (ADR-007 / GH#9019)."""

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import pytest

from knowledge.connectors import oauth_flow

# ---------------------------------------------------------------------------
# Provider registry
# ---------------------------------------------------------------------------


def test_get_provider_known():
    p = oauth_flow.get_provider("google")
    assert p.name == "google"
    assert p.token_url.startswith("https://")


def test_get_provider_unknown_raises():
    with pytest.raises(KeyError):
        oauth_flow.get_provider("does-not-exist")


def test_resolve_client_credentials_unconfigured_raises(monkeypatch):
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_id", "", raising=False)
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_secret", "", raising=False)
    with pytest.raises(ValueError):
        oauth_flow.resolve_client_credentials(oauth_flow.get_provider("google"))


def test_resolve_client_credentials_configured(monkeypatch):
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_id", "cid", raising=False)
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_secret", "csec", raising=False)
    cid, csec = oauth_flow.resolve_client_credentials(oauth_flow.get_provider("google"))
    assert (cid, csec) == ("cid", "csec")


# ---------------------------------------------------------------------------
# PKCE / state
# ---------------------------------------------------------------------------


def test_generate_pkce_is_valid_s256():
    verifier, challenge = oauth_flow.generate_pkce()
    # RFC 7636: 43..128 chars for the verifier.
    assert 43 <= len(verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest()).decode().rstrip("=")
    assert challenge == expected
    assert "=" not in challenge


def test_generate_pkce_unique():
    assert oauth_flow.generate_pkce()[0] != oauth_flow.generate_pkce()[0]


def test_generate_state_unique():
    assert oauth_flow.generate_state() != oauth_flow.generate_state()


# ---------------------------------------------------------------------------
# Authorize URL
# ---------------------------------------------------------------------------


def test_build_authorize_url_contains_required_params():
    provider = oauth_flow.get_provider("google")
    url = oauth_flow.build_authorize_url(
        provider,
        client_id="cid",
        redirect_uri="https://app.example.com/cb",
        state="st8",
        code_challenge="chal",
    )
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert qs["client_id"] == ["cid"]
    assert qs["response_type"] == ["code"]
    assert qs["redirect_uri"] == ["https://app.example.com/cb"]
    assert qs["state"] == ["st8"]
    assert qs["code_challenge"] == ["chal"]
    assert qs["code_challenge_method"] == ["S256"]
    # Google-specific: guarantees a refresh token.
    assert qs["access_type"] == ["offline"]
    assert qs["prompt"] == ["consent"]
    # Default scope applied when none supplied.
    assert "drive.readonly" in qs["scope"][0]


def test_build_authorize_url_custom_scopes_override_defaults():
    provider = oauth_flow.get_provider("gitlab")
    url = oauth_flow.build_authorize_url(
        provider,
        client_id="cid",
        redirect_uri="https://app/cb",
        state="s",
        code_challenge="c",
        scopes=("read_user",),
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["scope"] == ["read_user"]


# ---------------------------------------------------------------------------
# Token exchange / refresh
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exchange_code_posts_expected_payload(monkeypatch):
    captured = {}

    async def _fake_post(token_url, payload):
        captured["url"] = token_url
        captured["payload"] = payload
        return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}

    monkeypatch.setattr(oauth_flow, "_post_token", _fake_post)
    provider = oauth_flow.get_provider("google")
    result = await oauth_flow.exchange_code(
        provider, "cid", "csec", code="abc", redirect_uri="https://app/cb", code_verifier="ver"
    )
    assert result["access_token"] == "at"
    assert captured["url"] == provider.token_url
    assert captured["payload"]["grant_type"] == "authorization_code"
    assert captured["payload"]["code"] == "abc"
    assert captured["payload"]["code_verifier"] == "ver"


@pytest.mark.asyncio
async def test_refresh_access_token_posts_expected_payload(monkeypatch):
    captured = {}

    async def _fake_post(token_url, payload):
        captured["payload"] = payload
        return {"access_token": "fresh", "expires_in": 3600}

    monkeypatch.setattr(oauth_flow, "_post_token", _fake_post)
    result = await oauth_flow.refresh_access_token("https://token", "cid", "csec", refresh_token="rt")
    assert result["access_token"] == "fresh"
    assert captured["payload"]["grant_type"] == "refresh_token"
    assert captured["payload"]["refresh_token"] == "rt"


@pytest.mark.asyncio
async def test_post_token_raises_on_http_error(monkeypatch):
    """_post_token surfaces token-endpoint errors as RuntimeError."""

    class _FakeResp:
        status = 400

        async def json(self, content_type=None):
            return {"error": "invalid_grant", "error_description": "bad code"}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _FakeSession:
        def __init__(self, *a, **k):
            pass

        def post(self, *a, **k):
            return _FakeResp()

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    monkeypatch.setattr(oauth_flow.aiohttp, "ClientSession", _FakeSession)
    with pytest.raises(RuntimeError, match="bad code"):
        await oauth_flow._post_token("https://token", {"grant_type": "authorization_code"})
