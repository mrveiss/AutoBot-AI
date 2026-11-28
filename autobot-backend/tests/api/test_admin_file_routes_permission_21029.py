# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin file routes use the admin permission dependency (#21029).

Judged with the REAL ``check_admin_permission`` (the way ``test_rum_access_16375``
does): under pytest ``auth_middleware`` is a conftest stub, so the dependency the
routes name is overridden with the real one and only the identity it reads is
controlled. Also pins the service-auth exemption list to the sandbox routes.
"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.files as files_api
import auth_middleware as _stub_auth
from middleware.service_auth_enforcement import is_path_exempt

_ADMIN_USER = {"username": "root", "role": "admin"}
_NON_ADMIN = {"username": "viewer", "role": "user"}
_ROUTES = (("/api/files", {}), ("/api/files/read", {"path": "PLACEHOLDER"}))


@pytest.fixture
def client(real_auth_middleware, monkeypatch, tmp_path):
    identity = SimpleNamespace(user=None)

    async def _no_token(_request):
        return None

    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: identity.user,
        _extract_user_from_run_jwt=_no_token,
        _extract_user_from_device_jwt=_no_token,
    )
    monkeypatch.setattr(real_auth_middleware, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(files_api, "_ADMIN_ALLOWED_DIRS", (str(tmp_path),))
    (tmp_path / "note.txt").write_text("hello", encoding="utf-8")
    app = FastAPI()
    app.include_router(files_api.router, prefix="/api/files")
    app.dependency_overrides[files_api.ensure_sandbox_root] = lambda: None
    app.dependency_overrides[_stub_auth.check_admin_permission] = real_auth_middleware.check_admin_permission
    return TestClient(app), identity, tmp_path


def _get(test_client, route, params, tmp_path):
    query = {k: (str(tmp_path / "note.txt") if v == "PLACEHOLDER" else v) for k, v in params.items()}
    if route == "/api/files":
        query = {"path": str(tmp_path)}
    return test_client.get(route, params=query)


@pytest.mark.parametrize(("route", "params"), _ROUTES)
def test_admin_file_routes_require_admin_permission_anonymous(client, route, params) -> None:
    test_client, _, tmp_path = client
    assert _get(test_client, route, params, tmp_path).status_code in (401, 403)


@pytest.mark.parametrize(("route", "params"), _ROUTES)
def test_admin_file_routes_require_admin_permission_non_admin(client, route, params) -> None:
    test_client, identity, tmp_path = client
    identity.user = _NON_ADMIN
    assert _get(test_client, route, params, tmp_path).status_code == 403


@pytest.mark.parametrize(("route", "params"), _ROUTES)
def test_admin_file_routes_accept_admin(client, route, params) -> None:
    test_client, identity, tmp_path = client
    identity.user = _ADMIN_USER
    response = _get(test_client, route, params, tmp_path)
    assert response.status_code == 200
    assert "files" in response.json() or response.json() == {"content": "hello"}


@pytest.mark.parametrize("path", ["/api/files", "/api/files/", "/api/files/read"])
def test_service_auth_exemption_excludes_admin_file_paths(path: str) -> None:
    assert is_path_exempt(path) is False


@pytest.mark.parametrize(
    "path", ["/api/files/list", "/api/files/upload", "/api/files/download/a", "/api/files/view/a", "/api/files/stats"]
)
def test_service_auth_exemption_keeps_sandbox_file_paths(path: str) -> None:
    assert is_path_exempt(path) is True
