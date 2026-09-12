# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Infrastructure hosts are admin-only (#16426).

``GET /api/infrastructure/hosts`` and ``DELETE /api/infrastructure/hosts/{id}``
depended only on ``get_current_user``, so any authenticated caller could list
every host's connection metadata (host, ports, username) and delete any host.
Both now depend on ``check_admin_permission``, matching ``api/secrets.py``.

Judged with the REAL dependency, the same pattern as ``test_skills_auth_16368``:
under pytest ``auth_middleware`` is the conftest stub, whose ``get_current_user``
always returns an admin, so the router's ``Depends(...)`` captured stub
callables. This overrides exactly the object the router module bound with the
real function from ``real_auth_middleware``, and controls only the identity
the real code reads.

``_load_secrets_hosts`` is patched directly so these tests are only about the
auth gate, not the secrets-store data layer underneath it.
"""

from types import SimpleNamespace
from typing import Dict, Tuple

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.infrastructure as infrastructure_api
import api.secrets as secrets_api

_ADMIN_USER = {"username": "admin", "role": "admin"}
_NON_ADMIN_USER = {"username": "viewer", "role": "user"}

_HOST = {
    "id": "host-1",
    "name": "demo",
    "host": "10.0.0.1",
    "ssh_port": 22,
    "vnc_port": None,
    "username": "root",
    "os": None,
    "description": "",
    "capabilities": ["ssh"],
}

_ROUTES: Dict[str, Tuple[str, str]] = {
    "get": ("GET", "/api/infrastructure/hosts"),
    "delete": ("DELETE", "/api/infrastructure/hosts/host-1"),
}


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(infrastructure_api.router, prefix="/api/infrastructure")
    return app


@pytest.fixture
def client(real_auth_middleware, monkeypatch):
    """A client whose gate is the production code; ``identity.user`` is what it sees."""
    identity = SimpleNamespace(user=None)
    middleware = SimpleNamespace(get_user_from_request=lambda _request: identity.user)
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(infrastructure_api, "_load_secrets_hosts", lambda: [_HOST])

    app = _app()
    app.dependency_overrides[infrastructure_api.check_admin_permission] = real_auth_middleware.check_admin_permission
    return TestClient(app), identity


@pytest.mark.parametrize(("method", "path"), _ROUTES.values(), ids=_ROUTES.keys())
def test_an_anonymous_caller_is_refused(client, method: str, path: str) -> None:
    test_client, _ = client

    assert test_client.request(method, path).status_code == 401


@pytest.mark.parametrize(("method", "path"), _ROUTES.values(), ids=_ROUTES.keys())
def test_a_non_admin_is_refused(client, method: str, path: str) -> None:
    test_client, identity = client
    identity.user = dict(_NON_ADMIN_USER)

    assert test_client.request(method, path).status_code == 403


def test_an_admin_lists_hosts(client) -> None:
    test_client, identity = client
    identity.user = dict(_ADMIN_USER)

    response = test_client.get("/api/infrastructure/hosts")

    assert response.status_code == 200, response.text
    assert response.json()["hosts"] == [_HOST]


def test_an_admin_deletes_a_host(client, monkeypatch) -> None:
    test_client, identity = client
    identity.user = dict(_ADMIN_USER)
    monkeypatch.setattr(secrets_api.secrets_manager, "delete_secret", lambda _host_id: True)

    response = test_client.delete("/api/infrastructure/hosts/host-1")

    assert response.status_code == 200, response.text
