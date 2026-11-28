# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The /api/llm-auth security contract, by behaviour (#10551, #11298, #19241).

Replaces the dependency-set checks in ``llm_shared/tests/test_provider_auth.py``
that asserted every endpoint declared ``check_admin_permission``. What they
protected still holds, under the per-user scope the owner chose (#19241):

- no endpoint serves an unauthenticated caller (#10551 review);
- the org-shared ``system`` credential stays admin-only on every entry point and
  on both completions, and a non-admin cannot read its status (#11298);
- a non-admin's ``user`` scope works and only ever touches their own subject.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import provider_auth as mod
from api import provider_auth_flow_state as flow_state
from api import provider_auth_revoke as rv
from api.provider_auth_scope import provider_caller_is_admin
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.ssot_config import config
from knowledge.connectors import oauth_flow
from llm_shared.llm_oauth_registry import LlmOAuthClient

_REDIRECT = config.frontend_url + "/preferences/oauth/callback"
_USER = {"user_id": "u-7", "org_id": "org-1"}
_CLIENT = LlmOAuthClient(
    provider=oauth_flow.OAuthProvider(
        name="openai",
        authorize_url="https://auth.example.com/authorize",
        token_url="https://token.example.com/token",  # nosec B106  # endpoint URL, not a credential
        client_id_setting="openai_client_id",
        client_secret_setting="AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_SECRET",  # nosec B106  # pragma: allowlist secret
        device_authorization_url="https://auth.example.com/device",
        token_endpoint_auth_method="none",
    ),
    client_id="cid",
)

#: Every route on the router, as (method, path, json body).
_ALL_ROUTES = [
    ("get", "/api/llm-auth/providers", None),
    ("post", "/api/llm-auth/oauth/initiate", {"provider_name": "openai", "redirect_uri": _REDIRECT, "scope": "user"}),
    ("post", "/api/llm-auth/oauth/callback", {"state": "s", "code": "c", "redirect_uri": _REDIRECT}),
    ("post", "/api/llm-auth/device/initiate", {"provider_name": "openai", "scope": "user"}),
    ("post", "/api/llm-auth/device/poll", {"provider_name": "openai", "device_code": "dc"}),
    ("get", "/api/llm-auth/status/openai?scope=user", None),
    ("delete", "/api/llm-auth/openai?scope=user", None),
    ("delete", "/api/llm-auth/openai/shared", None),
]


def _unauthenticated():
    raise HTTPException(status_code=401, detail="not authenticated")


@pytest.fixture
def ctx(monkeypatch, single_use_fake_redis):
    """A non-admin caller ``u-7``; the registry resolves "openai" to fake endpoints."""
    session = AsyncMock()
    write = AsyncMock(return_value=None)
    monkeypatch.setattr(mod, "get_redis_client", lambda database="main": single_use_fake_redis)
    monkeypatch.setattr(mod, "get_oauth_allowed_hosts", lambda: {"auth.example.com", "token.example.com"})
    monkeypatch.setattr(mod, "resolve_client", lambda name, flow=None: _CLIENT)
    monkeypatch.setattr(mod, "_vault_write", write)
    monkeypatch.setattr(rv, "_vault_read", AsyncMock(return_value=None))  # DELETE reads the grant it may revoke
    monkeypatch.setattr(rv, "emit_security", MagicMock(return_value=True))
    monkeypatch.setattr(mod, "_pinned_connector", AsyncMock(return_value=None))
    # The code exchange's public-egress check resolves DNS; the fake token host has none. That the
    # check runs and blocks is proved in test_provider_auth_hardening.py (#19241).
    monkeypatch.setattr(mod, "assert_public_egress", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "_post_provider", AsyncMock(return_value={"device_code": "dc", "user_code": "UC"}))
    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: _USER
    app.dependency_overrides[provider_caller_is_admin] = lambda: False
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app), single_use_fake_redis, app, session, write


@pytest.mark.parametrize("method,path,body", _ALL_ROUTES)
def test_every_endpoint_rejects_an_unauthenticated_caller(ctx, method, path, body):
    tc, fake_redis, app, session, write = ctx
    app.dependency_overrides[get_current_user] = _unauthenticated
    app.dependency_overrides[provider_caller_is_admin] = _unauthenticated
    resp = tc.request(method.upper(), path, json=body)
    assert resp.status_code == 401
    assert not fake_redis.store
    write.assert_not_awaited()
    session.execute.assert_not_awaited()


@pytest.mark.parametrize(
    "method,path,body",
    [
        (
            "post",
            "/api/llm-auth/oauth/initiate",
            {"provider_name": "openai", "redirect_uri": _REDIRECT, "scope": "system"},
        ),
        ("post", "/api/llm-auth/device/initiate", {"provider_name": "openai", "scope": "system"}),
        ("get", "/api/llm-auth/status/openai?scope=system", None),
        ("delete", "/api/llm-auth/openai?scope=system", None),
    ],
)
def test_system_scope_entry_points_need_admin(ctx, method, path, body):
    tc, fake_redis, _, session, _ = ctx
    resp = tc.request(method.upper(), path, json=body)
    assert resp.status_code == 403
    assert not fake_redis.store
    session.execute.assert_not_awaited()


def _system_ctx() -> dict:
    """A system flow the caller (a former admin) started: initiator matches, admin does not."""
    return {"initiator_id": "u-7", "provider_name": "openai", "scope": "system", "subject": "org:org-1"}


def test_system_callback_completion_needs_admin(ctx, monkeypatch):
    tc, fake_redis, _, _, write = ctx
    monkeypatch.setattr(oauth_flow, "exchange_code", AsyncMock(return_value={"access_token": "at"}))
    fake_redis.store[flow_state.state_key("st")] = json.dumps(
        {**_system_ctx(), "verifier": "v", "redirect_uri": _REDIRECT}
    )
    resp = tc.post("/api/llm-auth/oauth/callback", json={"state": "st", "code": "c", "redirect_uri": _REDIRECT})
    assert resp.status_code == 403
    write.assert_not_awaited()


def test_system_poll_completion_needs_admin(ctx):
    tc, fake_redis, _, _, write = ctx
    fake_redis.store[flow_state.device_context_key("dc")] = json.dumps(_system_ctx())
    resp = tc.post("/api/llm-auth/device/poll", json={"provider_name": "openai", "device_code": "dc"})
    assert resp.status_code == 403
    mod._post_provider.assert_not_awaited()
    write.assert_not_awaited()


def test_user_scope_works_for_a_non_admin_on_their_own_subject(ctx, monkeypatch):
    tc, fake_redis, _, session, _ = ctx
    body = {"provider_name": "openai", "redirect_uri": _REDIRECT, "scope": "user"}
    initiate = tc.post("/api/llm-auth/oauth/initiate", json=body)
    assert initiate.status_code == 200, initiate.text
    (stored,) = [json.loads(v) for v in fake_redis.store.values()]
    assert (stored["scope"], stored["subject"]) == ("user", "user:u-7")

    read = AsyncMock(return_value=None)
    monkeypatch.setattr(mod, "_vault_read_dual", read)
    assert tc.get("/api/llm-auth/status/openai?scope=user").status_code == 200
    assert read.await_args.kwargs["subject"] == "user:u-7"

    assert tc.delete("/api/llm-auth/openai?scope=user").status_code == 200
    statement = str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))
    assert "provider_auth:openai:user:u-7" in statement
