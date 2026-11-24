# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#13710: the Microsoft 365 (Outlook mail) router through a real FastAPI app.

The integration and the secrets store are mocked: no Graph call, no credential.
Auth is the REAL ``check_admin_permission``.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import integration_microsoft365 as m365
from integrations.base import IntegrationHealth, IntegrationStatus

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
    """A mocked integration, with the secrets store returning a dummy token."""
    mock = MagicMock()
    mock.execute_action = AsyncMock(return_value={"value": []})
    mock.test_connection = AsyncMock(
        return_value=IntegrationHealth(provider="microsoft365", status=IntegrationStatus.CONNECTED)
    )
    svc = MagicMock()
    svc.get_secret.return_value = {"value": "dummy-token"}
    with (
        patch.object(m365, "get_secrets_service", return_value=svc),
        patch.object(m365, "Microsoft365Integration", return_value=mock) as cls,
    ):
        mock.cls, mock.svc = cls, svc
        yield mock


@pytest.fixture
def admin(app, as_user, integration):
    with as_user({"username": "root", "role": "admin"}):
        yield TestClient(app, raise_server_exceptions=False)


def test_list_messages(admin, integration):
    resp = admin.get(f"{PREFIX}/messages", params={"folder_id": "inbox", "limit": 5})
    assert resp.status_code == 200
    integration.execute_action.assert_awaited_once_with("list_messages", {"folder_id": "inbox", "limit": 5})


def test_token_comes_from_the_secrets_store(admin, integration):
    admin.get(f"{PREFIX}/folders")
    kwargs = integration.svc.get_secret.call_args.kwargs
    assert kwargs["name"] == m365.MICROSOFT365_CREDENTIAL_ENTRY and kwargs["include_value"] is True
    assert integration.cls.call_args.args[0].token == "dummy-token"


def test_token_query_parameter_is_not_accepted(admin, integration):
    admin.get(f"{PREFIX}/folders", params={"token": "attacker"})
    assert integration.cls.call_args.args[0].token == "dummy-token"


def test_missing_secret_is_a_400(admin, integration):
    integration.svc.get_secret.return_value = None
    assert admin.get(f"{PREFIX}/messages").status_code == 400
    integration.execute_action.assert_not_awaited()


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
