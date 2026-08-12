# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Endpoint tests for connector OAuth authorize + callback (ADR-007 / GH#9019)."""

import json
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_connector_oauth as mod
from auth_middleware import get_current_user
from knowledge.connectors import oauth_flow


@pytest.fixture
def client(monkeypatch, single_use_fake_redis):
    # Shared single-use-state Redis stub (conftest fixture — #11699).
    fake_redis = single_use_fake_redis
    monkeypatch.setattr(mod, "get_redis_client", lambda database=None: fake_redis)
    # Provider configured.
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_id", "cid", raising=False)
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_secret", "csec", raising=False)

    app = FastAPI()
    # Mount under /api to match production (app factory prepends /api); the
    # state-binding cookie is path-scoped to the real callback path.
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "user-42"}
    return TestClient(app), fake_redis


_AUTHZ = "/api/knowledge_base/connectors/oauth/{p}/authorize"
_CALLBACK = "/api/knowledge_base/connectors/oauth/callback"


@pytest.mark.parametrize(
    "user_dict,expected_owner",
    [
        ({"user_id": "user-42"}, "user-42"),
        # SLM-minted JWTs carry ``sub``; _extract_user_from_jwt sets user_id only
        # when the token has that claim, so these users have no user_id at all.
        ({"sub": "user-sub-7", "username": "alice"}, "user-sub-7"),
        # Internal API key path returns username/role/service and no id.
        ({"username": "service:slm", "role": "admin", "service": True}, "service:slm"),
        # Dev X-User-Role header path.
        ({"username": "dev_admin", "role": "admin", "auth_method": "development"}, "dev_admin"),
    ],
)
def test_authorize_resolves_owner_from_any_identity_claim(
    monkeypatch, single_use_fake_redis, user_dict, expected_owner
):
    """#13628: get_current_user does not guarantee ``user_id``.

    Requiring it alone would 401 the internal-API-key, dev-header and
    ``sub``-only JWT callers, all of which authenticate fine everywhere else.
    Identity is resolved as user_id -> sub -> username, matching api/voice.py
    and api/agent_terminal.py, and the stored owner must be that identity —
    never a shared literal.
    """
    fake_redis = single_use_fake_redis
    monkeypatch.setattr(mod, "get_redis_client", lambda database=None: fake_redis)
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_id", "cid", raising=False)
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_secret", "csec", raising=False)

    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: user_dict
    tc = TestClient(app)

    resp = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://localhost/cb"})
    assert resp.status_code == 200, resp.text

    state = resp.json()["state"]
    key = next(k for k in fake_redis.store if k.endswith(state))
    stored = json.loads(fake_redis.store[key])
    assert stored["owner_id"] == expected_owner
    assert stored["owner_id"] != "system", "shared literal owner reintroduced"


def test_authorize_rejects_a_caller_with_no_identity(monkeypatch, single_use_fake_redis):
    """#13628: only a caller with no resolvable identity at all is refused."""
    fake_redis = single_use_fake_redis
    monkeypatch.setattr(mod, "get_redis_client", lambda database=None: fake_redis)
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_id", "cid", raising=False)
    monkeypatch.setattr(oauth_flow.config.auth, "google_oauth_client_secret", "csec", raising=False)

    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: {"role": "admin"}
    tc = TestClient(app)

    resp = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://localhost/cb"})
    assert resp.status_code == 401, resp.text


def test_authorize_returns_url_and_persists_state(client):
    tc, fake_redis = client
    resp = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://localhost/cb"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    qs = parse_qs(urlparse(data["authorize_url"]).query)
    assert qs["client_id"] == ["cid"]
    assert qs["state"] == [data["state"]]
    assert qs["code_challenge_method"] == ["S256"]
    # State persisted server-side for the callback to consume.
    assert any(k.endswith(data["state"]) for k in fake_redis.store)
    # State-binding cookie issued for the completing browser (CSRF defense).
    assert "connector_oauth_state" in resp.cookies


def test_authorize_unknown_provider_404(client):
    tc, _ = client
    resp = tc.post(_AUTHZ.format(p="bogus"), json={"redirect_uri": "https://localhost/cb"})
    assert resp.status_code == 404


def test_authorize_unconfigured_provider_400(client, monkeypatch):
    tc, _ = client
    monkeypatch.setattr(oauth_flow.config.auth, "gitlab_oauth_client_id", "", raising=False)
    monkeypatch.setattr(oauth_flow.config.auth, "gitlab_oauth_client_secret", "", raising=False)
    resp = tc.post(_AUTHZ.format(p="gitlab"), json={"redirect_uri": "https://localhost/cb"})
    assert resp.status_code == 400


def test_authorize_rejects_unlisted_redirect_host(client):
    tc, _ = client
    resp = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://evil.example.com/cb"})
    assert resp.status_code == 400


def test_callback_exchanges_and_stores(client, monkeypatch):
    tc, fake_redis = client
    # Start a flow to mint valid state + binding cookie (carried by the client).
    start = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://localhost/cb"}).json()
    state = start["state"]

    async def _fake_exchange(provider, client_id, client_secret, code, redirect_uri, code_verifier):
        assert code == "auth-code"
        return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}

    stored = {}

    class _FakeStore:
        async def store_oauth(self, **kwargs):
            stored.update(kwargs)
            return "secret-xyz"

    monkeypatch.setattr(oauth_flow, "exchange_code", _fake_exchange)
    monkeypatch.setattr(mod, "get_credential_store", lambda: _FakeStore())

    resp = tc.get(f"{_CALLBACK}?state={state}&code=auth-code")
    assert resp.status_code == 200
    assert "secret-xyz" in resp.text  # passed to opener via postMessage payload
    assert stored["owner_id"] == "user-42"
    assert stored["provider"] == "google"
    # State is single-use: consumed on callback.
    assert not any(k.endswith(state) for k in fake_redis.store)


def test_callback_rejects_missing_binding_cookie(client):
    """A fresh browser (no binding cookie) cannot complete someone else's flow."""
    tc, fake_redis = client
    # Seed a valid state in redis but provide no matching cookie.
    fake_redis.store["connector:oauth:state:ghost"] = "{}"
    resp = tc.get(f"{_CALLBACK}?state=ghost&code=x")
    assert resp.status_code == 200
    assert "state_binding_mismatch" in resp.text
    # State NOT consumed — the CSRF check fires before touching redis.
    assert "connector:oauth:state:ghost" in fake_redis.store


def test_callback_expired_state_returns_error_page(client):
    tc, fake_redis = client
    state = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://localhost/cb"}).json()["state"]
    fake_redis.store.clear()  # simulate state expiry; cookie still present
    resp = tc.get(f"{_CALLBACK}?state={state}&code=x")
    assert resp.status_code == 200
    assert "invalid_or_expired_state" in resp.text


def test_callback_provider_error_passthrough(client):
    tc, _ = client
    state = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://localhost/cb"}).json()["state"]
    resp = tc.get(f"{_CALLBACK}?state={state}&error=access_denied")
    assert resp.status_code == 200
    assert "access_denied" in resp.text


def test_callback_escapes_reflected_error_xss(client):
    """A malicious provider error param cannot break out of the result HTML/JS."""
    tc, _ = client
    state = tc.post(_AUTHZ.format(p="google"), json={"redirect_uri": "https://localhost/cb"}).json()["state"]
    resp = tc.get(_CALLBACK, params={"state": state, "error": "</script><img src=x onerror=alert(1)>"})
    assert resp.status_code == 200
    # No raw closing-script or tag injection survives.
    assert "</script><img" not in resp.text
    assert "<img src=x" not in resp.text
