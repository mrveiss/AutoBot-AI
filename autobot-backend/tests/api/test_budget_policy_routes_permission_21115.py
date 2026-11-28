# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Budget policy routes use the admin permission dependency (#21115).

Judged with the REAL ``check_admin_permission`` (as ``test_admin_file_routes_permission_21029``
does): under pytest ``auth_middleware`` is a conftest stub, so the dependency the routes name
is overridden with the real one and only the identity it reads is controlled.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.budget_policies as bp
import auth_middleware as _stub_auth
from api.user_management.dependencies import get_db_session
from testkit.fake_async_session import FakeAsyncSession
from testkit.fake_result import FakeResult

_ADMIN_USER = {"username": "root", "role": "admin"}
_NON_ADMIN = {"username": "viewer", "role": "user"}
_BODY = {"scope": "agent", "scope_id": "a1", "period": "day", "threshold_usd": 5.0}
_POLICY = SimpleNamespace(
    id="p1",
    scope="agent",
    scope_id="a1",
    period="day",
    threshold_usd=5.0,
    warning_pct=0.8,
    action="alert",
    enabled=True,
    name="n",
    description="d",
    created_at="2026-01-01T00:00:00",
    updated_at="2026-01-01T00:00:00",
)
# (method, url, json body, expected status for an admin)
_ROUTES = (
    ("POST", "/api/budget-policies", _BODY, 201),
    ("GET", "/api/budget-policies", None, 200),
    ("GET", "/api/budget-policies/p1", None, 200),
    ("PATCH", "/api/budget-policies/p1", _BODY, 200),
    ("DELETE", "/api/budget-policies/p1", None, 204),
    ("POST", "/api/budget-policies/a1/resume", None, 200),
    ("GET", "/api/budget-policies/a1/status", None, 200),
)


@pytest.fixture
def client(real_auth_middleware, monkeypatch):
    identity = SimpleNamespace(user=None)

    async def _no_token(_request):
        return None

    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: identity.user,
        _extract_user_from_run_jwt=_no_token,
        _extract_user_from_device_jwt=_no_token,
    )
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)

    async def _policy(*_a, **_k):
        return _POLICY

    async def _policies(*_a, **_k):
        return [_POLICY]

    async def _true(*_a, **_k):
        return True

    monkeypatch.setattr(bp, "create_policy", _policy)
    monkeypatch.setattr(bp, "get_policy", _policy)
    monkeypatch.setattr(bp, "patch_policy", _policy)
    monkeypatch.setattr(bp, "list_all_policies", _policies)
    monkeypatch.setattr(bp, "list_policies_for_scope", _policies)
    monkeypatch.setattr(bp, "delete_policy", _true)
    monkeypatch.setattr(bp, "resume_agent", _true)

    async def _session():
        return FakeAsyncSession(default_result=FakeResult([]))

    app = FastAPI()
    app.include_router(bp.router, prefix="/api")
    app.dependency_overrides[_stub_auth.check_admin_permission] = real_auth_middleware.check_admin_permission
    app.dependency_overrides[get_db_session] = _session
    return TestClient(app), identity


@pytest.mark.parametrize(("method", "url", "body", "_ok"), _ROUTES)
def test_budget_policy_routes_require_admin_permission_anonymous(client, method, url, body, _ok) -> None:
    test_client, _ = client
    assert test_client.request(method, url, json=body).status_code in (401, 403)


@pytest.mark.parametrize(("method", "url", "body", "_ok"), _ROUTES)
def test_budget_policy_routes_require_admin_permission_non_admin(client, method, url, body, _ok) -> None:
    test_client, identity = client
    identity.user = _NON_ADMIN
    assert test_client.request(method, url, json=body).status_code == 403


@pytest.mark.parametrize(("method", "url", "body", "ok"), _ROUTES)
def test_budget_policy_routes_accept_admin(client, method, url, body, ok) -> None:
    test_client, identity = client
    identity.user = _ADMIN_USER
    assert test_client.request(method, url, json=body).status_code == ok
