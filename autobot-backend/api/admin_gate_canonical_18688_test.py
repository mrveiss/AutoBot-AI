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
    manager.stop_service = AsyncMock(
        return_value=SimpleNamespace(
            success=True,
            operation="stop",
            message="stopped",
            duration_seconds=0.1,
            timestamp="2026-10-18T00:00:00Z",
            new_status="stopped",
            error=None,
        )
    )
    app = FastAPI()
    app.include_router(module.router, prefix="/api")
    app.dependency_overrides[module.get_service_manager] = lambda: manager
    return TestClient(app, raise_server_exceptions=False), manager


_OPERATIONS = "/api/audit/operations"
_STOP = "/api/stop"


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


def test_redis_status_needs_a_user(stop_client, identity):
    client, _manager = stop_client
    assert client.get(_STATUS).status_code == 401
    identity.user = _USER
    assert client.get(_STATUS).status_code != 401
