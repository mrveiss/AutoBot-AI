# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Endpoint tests for connector OAuth authorize + callback (ADR-007 / GH#9019)."""

from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import knowledge_connector_oauth as mod
from auth_middleware import get_current_user
from knowledge.connectors import oauth_flow


class _FakeRedis:
    """Minimal in-memory redis supporting set(ex=) and getdel()."""

    def __init__(self):
        self.store = {}

    def set(self, key, value, ex=None):
        self.store[key] = value
        return True

    def get(self, key):
        return self.store.get(key)

    def getdel(self, key):
        return self.store.pop(key, None)

    def delete(self, key):
        return 1 if self.store.pop(key, None) is not None else 0


@pytest.fixture
def client(monkeypatch):
    fake_redis = _FakeRedis()
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
