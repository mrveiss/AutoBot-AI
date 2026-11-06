# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20567: the cleanup routes sit behind the REAL ``require_role("admin", "superadmin")`` gate.

The handler tests call the functions directly, so the router dependency never runs there. Here the
REAL auth stack answers through a ``TestClient``: only the identity it reads is stood in.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import auth_rbac
from api import admin_cleanup_proposals as routes
from services import install_cleanup_actions as acts
from tests.conftest import load_real_auth_middleware

_INTERNAL_KEY = {"X-Internal-API-Key": "internal-service-key-for-tests"}
_PATHS = {
    "status": ("GET", "/api/admin/env-copies-cleanup"),
    "propose": ("POST", "/api/admin/env-copies-cleanup/requests"),
}


@pytest.fixture
def client(monkeypatch):
    """A client whose gate is the production code; ``identity.user`` is what it sees."""
    real = load_real_auth_middleware()
    identity = SimpleNamespace(user=None)
    middleware = SimpleNamespace(get_user_from_request=lambda _request: identity.user)
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(
        real, "verify_internal_api_key", lambda provided: provided == _INTERNAL_KEY["X-Internal-API-Key"]
    )
    monkeypatch.setattr(auth_rbac, "resolve_human_user", real.resolve_human_user)
    monkeypatch.setattr(routes, "plan_env_copies", lambda: acts.CleanupPlan())
    app = FastAPI()
    app.include_router(routes.router, prefix="/api")
    return TestClient(app, raise_server_exceptions=False), identity


@pytest.mark.parametrize(("method", "path"), _PATHS.values(), ids=_PATHS.keys())
def test_an_anonymous_caller_is_401(client, method: str, path: str) -> None:
    test_client, _ = client

    assert test_client.request(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), _PATHS.values(), ids=_PATHS.keys())
def test_a_non_admin_is_403(client, method: str, path: str) -> None:
    test_client, identity = client
    identity.user = {"username": "viewer", "role": "user"}

    assert test_client.request(method, path).status_code == 403


@pytest.mark.parametrize(("method", "path"), _PATHS.values(), ids=_PATHS.keys())
def test_the_internal_key_alone_is_refused(client, method: str, path: str) -> None:
    test_client, _ = client

    assert test_client.request(method, path, headers=_INTERNAL_KEY).status_code in (401, 403)


def test_an_admin_passes_the_gate(client) -> None:
    test_client, identity = client
    identity.user = {"username": "admin", "role": "admin"}

    assert test_client.get(_PATHS["status"][1]).status_code == 200
