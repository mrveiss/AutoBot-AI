# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``audit`` and ``redis_service`` /stop use the ONE canonical admin gate (#18688).

Behaviour deltas the owner approved when the local copies were dropped:

* the audit routes now admit the internal service key (the canonical gate does);
* a caller whose role is missing gets 401 on ``/redis-service/stop`` (was 403);
* the catch-all 500 ``API_0003`` of the old audit gate is gone.

Under pytest ``auth_middleware`` is a stub (``testkit/auth_middleware_stub.py``), so
overriding a router's gate would hide which function the route really depends on.
These tests instead execute a FRESH copy of each router module with the REAL
``auth_middleware`` bound as the import, so the route's own ``Depends`` is what is
judged -- only the identity the real gate reads is faked.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from tests.conftest import load_real_auth_middleware

_API = Path(__file__).parent
_KEY = "test-internal-key"
_ADMIN = {"username": "root", "role": "admin"}
_NO_ROLE = {"username": "ghost"}
_USER = {"username": "viewer", "role": "user"}


@pytest.fixture
def identity(monkeypatch):
    """The user the real gate sees; the internal-key check is pinned to ``_KEY``."""
    real = load_real_auth_middleware()
    state = SimpleNamespace(user=None)
    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: state.user,
        # get_current_user's run/device-JWT fallbacks: no such token in these requests.
        _extract_user_from_run_jwt=AsyncMock(return_value=None),
        _extract_user_from_device_jwt=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(real, "verify_internal_api_key", lambda provided: provided == _KEY)
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    import security.human_admin as human_admin

    monkeypatch.setattr(human_admin, "auth_middleware", real)  # the same key check the gate makes
    return state


def _fresh(name: str):
    """Execute ``api/<name>.py`` under an alias, importing the (patched-in) real gate."""
    spec = importlib.util.spec_from_file_location(f"_fresh_18688_{name}", _API / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def audit_client(identity):
    module = _fresh("audit")
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    audit_logger = MagicMock()
    audit_logger.query_logs = AsyncMock(return_value=[])
    audit_logger.cleanup_old_logs = AsyncMock(return_value=None)
    with patch.object(module, "get_audit_logger", return_value=audit_logger):
        client = TestClient(app, raise_server_exceptions=False)
        client.audit_logger = audit_logger  # so a test can prove nothing was deleted
        yield client


@pytest.fixture
def stop_client(identity):
    module = _fresh("redis_service")
    manager = MagicMock()
    manager.get_service_status = AsyncMock(
        return_value=SimpleNamespace(
            status="running", pid=1, uptime_seconds=1.0, memory_mb=1.0, last_check="2026-10-18T00:00:00Z"
        )
    )
    outcome = SimpleNamespace(
        success=True,
        operation="op",
        message="done",
        duration_seconds=0.1,
        timestamp="2026-10-18T00:00:00Z",
        new_status="stopped",
        error=None,
    )
    for operation in ("start_service", "stop_service", "restart_service"):
        setattr(manager, operation, AsyncMock(return_value=outcome))
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.dependency_overrides[module.get_service_manager] = lambda: manager
    return TestClient(app, raise_server_exceptions=False), manager


_OPERATIONS = "/api/audit/operations"
_STOP = "/api/stop"
_START = "/api/start"
_RESTART = "/api/restart"


def test_the_internal_key_is_admitted_on_an_audit_route(audit_client, identity):
    identity.user = None
    response = audit_client.get(_OPERATIONS, headers={"X-Internal-API-Key": _KEY})
    assert response.status_code == 200


def test_a_wrong_internal_key_is_not_admitted_on_an_audit_route(audit_client, identity):
    identity.user = None
    assert audit_client.get(_OPERATIONS, headers={"X-Internal-API-Key": "wrong"}).status_code == 401


def test_a_missing_role_gives_401_on_an_audit_route(audit_client, identity):
    identity.user = dict(_NO_ROLE)
    assert audit_client.get(_OPERATIONS).status_code == 401


def test_a_non_admin_gives_403_on_an_audit_route(audit_client, identity):
    identity.user = dict(_USER)
    assert audit_client.get(_OPERATIONS).status_code == 403


def test_an_admin_gives_200_on_an_audit_route(audit_client, identity):
    identity.user = dict(_ADMIN)
    assert audit_client.get(_OPERATIONS).status_code == 200


def test_a_missing_role_gives_401_on_redis_service_stop(stop_client, identity):
    client, manager = stop_client
    identity.user = dict(_NO_ROLE)
    assert client.post(_STOP).status_code == 401
    manager.stop_service.assert_not_awaited()


def test_a_non_admin_gives_403_on_redis_service_stop(stop_client, identity):
    client, manager = stop_client
    identity.user = dict(_USER)
    assert client.post(_STOP).status_code == 403
    manager.stop_service.assert_not_awaited()


def test_an_admin_gives_200_on_redis_service_stop_and_is_named_in_the_audit(stop_client, identity):
    client, manager = stop_client
    identity.user = dict(_ADMIN)
    assert client.post(_STOP).status_code == 200
    manager.stop_service.assert_awaited_once_with(user_id="root")


# -- destructive routes are for human admins only (owner decision 2026-10-18) ---------------------

_CLEANUP = "/api/audit/cleanup"
_CLEANUP_BODY = {"confirm": True, "days_to_keep": 90}
_STATUS = "/api/status"


def test_the_internal_key_cannot_stop_redis(stop_client, identity):
    client, manager = stop_client
    response = client.post(_STOP, headers={"X-Internal-API-Key": _KEY})
    assert response.status_code == 403
    manager.stop_service.assert_not_awaited()


def test_the_internal_key_cannot_delete_audit_logs(audit_client, identity):
    response = audit_client.post(_CLEANUP, json=_CLEANUP_BODY, headers={"X-Internal-API-Key": _KEY})
    assert response.status_code == 403
    audit_client.audit_logger.cleanup_old_logs.assert_not_awaited()


def test_a_human_admin_can_still_delete_audit_logs(audit_client, identity):
    identity.user = _ADMIN
    assert audit_client.post(_CLEANUP, json=_CLEANUP_BODY).status_code == 200
    audit_client.audit_logger.cleanup_old_logs.assert_awaited_once()


def test_a_wrong_key_with_a_human_admin_session_is_not_refused_as_a_service(audit_client, identity):
    """Only a VALID service key is refused; a stray header doesn't block the human admin."""
    identity.user = _ADMIN
    assert audit_client.post(_CLEANUP, json=_CLEANUP_BODY, headers={"X-Internal-API-Key": "wrong"}).status_code == 200


# -- /start and /restart: the canonical operator-or-admin gate, service key refused (#18688) -------

_OPERATOR = {"username": "ops", "role": "operator"}
_OPERATIONS_BY_PATH = [(_START, "start_service"), (_RESTART, "restart_service")]


@pytest.mark.parametrize(("path", "operation"), _OPERATIONS_BY_PATH)
def test_the_internal_key_cannot_start_or_restart_redis(stop_client, identity, path, operation):
    client, manager = stop_client
    assert client.post(path, headers={"X-Internal-API-Key": _KEY}).status_code == 403
    getattr(manager, operation).assert_not_awaited()


@pytest.mark.parametrize(("path", "operation"), _OPERATIONS_BY_PATH)
def test_a_missing_role_gives_401_on_redis_start_and_restart(stop_client, identity, path, operation):
    client, manager = stop_client
    identity.user = dict(_NO_ROLE)
    assert client.post(path).status_code == 401
    getattr(manager, operation).assert_not_awaited()


@pytest.mark.parametrize(("path", "operation"), _OPERATIONS_BY_PATH)
def test_a_non_operator_gives_403_on_redis_start_and_restart(stop_client, identity, path, operation):
    client, manager = stop_client
    identity.user = dict(_USER)
    assert client.post(path).status_code == 403
    getattr(manager, operation).assert_not_awaited()


@pytest.mark.parametrize(("path", "operation"), _OPERATIONS_BY_PATH)
@pytest.mark.parametrize("user", [_OPERATOR, _ADMIN], ids=["operator", "admin"])
def test_an_operator_or_admin_gives_200_and_is_named_in_the_audit(stop_client, identity, path, operation, user):
    client, manager = stop_client
    identity.user = dict(user)
    assert client.post(path).status_code == 200
    getattr(manager, operation).assert_awaited_once_with(user_id=user["username"])


@pytest.mark.parametrize(("path", "operation"), _OPERATIONS_BY_PATH)
def test_a_password_change_revoked_jwt_gives_401_on_redis_start_and_restart(
    stop_client, identity, monkeypatch, path, operation
):
    import auth_revocation  # noqa: PLC0415

    client, manager = stop_client
    identity.user = {**_OPERATOR, "auth_method": "jwt", "sub": "ops", "iat": 1}
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=True))
    response = client.post(path)
    assert response.status_code == 401
    getattr(manager, operation).assert_not_awaited()
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False))
    assert client.post(path).status_code == 200  # contrast: the same JWT, not revoked


def test_redis_status_needs_a_user(stop_client, identity):
    client, _manager = stop_client
    assert client.get(_STATUS).status_code == 401
    identity.user = _USER
    assert client.get(_STATUS).status_code != 401


# -- service_messages uses the canonical human-admin gate (owner decision 2026-10-18) --------------

_MESSAGES = "/api/service-messages/latest"


@pytest.fixture
def messages_client(identity, monkeypatch):
    # HUMAN_ADMIN_DEPENDENCIES binds the gate when ``security.human_admin`` first loads (the
    # stub, under pytest). Load a FRESH copy against the real gate so the route's own list is judged.
    spec = importlib.util.spec_from_file_location(
        "_fresh_18688_human_admin", _API.parent / "security" / "human_admin.py"
    )
    human_admin = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(human_admin)
    monkeypatch.setitem(sys.modules, "security.human_admin", human_admin)
    module = _fresh("service_messages")
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    bus = MagicMock()
    bus.get_latest = AsyncMock(return_value=[])
    with patch.object(module, "get_message_bus", return_value=bus):
        client = TestClient(app, raise_server_exceptions=False)
        client.bus = bus  # so a test can prove a refused caller never reached the bus
        yield client


def test_service_messages_anonymous_gives_401(messages_client, identity):
    identity.user = None
    assert messages_client.get(_MESSAGES).status_code == 401
    messages_client.bus.get_latest.assert_not_awaited()


def test_service_messages_missing_role_gives_401_not_500(messages_client, identity):
    identity.user = dict(_NO_ROLE)
    assert messages_client.get(_MESSAGES).status_code == 401


def test_service_messages_non_admin_gives_403(messages_client, identity):
    identity.user = dict(_USER)
    assert messages_client.get(_MESSAGES).status_code == 403
    messages_client.bus.get_latest.assert_not_awaited()


def test_service_messages_refuses_the_internal_key(messages_client, identity):
    response = messages_client.get(_MESSAGES, headers={"X-Internal-API-Key": _KEY})
    assert response.status_code == 403
    messages_client.bus.get_latest.assert_not_awaited()


def test_service_messages_admin_gives_200(messages_client, identity):
    identity.user = dict(_ADMIN)
    assert messages_client.get(_MESSAGES).status_code == 200
    messages_client.bus.get_latest.assert_awaited_once()
