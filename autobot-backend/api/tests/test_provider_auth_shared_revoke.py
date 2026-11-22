# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Superadmin shared-token revoke and the disconnect audit trail (#19241, owner decision 2026-10-23).

- ``DELETE /api/llm-auth/{provider}/shared`` is gated by the existing RBAC
  ``require_role(Role.SUPERADMIN)``: an org admin gets 403.
- A superadmin's revoke deletes the legacy ``global`` token and revokes it at the provider.
- Every disconnect and revoke writes one canonical SECURITY audit event carrying who,
  provider, scope, subject kind and result -- and no token or subject id.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth_rbac
from api import provider_auth as mod
from api import provider_auth_revoke as rv
from api.provider_auth_scope import provider_caller_is_admin
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from knowledge.connectors import oauth_flow
from llm_shared.llm_oauth_registry import LlmOAuthClient

_PROVIDER = oauth_flow.OAuthProvider(
    name="openai",
    authorize_url="https://auth.example.com/authorize",
    token_url="https://token.example.com/token",  # nosec B106  # endpoint URL, not a credential
    client_id_setting="openai_client_id",
    client_secret_setting="AUTOBOT_LLM_OAUTH_OPENAI_CLIENT_SECRET",  # nosec B106  # pragma: allowlist secret
    revocation_url="https://auth.example.com/revoke",
    token_endpoint_auth_method="none",
)
_GRANTS = {
    "global": {"access_token": "shared-at", "refresh_token": "shared-rt"},
    "org:org-1": {"access_token": "org-at"},
    "user:u-7": {"access_token": "user-at"},
}
_SECRET_MATERIAL = ("shared-at", "shared-rt", "org-at", "user-at", "org-1", "user:u-7", "org:org-1")


class _Who:
    def __init__(self):
        self.user = {"user_id": "u-7", "org_id": "org-1", "role": "admin"}
        self.admin = True


@pytest.fixture
def ctx(monkeypatch):
    who, session, audit, revoke_one = _Who(), AsyncMock(), MagicMock(return_value=True), AsyncMock()

    async def _read(session, *, provider_name, subject, owner_vault_str):
        return _GRANTS.get(subject)

    monkeypatch.setattr(rv, "_vault_read", _read)
    monkeypatch.setattr(rv, "_vault_write", AsyncMock(return_value=None))
    monkeypatch.setattr(rv, "build_provider", lambda name: _PROVIDER)
    monkeypatch.setattr(rv, "revoke_one", revoke_one)
    monkeypatch.setattr(rv, "emit_security", audit)
    monkeypatch.setattr(mod, "get_oauth_allowed_hosts", lambda: {"auth.example.com", "token.example.com"})
    monkeypatch.setattr(mod, "resolve_client", lambda name, flow=None: LlmOAuthClient(_PROVIDER, "cid"))
    # The real superadmin gate runs; only the request's principal and its denial log are stubbed.
    monkeypatch.setattr(auth_rbac, "resolve_human_user", AsyncMock(side_effect=lambda request: who.user))
    monkeypatch.setattr(auth_rbac, "_get_security_layer", lambda: MagicMock())
    app = FastAPI()
    app.include_router(mod.router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: who.user
    app.dependency_overrides[provider_caller_is_admin] = lambda: who.admin
    app.dependency_overrides[get_db_session] = lambda: session
    return TestClient(app), who, session, audit, revoke_one


def _statement(session) -> str:
    return str(session.execute.await_args.args[0].compile(compile_kwargs={"literal_binds": True}))


def _metadata(audit) -> dict:
    (call,) = audit.call_args_list
    return call.kwargs["metadata"]


def test_an_org_admin_cannot_revoke_the_shared_token(ctx):
    tc, _, session, audit, revoke_one = ctx
    assert tc.delete("/api/llm-auth/openai/shared").status_code == 403
    session.execute.assert_not_awaited()
    revoke_one.assert_not_awaited()
    audit.assert_not_called()


def test_a_superadmin_revoke_deletes_global_and_revokes_it_at_the_provider(ctx):
    tc, who, session, audit, revoke_one = ctx
    who.user = {**who.user, "role": "superadmin"}
    resp = tc.delete("/api/llm-auth/openai/shared")
    assert resp.status_code == 200, resp.text
    assert resp.json()["scope"] == "shared" and resp.json()["provider_revoked"] is True
    assert "provider_auth:openai:global" in _statement(session)
    assert revoke_one.await_args.args[2] == _GRANTS["global"]
    session.commit.assert_awaited()


@pytest.mark.parametrize(
    "role,path,expected",
    [
        ("admin", "/api/llm-auth/openai?scope=user", {"scope": "user", "subject_kind": "user", "local": "deleted"}),
        ("admin", "/api/llm-auth/openai?scope=system", {"scope": "system", "subject_kind": "org", "local": "marked"}),
        (
            "superadmin",
            "/api/llm-auth/openai/shared",
            {"scope": "shared", "subject_kind": "legacy", "local": "deleted"},
        ),
    ],
)
def test_every_disconnect_writes_one_audit_event_without_secret_material(ctx, role, path, expected):
    tc, who, _, audit, _ = ctx
    who.user = {**who.user, "role": role}
    assert tc.delete(path).status_code == 200
    (call,) = audit.call_args_list
    assert call.args[0].value == "provider_signin.revoke"
    assert call.args[1] == "u-7"  # who: the principal id
    assert call.kwargs["resource_id"] == "openai"
    assert _metadata(audit) == {"provider": "openai", "provider_revoke": "revoked", **expected}
    rendered = repr(call)
    assert not any(material in rendered for material in _SECRET_MATERIAL)


def test_an_org_less_admin_system_disconnect_is_refused_and_audited_as_denied(ctx):
    tc, who, session, audit, revoke_one = ctx
    who.user = {"user_id": "u-7", "role": "admin"}  # no org: the system subject IS "global"
    assert tc.delete("/api/llm-auth/openai?scope=system").status_code == 403
    session.execute.assert_not_awaited()
    revoke_one.assert_not_awaited()
    assert audit.call_args.kwargs["outcome"] == "denied"
    assert _metadata(audit) == {
        "provider": "openai",
        "scope": "system",
        "subject_kind": "legacy",
        "local": "none",
        "provider_revoke": "not_attempted",
    }


def test_a_provider_revoke_failure_is_audited_as_partial(ctx, monkeypatch):
    from fastapi import HTTPException

    tc, who, _, audit, _ = ctx
    who.user = {**who.user, "role": "superadmin"}
    monkeypatch.setattr(rv, "revoke_one", AsyncMock(side_effect=HTTPException(status_code=502, detail="boom")))
    body = tc.delete("/api/llm-auth/openai/shared").json()
    assert body["provider_revoked"] is False and "boom" in body["provider_error"]
    assert _metadata(audit)["provider_revoke"] == "failed"
    assert audit.call_args.kwargs["outcome"] == "partial"


def test_no_revoke_url_is_audited_as_not_configured(ctx, monkeypatch):
    import dataclasses

    tc, _, _, audit, _ = ctx
    monkeypatch.setattr(rv, "build_provider", lambda name: dataclasses.replace(_PROVIDER, revocation_url=""))
    assert tc.delete("/api/llm-auth/openai?scope=user").status_code == 200
    assert _metadata(audit)["provider_revoke"] == "not_configured"


def test_a_failed_audit_write_is_warned_about(ctx, monkeypatch):
    """Review low: emit_security() returning False must not pass silently."""
    tc, _, _, audit, _ = ctx
    audit.return_value = False
    log = MagicMock()
    monkeypatch.setattr(rv, "logger", log)
    assert tc.delete("/api/llm-auth/openai?scope=user").status_code == 200
    assert any("could not be written" in str(c.args[0]) for c in log.warning.call_args_list)
