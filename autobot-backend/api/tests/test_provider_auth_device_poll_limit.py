# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RFC-8628 server-side device-code poll limiter (#11061).

Proves /device/poll rejects too-fast polls and exhausted attempts (429) before
hitting the provider, and honors ``slow_down`` by backing the interval off +5s.
"""

import json
import time
import types
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import provider_auth as mod
from api.user_management.dependencies import get_db_session
from auth_middleware import check_admin_permission, get_current_user


class _FakeResp:
    def __init__(self, data):
        self._data = data

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def json(self, content_type=None):
        return self._data


class _FakeSession:
    """Stand-in for aiohttp.ClientSession returning a canned token response."""

    _data = {"error": "authorization_pending"}

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def post(self, *a, **k):
        return _FakeResp(self._data)


_ADMIN = types.SimpleNamespace(user_id="admin-1")
_POLL = "/api/llm-auth/device/poll"


@pytest.fixture
def ctx(monkeypatch, single_use_fake_redis):
    # Shared single-use-state Redis stub (conftest fixture — #11699).
    fake_redis = single_use_fake_redis
    monkeypatch.setattr(mod, "get_redis_client", lambda database="main": fake_redis)
    monkeypatch.setattr(mod, "get_oauth_allowed_hosts", lambda: {"token.example.com"})
    monkeypatch.setattr(mod, "_vault_write", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "build_token_data", lambda data, created_by: {"expires_at": 1.0})
    # #11497 finding #2: the outbound POST is now IP-pinned. Stub the resolve so the
    # test never does real DNS on the fake token host.
    monkeypatch.setattr(mod, "_pinned_connector", AsyncMock(return_value=None))

    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _ADMIN
    app.dependency_overrides[check_admin_permission] = lambda: True
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    return TestClient(app), fake_redis


def _body(device_code="dev-code-1"):
    return {
        "provider_name": "acme",
        "token_url": "https://token.example.com/token",
        "client_id": "cid",
        "device_code": device_code,
    }


def test_poll_too_fast_returns_429_before_provider_call(ctx):
    tc, fake_redis = ctx
    # A poll happened "just now" — the next one is inside the interval window.
    fake_redis.store[mod._device_poll_key("dev-code-1")] = json.dumps(
        {"interval": 5, "count": 1, "last_ts": time.time()}
    )
    resp = tc.post(_POLL, json=_body())
    assert resp.status_code == 429
    assert "too fast" in resp.json()["detail"]


def test_poll_attempts_exhausted_returns_429(ctx):
    tc, fake_redis = ctx
    fake_redis.store[mod._device_poll_key("dev-code-1")] = json.dumps(
        {"interval": 5, "count": mod._DEVICE_POLL_MAX_ATTEMPTS, "last_ts": 0.0}
    )
    resp = tc.post(_POLL, json=_body())
    assert resp.status_code == 429
    assert "exhausted" in resp.json()["detail"]


def test_first_poll_allowed_and_persists_state(ctx, monkeypatch):
    tc, fake_redis = ctx
    monkeypatch.setattr("aiohttp.ClientSession", _FakeSession)
    resp = tc.post(_POLL, json=_body())
    assert resp.status_code == 200
    assert resp.json()["stored"] is False  # authorization_pending
    saved = json.loads(fake_redis.store[mod._device_poll_key("dev-code-1")])
    assert saved["count"] == 1 and saved["last_ts"] > 0


def test_slow_down_backs_off_interval(ctx, monkeypatch):
    tc, fake_redis = ctx

    class _SlowSession(_FakeSession):
        _data = {"error": "slow_down"}

    monkeypatch.setattr("aiohttp.ClientSession", _SlowSession)
    # Pre-existing state whose window has elapsed so the poll is allowed through.
    fake_redis.store[mod._device_poll_key("dev-code-1")] = json.dumps({"interval": 5, "count": 1, "last_ts": 0.0})
    resp = tc.post(_POLL, json=_body())
    assert resp.status_code == 200
    saved = json.loads(fake_redis.store[mod._device_poll_key("dev-code-1")])
    assert saved["interval"] == 5 + mod._DEVICE_POLL_BACKOFF  # backed off +5s
    assert saved["count"] == 2


def test_poll_key_hashes_device_code(ctx):
    key = mod._device_poll_key("super-secret-code")
    assert "super-secret-code" not in key
    assert key.startswith("llm-auth:device:poll:")
