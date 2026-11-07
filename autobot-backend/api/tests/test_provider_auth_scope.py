# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""System vs per-user provider sign-in (#19241).

Proves a non-admin cannot start or finish a system-level flow, a user's flow
writes to that user's own subject, the callback/poll writes to the scope the
flow STARTED with, and one user can never complete or read another's.
"""

import json
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api import provider_auth as mod
from api import provider_auth_flow_state as flow_state
from api import provider_auth_scope as scope_mod
from api.provider_auth_scope import provider_caller_is_admin
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.ssot_config import config
from knowledge.connectors import oauth_flow
from llm_shared.llm_oauth_registry import LlmOAuthClient

_INITIATE = "/api/llm-auth/oauth/initiate"
_CALLBACK = "/api/llm-auth/oauth/callback"
_REDIRECT = config.frontend_url + "/preferences/oauth/callback"
_CLIENT = LlmOAuthClient(
    provider=oauth_flow.OAuthProvider(
        name="acme",
        authorize_url="https://auth.example.com/authorize",
        token_url="https://token.example.com/token",  # nosec B106  # endpoint URL, not a credential
        client_id_setting="acme_client_id",
        client_secret_setting="ACME_CLIENT_SECRET",  # nosec B106  # pragma: allowlist secret  # setting NAME
        device_authorization_url="https://auth.example.com/device",
        token_endpoint_auth_method="none",
    ),
    client_id="cid",
)


class _Principal:
    """Mutable caller so one test can switch users between requests."""

    def __init__(self):
        self.user = {"user_id": "u-7", "org_id": "org-1"}
        self.admin = False


@pytest.fixture
def ctx(monkeypatch, single_use_fake_redis):
    who = _Principal()
    write = AsyncMock(return_value=None)
    monkeypatch.setattr(mod, "get_redis_client", lambda database="main": single_use_fake_redis)
    monkeypatch.setattr(mod, "get_oauth_allowed_hosts", lambda: {"auth.example.com", "token.example.com"})
    monkeypatch.setattr(mod, "resolve_client", lambda name, flow=None: _CLIENT)
    monkeypatch.setattr(mod, "_vault_write", write)
    monkeypatch.setattr(mod, "_pinned_connector", AsyncMock(return_value=None))
    # The code exchange's public-egress check resolves DNS; the fake token host has none. That the
    # check runs and blocks is proved in test_provider_auth_hardening.py (#19241).
    monkeypatch.setattr(mod, "assert_public_egress", AsyncMock(return_value=None))
    monkeypatch.setattr(oauth_flow, "exchange_code", AsyncMock(return_value={"access_token": "at", "expires_in": 60}))
    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: who.user
    app.dependency_overrides[provider_caller_is_admin] = lambda: who.admin
    app.dependency_overrides[get_db_session] = lambda: AsyncMock()
    return TestClient(app), single_use_fake_redis, who, write


def _initiate(tc, scope="user"):
    return tc.post(_INITIATE, json={"provider_name": "acme", "redirect_uri": _REDIRECT, "scope": scope})


def _callback(tc, state):
    return tc.post(_CALLBACK, json={"state": state, "code": "c", "redirect_uri": _REDIRECT})


def test_non_admin_cannot_initiate_system_scope(ctx):
    tc, fake_redis, _, _ = ctx
    resp = _initiate(tc, "system")
    assert resp.status_code == 403
    assert not fake_redis.store


def test_scope_is_required_on_both_initiates(ctx):
    """#19241 review: the caller always says whose connection it is; no server-side default."""
    tc, fake_redis, _, _ = ctx
    assert tc.post(_INITIATE, json={"provider_name": "acme", "redirect_uri": _REDIRECT}).status_code == 422
    assert tc.post("/api/llm-auth/device/initiate", json={"provider_name": "acme"}).status_code == 422
    assert not fake_redis.store


def test_non_admin_user_scope_writes_own_subject(ctx):
    tc, fake_redis, _, write = ctx
    resp = _initiate(tc)
    assert resp.status_code == 200, resp.text
    (stored,) = [json.loads(v) for v in fake_redis.store.values()]
    assert stored["scope"] == "user" and stored["subject"] == "user:u-7"
    done = _callback(tc, resp.json()["state"])
    assert done.status_code == 200, done.text
    assert done.json()["scope"] == "user"
    assert write.await_args.kwargs["subject"] == "user:u-7"


def test_admin_user_scope_writes_user_subject_not_org(ctx):
    tc, _, who, write = ctx
    who.admin = True
    state = _initiate(tc, "user").json()["state"]
    assert _callback(tc, state).status_code == 200
    assert write.await_args.kwargs["subject"] == "user:u-7"


def test_admin_system_scope_writes_org_subject(ctx):
    tc, _, who, write = ctx
    who.admin = True
    state = _initiate(tc, "system").json()["state"]
    assert _callback(tc, state).status_code == 200
    assert write.await_args.kwargs["subject"] == "org:org-1"


def test_callback_writes_the_initiated_scope_even_if_admin_status_changes(ctx):
    """A user flow started by an admin stays a user flow; a system flow cannot be finished by a non-admin."""
    tc, _, who, write = ctx
    who.admin = True
    system_state = _initiate(tc, "system").json()["state"]
    who.admin = False  # demoted between initiate and callback
    assert _callback(tc, system_state).status_code == 403
    write.assert_not_awaited()


def test_another_user_cannot_complete_or_burn_my_flow(ctx):
    """L3: a wrong initiator gets 403 and the state survives; its owner completes it once."""
    tc, fake_redis, who, write = ctx
    state = _initiate(tc).json()["state"]
    who.user = {"user_id": "u-8", "org_id": "org-1"}
    assert _callback(tc, state).status_code == 403
    write.assert_not_awaited()
    assert flow_state.state_key(state) in fake_redis.store
    who.user = {"user_id": "u-7", "org_id": "org-1"}
    assert _callback(tc, state).status_code == 200
    assert _callback(tc, state).status_code == 400  # still single-use


def test_status_reads_only_the_callers_own_subject(ctx, monkeypatch):
    tc, _, _, _ = ctx
    read = AsyncMock(return_value=None)
    monkeypatch.setattr(mod, "_vault_read_dual", read)
    resp = tc.get("/api/llm-auth/status/openai?scope=user")
    assert resp.status_code == 200
    assert resp.json()["scope"] == "user"
    assert read.await_args.kwargs["subject"] == "user:u-7"
    assert tc.get("/api/llm-auth/status/openai?scope=system").status_code == 403


def test_status_defaults_to_the_callers_own_even_for_an_admin(ctx, monkeypatch):
    """M2: no scope means "mine", never the org credential."""
    tc, _, who, _ = ctx
    who.admin = True
    read = AsyncMock(return_value=None)
    monkeypatch.setattr(mod, "_vault_read_dual", read)
    resp = tc.get("/api/llm-auth/status/openai")
    assert resp.status_code == 200 and resp.json()["scope"] == "user"
    assert read.await_args.kwargs["subject"] == "user:u-7"


def test_delete_requires_an_explicit_scope(ctx):
    """M2: an admin's scope-less disconnect must not delete the org credential."""
    tc, _, who, _ = ctx
    who.admin = True
    assert tc.delete("/api/llm-auth/openai").status_code == 422


@pytest.mark.parametrize("name", ["acme", "openai:org:other", "user:u-8"])
def test_status_and_delete_reject_unknown_providers(ctx, name):
    """L1: only registry providers; a ``:`` can never reach the vault secret name."""
    tc, _, _, _ = ctx
    assert tc.get(f"/api/llm-auth/status/{name}?scope=user").status_code == 404
    assert tc.delete(f"/api/llm-auth/{name}?scope=user").status_code == 404


def test_device_poll_bound_to_initiating_user(ctx, monkeypatch):
    tc, fake_redis, who, _ = ctx
    monkeypatch.setattr(
        mod,
        "_post_provider",
        AsyncMock(return_value={"device_code": "dc-1", "user_code": "UC", "verification_uri": "https://x"}),
    )
    resp = tc.post("/api/llm-auth/device/initiate", json={"provider_name": "acme", "scope": "user"})
    assert resp.status_code == 200, resp.text
    ctx_saved = json.loads(fake_redis.store[flow_state.device_context_key("dc-1")])
    assert ctx_saved["scope"] == "user" and ctx_saved["subject"] == "user:u-7"
    who.user = {"user_id": "u-8"}
    poll = tc.post("/api/llm-auth/device/poll", json={"provider_name": "acme", "device_code": "dc-1"})
    assert poll.status_code == 403


@pytest.mark.asyncio
async def test_caller_is_admin_maps_only_403_to_false(monkeypatch):
    async def _forbidden(request):
        raise HTTPException(status_code=403, detail="no")

    async def _unauthenticated(request):
        raise HTTPException(status_code=401, detail="no")

    monkeypatch.setattr(scope_mod, "check_admin_permission", _forbidden)
    assert await scope_mod.provider_caller_is_admin(object()) is False
    monkeypatch.setattr(scope_mod, "check_admin_permission", _unauthenticated)
    with pytest.raises(HTTPException):
        await scope_mod.provider_caller_is_admin(object())


def test_user_scope_without_a_user_id_is_refused():
    with pytest.raises(HTTPException) as exc:
        scope_mod.subject_for("user", {})
    assert exc.value.status_code == 401
