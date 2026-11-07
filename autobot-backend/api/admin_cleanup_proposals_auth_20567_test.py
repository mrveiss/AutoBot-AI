# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: the cleanup routes sit behind the REAL ``check_admin_permission`` gate and the real ``get_current_user``.

The handler tests call the functions directly, so the router dependency never runs there. Here the REAL auth
stack answers through a ``TestClient``: only the identity it reads and the database (a ``FakeAsyncSession``: auth, not transactions, is under test) are stood in.
"""

from __future__ import annotations

import importlib
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services import install_cleanup_actions as acts
from services.approval_gate_service import ApprovalGateService
from testkit.fake_async_session import FakeAsyncSession
from tests.conftest import load_real_auth_middleware

_INTERNAL_KEY = {"X-Internal-API-Key": "internal-service-key-for-tests"}
_APPROVAL_ID = uuid.UUID("00000000-0000-4000-8000-000000000567")
_PATHS = {
    "status": ("GET", "/api/admin/env-copies-cleanup"),
    "propose": ("POST", "/api/admin/env-copies-cleanup/requests"),
}


def _person(role: str) -> dict:
    return {"username": role, "role": role, "user_id": "u-567", "id": "u-567", "auth_method": "jwt"}


@pytest.fixture
def client(monkeypatch):
    """A client whose gate is the production code; ``identity.user`` is the human it resolves."""
    real = load_real_auth_middleware()
    monkeypatch.setitem(sys.modules, "auth_middleware", real)
    monkeypatch.delitem(sys.modules, "api.admin_cleanup_proposals", raising=False)
    routes = importlib.import_module("api.admin_cleanup_proposals")
    identity = SimpleNamespace(user=None)
    monkeypatch.setattr(real, "resolve_human_user", AsyncMock(side_effect=lambda _request: identity.user))
    monkeypatch.setattr(
        real, "verify_internal_api_key", lambda provided: provided == _INTERNAL_KEY["X-Internal-API-Key"]
    )
    plan = acts.CleanupPlan(targets=(acts.Path("a"),), kept=acts.Path("b"))
    monkeypatch.setattr(routes, "plan_env_copies", lambda: plan)
    created = SimpleNamespace(id=_APPROVAL_ID, status="pending")
    monkeypatch.setattr(ApprovalGateService, "list_approvals", AsyncMock(return_value=[]))
    monkeypatch.setattr(ApprovalGateService, "create_approval", AsyncMock(return_value=created))
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    app.dependency_overrides[routes.get_db_session] = lambda: FakeAsyncSession()
    yield TestClient(app, raise_server_exceptions=False), identity
    sys.modules.pop("api.admin_cleanup_proposals", None)


@pytest.mark.parametrize(("method", "path"), _PATHS.values(), ids=list(_PATHS))
def test_an_anonymous_caller_is_401(client, method: str, path: str) -> None:
    test_client, _ = client

    assert test_client.request(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), _PATHS.values(), ids=list(_PATHS))
def test_a_non_admin_is_403(client, method: str, path: str) -> None:
    test_client, identity = client
    identity.user = _person("user")

    assert test_client.request(method, path).status_code == 403


@pytest.mark.parametrize(("method", "path"), _PATHS.values(), ids=list(_PATHS))
def test_the_internal_key_alone_is_refused(client, method: str, path: str) -> None:
    test_client, _ = client

    assert test_client.request(method, path, headers=_INTERNAL_KEY).status_code in (401, 403)


def test_an_admin_passes_the_gate(client) -> None:
    test_client, identity = client
    identity.user = _person("admin")

    assert test_client.get(_PATHS["status"][1]).status_code == 200


def test_an_admin_proposal_is_201_and_names_the_approval(client) -> None:
    test_client, identity = client
    identity.user = _person("admin")

    reply = test_client.post(_PATHS["propose"][1])

    assert reply.status_code == 201
    assert reply.json()["approval_id"] == str(_APPROVAL_ID) and reply.json()["action"] == acts.ENV_COPIES_ACTION
