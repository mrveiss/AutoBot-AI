# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The service key is not an admin, except on a route that names its caller (#16333, owner ruling b)."""

import logging
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import APIRouter, Depends, FastAPI
from fastapi.testclient import TestClient

import auth_service_opt_in
from auth_service_opt_in import service_opt_in
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_once import reset_log_once
from services.audit.taxonomy import AuditAction

KEY = {"X-Internal-API-Key": "k"}


@pytest.fixture
def am(real_auth_middleware):
    """The REAL auth_middleware: the suite-wide stub would make every gate pass."""
    return real_auth_middleware


def _app(am) -> FastAPI:
    admin = APIRouter(dependencies=[Depends(am.check_admin_permission)])

    @admin.get("/gated")
    async def gated():
        return {"ok": True}

    @admin.get("/opted")
    @with_error_handling(category=ErrorCategory.SERVER_ERROR, operation="t", error_code_prefix="T")
    @service_opt_in("test-caller")
    async def opted():
        return {"ok": True}

    user = APIRouter()

    @user.get("/user")
    async def user_only(current: dict = Depends(am.get_current_user)):
        return current

    app = FastAPI()
    app.include_router(admin)
    app.include_router(user)
    return app


@pytest.fixture
def client(am):
    return TestClient(_app(am), raise_server_exceptions=False)


@pytest.fixture
def key_valid():
    with patch.object(auth_service_opt_in, "verify_internal_api_key", side_effect=lambda v: v == "k"):
        yield


@pytest.fixture
def as_user(am):
    return lambda user: patch.object(am, "resolve_human_user", AsyncMock(return_value=user))


def test_the_key_alone_is_not_an_admin(client, key_valid, as_user):
    with as_user(None):
        assert client.get("/gated", headers=KEY).status_code == 401


def test_the_key_alone_is_not_a_user_either(client, key_valid, as_user):
    """It used to become a synthetic admin on every get_current_user route."""
    with as_user(None):
        assert client.get("/user", headers=KEY).status_code == 401


def test_a_route_that_names_its_caller_admits_the_key_and_audits_it(client, key_valid, as_user):
    """``/opted`` is wrapped by ``with_error_handling`` too: the marker survives the route decorators."""
    with as_user(None), patch("services.audit.audit.record_committed", AsyncMock(return_value=True)) as recorded:
        assert client.get("/opted", headers=KEY).status_code == 200
    event = recorded.await_args.args[0]
    assert event.action == AuditAction.SERVICE_KEY_ADMITTED.value and event.actor_id == "service:test-caller"
    assert event.resource_id == "/opted"


def test_an_admission_whose_audit_row_is_not_committed_is_refused(client, key_valid, as_user):
    """Fail closed, by decision: the exception exists because it is recorded."""
    with as_user(None), patch("services.audit.audit.record_committed", AsyncMock(return_value=False)):
        response = client.get("/opted", headers=KEY)
    assert response.status_code == 503
    assert response.json()["detail"] == auth_service_opt_in.ADMISSION_NOT_AUDITED


def test_a_wrong_key_is_not_admitted_even_where_opted_in(client, key_valid, as_user):
    with as_user(None):
        assert client.get("/opted", headers={"X-Internal-API-Key": "nope"}).status_code == 401


def test_a_human_admin_passes_both_gates(client, as_user):
    with as_user({"username": "ada", "role": "admin"}):
        assert client.get("/gated").status_code == 200
        assert client.get("/opted").status_code == 200


def test_a_non_admin_gets_the_same_403_everywhere(client, as_user):
    with as_user({"username": "bob", "role": "user"}):
        gated, opted = client.get("/gated"), client.get("/opted")
    assert gated.status_code == opted.status_code == 403
    assert gated.json() == opted.json()


def test_a_proxied_call_whose_session_does_not_verify_names_the_likely_cause_once(client, key_valid, caplog, as_user):
    reset_log_once()
    with as_user(None), caplog.at_level(logging.WARNING):
        client.get("/gated", headers={**KEY, "Authorization": "Bearer unverifiable"})
        client.get("/gated", headers={**KEY, "Authorization": "Bearer unverifiable"})
    hits = [r for r in caplog.records if "JWT secrets may differ" in r.getMessage()]
    assert len(hits) == 1


def test_one_request_writes_one_audit_row_however_many_gates_ask(am, key_valid, as_user):
    """The router's admin gate and the route's own get_current_user both run; the row is written once."""
    router = APIRouter(dependencies=[Depends(am.check_admin_permission)])

    @router.get("/both")
    @service_opt_in("test-caller")
    async def both(current: dict = Depends(am.get_current_user)):
        return current

    app = FastAPI()
    app.include_router(router)
    with as_user(None), patch("services.audit.audit.record_committed", AsyncMock(return_value=True)) as recorded:
        response = TestClient(app).get("/both", headers=KEY)
    assert response.status_code == 200 and response.json()["role"] == "service"
    assert recorded.await_count == 1


def test_a_refused_non_admin_is_audited_by_the_one_gate(client, as_user):
    """PR B (#16333): routes that used require_role keep their role_denied row on check_admin_permission."""
    with as_user({"username": "bob", "role": "user"}), patch("auth_rbac.audit_role_denied") as audited:
        assert client.get("/gated").status_code == 403
    user, allowed, role, _request = audited.call_args.args
    assert user["username"] == "bob" and role == "user" and set(allowed) == {"admin", "superadmin"}


def test_a_session_with_no_role_is_401_and_a_role_is_recorded_normalised(client, as_user):
    """PR B (#16333): a role-less session is 401 on the one gate (require_role gave 403); the row's role is lowercased."""
    with as_user({"username": "nobody", "role": ""}):
        assert client.get("/gated").status_code == 401
    with as_user({"username": "bob", "role": "USER"}), patch("auth_rbac.audit_role_denied") as audited:
        assert client.get("/gated").status_code == 403
    assert audited.call_args.args[2] == "user"
