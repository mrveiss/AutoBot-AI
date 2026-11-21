# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""PR #19259 review hardening of /api/llm-auth (#19241).

- A multi-tenant system disconnect replaces the org's token with a per-org stop
  marker (the shared legacy ``global`` token stays for other orgs); an org-less
  admin's system disconnect (its subject IS ``global``) is refused -- that is the
  superadmin's shared revoke. Only the deleted grant is revoked at the provider (RFC 7009),
  and a provider-side failure is reported while the local change still happens.
- /status reports ``needs_reauth`` for a token the provider rejected.
- The device flow refuses a non-https ``verification_uri`` and a non-JSON body (502).
- The code exchange runs the public-egress check.
"""

import dataclasses
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

_REVOKE_URL = "https://auth.example.com/revoke"
_PROVIDER = oauth_flow.OAuthProvider(
    name="openai",
    authorize_url="https://auth.example.com/authorize",
    token_url="https://token.example.com/token",  # nosec B106  # endpoint URL, not a credential
    client_id_setting="openai_client_id",
    client_secret_setting="AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_SECRET",  # nosec B106  # pragma: allowlist secret
    device_authorization_url="https://auth.example.com/device",
    revocation_url=_REVOKE_URL,
    token_endpoint_auth_method="none",
)
_CLIENT = LlmOAuthClient(provider=_PROVIDER, client_id="cid")
_REDIRECT = config.frontend_url + "/preferences/oauth/callback"


class _Who:
    def __init__(self):
        self.user = {"user_id": "admin-1", "org_id": "org-1"}
        self.admin = True


@pytest.fixture
def ctx(monkeypatch, single_use_fake_redis):
    who, session = _Who(), AsyncMock()
    monkeypatch.setattr(mod, "get_redis_client", lambda database="main": single_use_fake_redis)
    monkeypatch.setattr(mod, "get_oauth_allowed_hosts", lambda: {"auth.example.com", "token.example.com"})
    monkeypatch.setattr(mod, "resolve_client", lambda name, flow=None: _CLIENT)
    monkeypatch.setattr(rv, "build_provider", lambda name: _PROVIDER)
    monkeypatch.setattr(rv, "emit_security", MagicMock(return_value=True))
    monkeypatch.setattr(mod, "_pinned_connector", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "assert_public_egress", AsyncMock(return_value=None))
    monkeypatch.setattr(mod, "_vault_write", AsyncMock(return_value=None))  # a sign-in's token write
    monkeypatch.setattr(rv, "_vault_write", AsyncMock(return_value=None))  # a disconnect's stop-marker write
    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: who.user
    app.dependency_overrides[provider_caller_is_admin] = lambda: who.admin
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app), single_use_fake_redis, who, session


def _grants(monkeypatch, by_subject: dict) -> AsyncMock:
    read = AsyncMock(side_effect=lambda session, *, provider_name, subject, owner_vault_str: by_subject.get(subject))
    monkeypatch.setattr(rv, "_vault_read", read)
    return read


def _deleted_names(session) -> str:
    return str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))


# --- revoke -------------------------------------------------------------------


def test_multi_tenant_system_revoke_leaves_a_stop_marker_and_keeps_the_legacy_token(ctx, monkeypatch):
    tc, _, _, session = ctx
    _grants(monkeypatch, {"org:org-1": {"access_token": "a"}, "global": {"access_token": "g", "refresh_token": "gr"}})
    revoke_one = AsyncMock(return_value=None)
    monkeypatch.setattr(rv, "revoke_one", revoke_one)
    resp = tc.delete("/api/llm-auth/openai?scope=system")
    assert resp.status_code == 200, resp.text
    write = rv._vault_write.await_args.kwargs
    assert write["subject"] == "org:org-1" and write["token_data"]["legacy_fallback_stopped"] is True
    session.execute.assert_not_awaited()  # nothing deleted by name: "global" survives for other orgs
    assert [c.args[2] for c in revoke_one.await_args_list] == [{"access_token": "a"}]  # never the shared token
    assert resp.json()["deleted"] == 1
    session.commit.assert_awaited()


def test_an_org_less_admin_system_disconnect_is_refused_without_side_effects(ctx, monkeypatch):
    """Owner decision (#19241): an org-less admin's system subject IS the shared token -- superadmin only."""
    tc, _, who, session = ctx
    who.user = {"user_id": "admin-1"}  # no org: the system subject is "global"
    _grants(monkeypatch, {"global": {"access_token": "g", "refresh_token": "gr"}})
    revoke_one = AsyncMock(return_value=None)
    monkeypatch.setattr(rv, "revoke_one", revoke_one)
    resp = tc.delete("/api/llm-auth/openai?scope=system")
    assert resp.status_code == 403
    assert "/api/llm-auth/openai/shared" in resp.json()["detail"]
    session.execute.assert_not_awaited()
    session.commit.assert_not_awaited()
    rv._vault_write.assert_not_awaited()
    revoke_one.assert_not_awaited()
    (call,) = rv.emit_security.call_args_list
    assert call.kwargs["outcome"] == "denied"
    assert call.kwargs["metadata"]["local"] == "none" and call.kwargs["metadata"]["provider_revoke"] == "not_attempted"


def test_an_org_admin_with_an_org_still_gets_the_stop_marker(ctx, monkeypatch):
    tc, _, _, session = ctx
    _grants(monkeypatch, {"org:org-1": {"access_token": "a"}})
    monkeypatch.setattr(rv, "revoke_one", AsyncMock(return_value=None))
    assert tc.delete("/api/llm-auth/openai?scope=system").status_code == 200
    assert rv._vault_write.await_args.kwargs["token_data"]["legacy_fallback_stopped"] is True
    session.execute.assert_not_awaited()  # nothing deleted by name


def test_status_flags_an_org_less_admin_system_connection_as_shared(ctx, monkeypatch):
    tc, _, who, _ = ctx
    who.user = {"user_id": "admin-1"}
    monkeypatch.setattr(mod, "_vault_read_dual", AsyncMock(return_value={"access_token": "g"}))
    assert tc.get("/api/llm-auth/status/openai?scope=system").json()["shared"] is True
    who.user = {"user_id": "admin-1", "org_id": "org-1"}
    assert tc.get("/api/llm-auth/status/openai?scope=system").json()["shared"] is False


def test_org_signing_in_again_overwrites_its_stop_marker(ctx, monkeypatch):
    """The callback writes the new token to the same org subject, replacing the marker."""
    tc, fake_redis, _, _ = ctx
    monkeypatch.setattr(oauth_flow, "exchange_code", AsyncMock(return_value={"access_token": "new-at"}))
    fake_redis.store[flow_state.state_key("st")] = json.dumps(
        {
            "initiator_id": "admin-1",
            "provider_name": "openai",
            "scope": "system",
            "subject": "org:org-1",
            "verifier": "v",
            "redirect_uri": _REDIRECT,
        }
    )
    resp = tc.post("/api/llm-auth/oauth/callback", json={"state": "st", "code": "c", "redirect_uri": _REDIRECT})
    assert resp.status_code == 200, resp.text
    write = mod._vault_write.await_args.kwargs
    assert write["subject"] == "org:org-1" and "legacy_fallback_stopped" not in write["token_data"]


def test_user_revoke_never_touches_the_shared_tokens(ctx, monkeypatch):
    tc, _, who, session = ctx
    who.admin = False
    _grants(monkeypatch, {"user:admin-1": {"access_token": "u"}})
    monkeypatch.setattr(rv, "revoke_one", AsyncMock(return_value=None))
    assert tc.delete("/api/llm-auth/openai?scope=user").status_code == 200
    statement = _deleted_names(session)
    assert "provider_auth:openai:user:admin-1" in statement
    assert "global" not in statement and "org:org-1" not in statement


def test_revoke_calls_the_provider_rfc7009_endpoint_with_the_refresh_token(ctx, monkeypatch):
    tc, _, _, _ = ctx
    _grants(monkeypatch, {"org:org-1": {"access_token": "a", "refresh_token": "r"}})
    sent = []

    async def _post_form(url, payload, what, handle):
        sent.append((url, payload))

    monkeypatch.setattr(mod, "_post_form", _post_form)
    body = tc.delete("/api/llm-auth/openai?scope=system").json()
    assert body["provider_revoked"] is True and body["provider_error"] is None
    assert sent == [(_REVOKE_URL, {"client_id": "cid", "token": "r", "token_type_hint": "refresh_token"})]


def test_a_provider_revoke_failure_is_reported_and_the_local_delete_still_happens(ctx, monkeypatch):
    tc, _, _, session = ctx
    _grants(monkeypatch, {"org:org-1": {"access_token": "a"}})
    failing = AsyncMock(side_effect=HTTPException(status_code=502, detail="Revocation endpoint failed: boom"))
    monkeypatch.setattr(rv, "revoke_one", failing)
    resp = tc.delete("/api/llm-auth/openai?scope=system")
    assert resp.status_code == 200
    assert resp.json()["provider_revoked"] is False
    assert "boom" in resp.json()["provider_error"]
    assert rv._vault_write.await_args.kwargs["token_data"]["legacy_fallback_stopped"] is True  # local change done
    session.commit.assert_awaited()


def test_no_revoke_url_means_local_only(ctx, monkeypatch):
    tc, _, _, _ = ctx
    monkeypatch.setattr(rv, "build_provider", lambda name: dataclasses.replace(_PROVIDER, revocation_url=""))
    _grants(monkeypatch, {"org:org-1": {"access_token": "a"}})
    sent = AsyncMock()
    monkeypatch.setattr(mod, "_post_form", sent)
    assert tc.delete("/api/llm-auth/openai?scope=system").json()["provider_revoked"] is None
    sent.assert_not_awaited()


def test_an_unsafe_revoke_url_is_refused_before_any_request(ctx, monkeypatch):
    tc, _, _, session = ctx
    monkeypatch.setattr(
        rv, "build_provider", lambda name: dataclasses.replace(_PROVIDER, revocation_url="https://evil.example.net/r")
    )
    _grants(monkeypatch, {"org:org-1": {"access_token": "a"}})
    sent = AsyncMock()
    monkeypatch.setattr(mod, "_post_form", sent)
    body = tc.delete("/api/llm-auth/openai?scope=system").json()
    assert body["provider_revoked"] is False
    sent.assert_not_awaited()
    session.commit.assert_awaited()  # the local delete still happened


# --- status -----------------------------------------------------------------


def test_status_reports_needs_reauth_for_a_rejected_token(ctx, monkeypatch):
    tc, _, _, _ = ctx
    monkeypatch.setattr(mod, "_vault_read_dual", AsyncMock(return_value={"access_token": "a", "needs_reauth": True}))
    body = tc.get("/api/llm-auth/status/openai?scope=user").json()
    assert body["needs_reauth"] is True and body["connected"] is False


# --- device flow / exchange -------------------------------------------------


def test_device_initiate_refuses_a_non_https_verification_uri(ctx, monkeypatch):
    tc, fake_redis, _, _ = ctx
    answer = {"device_code": "dc", "user_code": "UC", "verification_uri": "http://phish.example.net/"}
    monkeypatch.setattr(mod, "_post_provider", AsyncMock(return_value=answer))
    resp = tc.post("/api/llm-auth/device/initiate", json={"provider_name": "openai", "scope": "user"})
    assert resp.status_code == 502
    assert not fake_redis.store


def test_device_poll_maps_a_non_json_body_to_502(ctx, monkeypatch):
    tc, fake_redis, who, _ = ctx
    fake_redis.store[flow_state.device_context_key("dc")] = json.dumps(
        {"initiator_id": "admin-1", "provider_name": "openai", "scope": "user", "subject": "user:admin-1"}
    )

    class _Resp:
        status, headers = 200, {}

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def json(self, content_type=None):
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

    class _Session:
        def __init__(self, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def post(self, *a, **k):
            return _Resp()

    monkeypatch.setattr("aiohttp.ClientSession", _Session)
    resp = tc.post("/api/llm-auth/device/poll", json={"provider_name": "openai", "device_code": "dc"})
    assert resp.status_code == 502


def test_the_code_exchange_runs_the_public_egress_check(ctx, monkeypatch):
    tc, fake_redis, _, _ = ctx
    from autobot_shared.http_egress_guard import EgressBlockedError

    monkeypatch.setattr(mod, "assert_public_egress", AsyncMock(side_effect=EgressBlockedError("private address")))
    exchange = AsyncMock(return_value={"access_token": "at"})
    monkeypatch.setattr(oauth_flow, "exchange_code", exchange)
    fake_redis.store[flow_state.state_key("st")] = json.dumps(
        {
            "initiator_id": "admin-1",
            "provider_name": "openai",
            "scope": "system",
            "subject": "org:org-1",
            "verifier": "v",
            "redirect_uri": _REDIRECT,
        }
    )
    resp = tc.post("/api/llm-auth/oauth/callback", json={"state": "st", "code": "c", "redirect_uri": _REDIRECT})
    assert resp.status_code == 400
    exchange.assert_not_awaited()
