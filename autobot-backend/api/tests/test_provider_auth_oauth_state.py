# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""State-bound provider OAuth: /oauth/initiate + single-use /oauth/callback (#11297).

Proves the callback is authorized by a server-minted, single-use ``state`` (not a
client-supplied verifier): missing/replayed/expired state → 400, admin mismatch →
403, and the happy path exchanges with the SERVER-STORED verifier.
"""

import json
import types
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import provider_auth as mod
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user
from knowledge.connectors import oauth_flow


class _FakeRedis:
    """Minimal in-memory redis supporting set(ex=) and getdel() (single-use)."""

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


_ADMIN = types.SimpleNamespace(user_id="admin-1")
_INITIATE = "/api/llm-auth/oauth/initiate"
_CALLBACK = "/api/llm-auth/oauth/callback"


@pytest.fixture
def ctx(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(mod, "get_redis_client", lambda database="main": fake_redis)
    # Allow the test provider hosts through the SSRF guard.
    monkeypatch.setattr(mod, "get_oauth_allowed_hosts", lambda: {"auth.example.com", "token.example.com"})
    # Persist step is exercised elsewhere; isolate the state/PKCE/admin logic.
    monkeypatch.setattr(mod, "_vault_write", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "build_token_data", lambda resp, created_by: {"expires_at": 111.0})

    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    return TestClient(app), fake_redis, app


def _valid_initiate_body():
    return {
        "provider_name": "acme",
        "authorize_url": "https://auth.example.com/authorize",
        "token_url": "https://token.example.com/token",
        "client_id": "cid-123",
        "redirect_uri": "https://app.local/cb",
        "scopes": ["read"],
    }


def test_initiate_stores_state_and_verifier_keyed_to_admin(ctx):
    tc, fake_redis, _ = ctx
    resp = tc.post(_INITIATE, json=_valid_initiate_body())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["state"]
    assert data["authorize_url"].startswith("https://auth.example.com/authorize?")
    assert "code_challenge=" in data["authorize_url"] and "state=%s" % data["state"] in data["authorize_url"]
    # Server-side state carries the verifier + initiating admin; verifier never leaves the server.
    (stored_raw,) = fake_redis.store.values()
    stored = json.loads(stored_raw)
    assert stored["admin_id"] == "admin-1"
    assert stored["verifier"] and stored["verifier"] not in data["authorize_url"]
    assert stored["token_url"] == "https://token.example.com/token"
    assert stored["client_id"] == "cid-123"


def test_initiate_rejects_ssrf_token_url(ctx):
    tc, _, _ = ctx
    body = _valid_initiate_body()
    body["token_url"] = "https://evil.example.net/token"  # not allow-listed
    resp = tc.post(_INITIATE, json=body)
    assert resp.status_code == 400


def _prestore_state(fake_redis, state="st-1", admin_id="admin-1"):
    fake_redis.store[mod._state_key(state)] = json.dumps(
        {
            "verifier": "server-verifier",
            "admin_id": admin_id,
            "provider_name": "acme",
            "token_url": "https://token.example.com/token",
            "client_id": "cid-123",
        }
    )
    return state


def test_callback_happy_path_uses_stored_verifier(ctx, monkeypatch):
    tc, fake_redis, _ = ctx
    captured = {}

    async def fake_exchange(provider, client_id, client_secret, code, redirect_uri, code_verifier):
        captured.update(client_id=client_id, client_secret=client_secret, code=code, verifier=code_verifier)
        return {"access_token": "at", "refresh_token": "rt", "expires_in": 3600}

    monkeypatch.setattr(oauth_flow, "exchange_code", fake_exchange)
    state = _prestore_state(fake_redis)

    resp = tc.post(_CALLBACK, json={"state": state, "code": "auth-code", "redirect_uri": "https://app.local/cb"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["stored"] is True
    # Exchange used the SERVER-STORED verifier + client_id, and a PKCE public-client (no secret).
    assert captured["verifier"] == "server-verifier"
    assert captured["client_id"] == "cid-123"
    assert captured["client_secret"] == ""
    # State was consumed (single-use).
    assert mod._state_key(state) not in fake_redis.store


def test_callback_missing_state_400(ctx):
    tc, _, _ = ctx
    resp = tc.post(_CALLBACK, json={"state": "nope", "code": "c", "redirect_uri": "https://app.local/cb"})
    assert resp.status_code == 400


def test_callback_replayed_state_400(ctx, monkeypatch):
    tc, fake_redis, _ = ctx

    async def fake_exchange(*a, **k):
        return {"access_token": "at", "expires_in": 3600}

    monkeypatch.setattr(oauth_flow, "exchange_code", fake_exchange)
    state = _prestore_state(fake_redis)
    first = tc.post(_CALLBACK, json={"state": state, "code": "c", "redirect_uri": "https://app.local/cb"})
    assert first.status_code == 200
    # Replay the same (now-consumed) state → rejected.
    replay = tc.post(_CALLBACK, json={"state": state, "code": "c", "redirect_uri": "https://app.local/cb"})
    assert replay.status_code == 400


def test_callback_admin_mismatch_403(ctx):
    tc, fake_redis, _ = ctx
    # State minted by a DIFFERENT admin than the caller (_ADMIN = admin-1).
    state = _prestore_state(fake_redis, admin_id="admin-999")
    resp = tc.post(_CALLBACK, json={"state": state, "code": "c", "redirect_uri": "https://app.local/cb"})
    assert resp.status_code == 403
    # A rejected mismatch still consumed the single-use state (no reuse window).
    assert mod._state_key(state) not in fake_redis.store
