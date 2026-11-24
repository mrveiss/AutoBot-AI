# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#13710: the Microsoft 365 (Outlook mail) router through a real FastAPI app.

The integration and the credential store are mocked: no Graph call, no credential.
Auth is the REAL ``check_admin_permission``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import integration_microsoft365 as m365
from integrations.base import IntegrationHealth, IntegrationStatus
from knowledge.connectors import oauth_flow

PREFIX = "/integrations/microsoft365"


@pytest.fixture
def app(real_auth_middleware):
    app = FastAPI()
    app.include_router(m365.router, prefix=PREFIX)
    app.dependency_overrides[m365.check_admin_permission] = real_auth_middleware.check_admin_permission
    return app


@pytest.fixture
def as_user(real_auth_middleware):
    def _patch(user):
        return patch.object(real_auth_middleware, "resolve_human_user", AsyncMock(return_value=user))

    return _patch


@pytest.fixture
def integration():
    """A mocked integration; the credential store and the secret lookup are mocked too."""
    mock = MagicMock()
    mock.execute_action = AsyncMock(return_value={"value": []})
    mock.test_connection = AsyncMock(
        return_value=IntegrationHealth(provider="microsoft365", status=IntegrationStatus.CONNECTED)
    )
    store = MagicMock()
    store.get_access_token = AsyncMock(return_value="dummy-token")
    with (
        patch.object(m365, "find_connector_secret_id", new=AsyncMock(return_value="sid-1")) as find,
        patch.object(m365, "get_credential_store", return_value=store),
        patch.object(m365, "Microsoft365Integration", return_value=mock) as cls,
    ):
        mock.cls, mock.store, mock.find = cls, store, find
        yield mock


@pytest.fixture
def admin(app, as_user, integration):
    with as_user({"username": "root", "role": "admin"}):
        yield TestClient(app, raise_server_exceptions=False)


def test_list_messages(admin, integration):
    resp = admin.get(f"{PREFIX}/messages", params={"folder_id": "inbox", "limit": 5})
    assert resp.status_code == 200
    integration.execute_action.assert_awaited_once_with("list_messages", {"folder_id": "inbox", "limit": 5})


def test_stored_credential_gives_a_token_for_the_call(admin, integration):
    admin.get(f"{PREFIX}/folders")
    integration.find.assert_awaited_once_with("microsoft365")
    integration.store.get_access_token.assert_awaited_once_with("sid-1", "system")
    assert integration.cls.call_args.args[0].token == "dummy-token"


def test_expired_token_is_refreshed_by_the_store(admin, integration):
    integration.store.get_access_token.side_effect = ["refreshed-token"]
    admin.get(f"{PREFIX}/folders")
    assert integration.cls.call_args.args[0].token == "refreshed-token"


def test_query_token_is_ignored(admin, integration):
    admin.get(f"{PREFIX}/folders", params={"token": "attacker"})
    assert integration.cls.call_args.args[0].token == "dummy-token"


def test_missing_credential_is_a_400(admin, integration):
    integration.find.return_value = None
    resp = admin.get(f"{PREFIX}/messages")
    assert resp.status_code == 400 and "not connected" in resp.text
    integration.execute_action.assert_not_awaited()


@pytest.mark.parametrize("exc", [LookupError("secret detail"), PermissionError("secret detail")])
def test_store_refusal_is_a_fixed_400(admin, integration, exc):
    integration.store.get_access_token.side_effect = exc
    resp = admin.get(f"{PREFIX}/messages")
    assert resp.status_code == 400 and "secret detail" not in resp.text


def test_mail_provider_scopes_and_microsoft_unchanged():
    mail = oauth_flow.get_provider("microsoft-mail")
    assert mail.default_scopes == ("offline_access", "Mail.Read", "Mail.Send")
    assert (mail.service_owner_id, mail.service_connector_id) == ("system", "microsoft365")
    drive = oauth_flow.get_provider("microsoft")
    assert drive.default_scopes == ("offline_access", "Files.Read.All", "Sites.Read.All")
    assert not drive.service_owner_id and not drive.service_connector_id


def test_search_messages(admin, integration):
    resp = admin.get(f"{PREFIX}/messages/search", params={"query": "invoice"})
    assert resp.status_code == 200
    integration.execute_action.assert_awaited_once_with("search_messages", {"query": "invoice", "limit": 50})


def test_integration_error_is_a_fixed_400(admin, integration):
    integration.execute_action.return_value = {"error": "secret detail"}
    resp = admin.get(f"{PREFIX}/messages/search", params={"query": "x"})
    assert resp.status_code == 400 and "secret detail" not in resp.text


def test_send_email(admin, integration):
    integration.execute_action.return_value = {"success": True}
    body = {"to": ["a@example.invalid"], "subject": "s", "body": "b"}
    resp = admin.post(f"{PREFIX}/messages", json=body)
    assert resp.status_code == 200 and resp.json() == {"success": True}
    action, params = integration.execute_action.await_args.args
    assert action == "send_email" and params["to"] == ["a@example.invalid"] and params["body_type"] == "HTML"


def test_send_email_denied_by_egress_policy(admin, integration):
    verdict = MagicMock(allowed=False)
    with patch.object(m365.egress_governor, "gate", new=AsyncMock(return_value=verdict)):
        resp = admin.post(f"{PREFIX}/messages", json={"to": ["a@example.invalid"], "subject": "s", "body": "b"})
    assert resp.status_code == 403
    integration.execute_action.assert_not_awaited()


def test_health(admin, integration):
    resp = admin.post(f"{PREFIX}/test-connection")
    assert resp.status_code == 200 and resp.json()["status"] == IntegrationStatus.CONNECTED.value


ROUTES = [
    ("get", "/messages"),
    ("get", "/messages/search?query=x"),
    ("get", "/folders"),
    ("post", "/test-connection"),
    ("post", "/messages"),
]


@pytest.mark.parametrize("method,path", ROUTES)
def test_unauthenticated_is_refused(app, as_user, integration, method, path):
    with as_user(None):
        client = TestClient(app, raise_server_exceptions=False)
        resp = getattr(client, method)(PREFIX + path)
    assert resp.status_code == 401
    integration.execute_action.assert_not_awaited()


@pytest.mark.parametrize("method,path", ROUTES)
def test_non_admin_is_refused(app, as_user, integration, method, path):
    with as_user({"username": "bob", "role": "user"}), patch("auth_rbac.audit_role_denied"):
        client = TestClient(app, raise_server_exceptions=False)
        resp = getattr(client, method)(PREFIX + path)
    assert resp.status_code == 403
    integration.execute_action.assert_not_awaited()


# --- the OAuth flow files the mailbox credential under the service owner (#13710) ---


@pytest.fixture
def oauth_client(monkeypatch):
    from api import knowledge_connector_oauth as oauth_api

    app = FastAPI()
    app.include_router(oauth_api.router)
    app.dependency_overrides[oauth_api.get_current_user] = lambda: {"user_id": "alice", "role": "admin"}
    monkeypatch.setattr(oauth_api, "_validate_redirect_uri", lambda uri: None)
    monkeypatch.setattr(oauth_api.oauth_flow, "resolve_client_credentials", lambda prov: ("cid", "csec"))
    setex = AsyncMock()
    monkeypatch.setattr(oauth_api, "client_setex", setex)
    monkeypatch.setattr(oauth_api, "get_redis_client", MagicMock())
    return TestClient(app, raise_server_exceptions=False), oauth_api, setex


def _stored_payload(setex):
    import json

    return json.loads(setex.await_args.args[3])


def test_mail_provider_flow_is_filed_under_the_service_owner(oauth_client):
    client, oauth_api, setex = oauth_client
    with patch.object(oauth_api, "check_admin_permission", new=AsyncMock(return_value=True)) as admin_check:
        resp = client.post("/knowledge_base/connectors/oauth/microsoft-mail/authorize", json={"redirect_uri": "x"})
    assert resp.status_code == 200 and resp.json()["connector_id"] == "microsoft365"
    admin_check.assert_awaited_once()
    assert _stored_payload(setex)["owner_id"] == "system"


def test_mail_provider_flow_is_admin_only(oauth_client):
    from fastapi import HTTPException

    client, oauth_api, setex = oauth_client
    deny = AsyncMock(side_effect=HTTPException(status_code=403, detail="no"))
    with patch.object(oauth_api, "check_admin_permission", new=deny):
        resp = client.post("/knowledge_base/connectors/oauth/microsoft-mail/authorize", json={"redirect_uri": "x"})
    assert resp.status_code == 403
    setex.assert_not_awaited()


def test_per_user_provider_flow_is_unchanged(oauth_client):
    client, oauth_api, setex = oauth_client
    with patch.object(oauth_api, "check_admin_permission", new=AsyncMock()) as admin_check:
        resp = client.post("/knowledge_base/connectors/oauth/microsoft/authorize", json={"redirect_uri": "x"})
    assert resp.status_code == 200 and resp.json()["connector_id"] != "microsoft365"
    admin_check.assert_not_awaited()
    assert _stored_payload(setex)["owner_id"] == "alice"


def test_failed_send_is_a_fixed_502(admin, integration):
    integration.execute_action.return_value = {"success": False}
    resp = admin.post(f"{PREFIX}/messages", json={"to": ["a@example.invalid"], "subject": "s", "body": "b"})
    assert resp.status_code == 502 and resp.json()["detail"] == "Microsoft 365 did not accept the request"


def test_client_scopes_are_ignored_for_the_mailbox_provider(oauth_client):
    client, oauth_api, setex = oauth_client
    with patch.object(oauth_api, "check_admin_permission", new=AsyncMock(return_value=True)):
        client.post(
            "/knowledge_base/connectors/oauth/microsoft-mail/authorize",
            json={"redirect_uri": "x", "scopes": ["Mail.ReadWrite", "Files.Read.All"]},
        )
    assert _stored_payload(setex)["scopes"] == []


def test_client_scopes_still_apply_to_a_per_user_provider(oauth_client):
    client, oauth_api, setex = oauth_client
    client.post(
        "/knowledge_base/connectors/oauth/microsoft/authorize", json={"redirect_uri": "x", "scopes": ["Files.Read"]}
    )
    assert _stored_payload(setex)["scopes"] == ["Files.Read"]


@pytest.mark.parametrize(
    "user,expected", [({"username": "root", "role": "admin"}, 200), ({"username": "bob", "role": "user"}, 403)]
)
def test_mailbox_start_uses_the_real_admin_check(oauth_client, real_auth_middleware, user, expected):
    client, oauth_api, setex = oauth_client
    with (
        patch.object(oauth_api, "check_admin_permission", real_auth_middleware.check_admin_permission),
        patch.object(real_auth_middleware, "resolve_human_user", AsyncMock(return_value=user)),
        patch("auth_rbac.audit_role_denied"),
    ):
        resp = client.post("/knowledge_base/connectors/oauth/microsoft-mail/authorize", json={"redirect_uri": "x"})
    assert resp.status_code == expected
    assert setex.await_count == (1 if expected == 200 else 0)


# --- re-authorization stores first, revokes the replaced credential after (#13710) ---


@pytest.fixture
def exchange(monkeypatch):
    from api import knowledge_connector_oauth as oauth_api

    monkeypatch.setattr(oauth_api.oauth_flow, "resolve_client_credentials", lambda prov: ("cid", "csec"))
    monkeypatch.setattr(oauth_api.oauth_flow, "exchange_code", AsyncMock(return_value={"access_token": "at"}))
    store = MagicMock()
    store.store_oauth = AsyncMock(return_value="new")
    store.revoke = AsyncMock()
    monkeypatch.setattr(oauth_api, "get_credential_store", lambda: store)
    monkeypatch.setattr(oauth_api, "find_connector_secret_id", AsyncMock(return_value="old"))
    payload = {
        "provider": "microsoft-mail",
        "owner_id": "system",
        "connector_id": "microsoft365",
        "redirect_uri": "x",
        "code_verifier": "v",
    }
    return oauth_api, store, payload


@pytest.mark.asyncio
async def test_store_failure_leaves_the_old_credential_intact(exchange):
    oauth_api, store, payload = exchange
    store.store_oauth.side_effect = RuntimeError("store down")
    with pytest.raises(RuntimeError):
        await oauth_api._exchange_and_store(payload, "code")
    store.revoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_old_credential_is_revoked_after_the_new_one_is_stored(exchange):
    oauth_api, store, payload = exchange
    assert await oauth_api._exchange_and_store(payload, "code") == "new"
    store.revoke.assert_awaited_once_with("old", "system")


@pytest.mark.asyncio
async def test_revoke_failure_does_not_fail_the_authorization(exchange):
    oauth_api, store, payload = exchange
    store.revoke.side_effect = RuntimeError("boom")
    assert await oauth_api._exchange_and_store(payload, "code") == "new"


# --- a connector can never attach the company mailbox credential (#13710) ---


def _secret(created_by, name="connector:other:auth"):
    return {"id": "s1", "name": name, "created_by": created_by}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "secret,owner,ok",
    [
        (_secret("alice"), "alice", True),
        (_secret("bob"), "alice", False),
        (_secret(""), "alice", False),
        (_secret("system", "connector:microsoft365:auth"), "system", False),
        (_secret("system"), "alice", False),
        (_secret("alice", "connector:microsoft365:auth"), "alice", False),
        (None, "alice", False),
    ],
)
async def test_attachable_secret_id(secret, owner, ok):
    from fastapi import HTTPException

    from api import knowledge_connector_oauth as oauth_api

    svc = MagicMock()
    svc.get_secret.return_value = secret
    with patch("services.secrets_service.get_secrets_service", return_value=svc):
        if ok:
            assert await oauth_api.attachable_secret_id("s1", owner) == "s1"
        else:
            with pytest.raises(HTTPException) as raised:
                await oauth_api.attachable_secret_id("s1", owner)
            assert raised.value.status_code == 400
