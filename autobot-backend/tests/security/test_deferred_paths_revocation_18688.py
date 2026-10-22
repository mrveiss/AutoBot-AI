# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The paths slice 3 deferred now refuse a password-change-revoked JWT (#18688).

Covered: ``/auth/check``, ``/auth/change-password``, ``/auth/refresh``, ``/auth/permissions/{op}``,
``/auth/validate`` (the caller, and the token being introspected), ``/auth/logout`` (idempotent --
a void credential is simply not named in the audit), and ``check_file_permissions`` with its
callers in ``files`` / ``sandbox_files`` / ``conversation_files``.

The REAL ``auth_middleware`` gate runs (``tests.conftest.load_real_auth_middleware``); only the
identity it reads and the epoch lookup are stood in. Each path has a contrast: the same JWT,
not revoked, passes.
"""

import asyncio
import importlib
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from tests.conftest import load_real_auth_middleware

_JWT_USER = {
    "username": "alice",
    "role": "admin",
    "user_id": str(uuid.uuid4()),
    "sub": "alice",
    "iat": 1,
    "auth_method": "jwt",
}
_REVOKED_DETAIL = "password was changed"
_PASSWORD_BODY = {"current_password": "Old-pass-1", "new_password": "New-pass-2"}  # pragma: allowlist secret


def _request() -> Request:
    scope = {"type": "http", "method": "GET", "path": "/probe", "query_string": b"", "headers": []}
    scope.update({"client": ("testclient", 50000), "app": FastAPI()})
    return Request(scope)


def _epoch_says(monkeypatch, revoked: bool) -> None:
    import auth_revocation  # noqa: PLC0415

    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=revoked))


@pytest.fixture
def gate(monkeypatch):
    """The real ``resolve_human_user`` / ``check_file_permissions`` over a stand-in identity."""
    real = load_real_auth_middleware()
    fake_self = SimpleNamespace(
        get_user_from_request=lambda _request: dict(_JWT_USER),  # the instance resolves, not the singleton (#19061)
        security_layer=SimpleNamespace(check_permission=lambda **_kw: True),
        _log_file_access_granted=MagicMock(),
        _log_file_access_denied=MagicMock(),
    )
    middleware = SimpleNamespace(
        get_user_from_request=lambda _request: dict(_JWT_USER),
        check_file_permissions=lambda request, operation: real.AuthenticationMiddleware.check_file_permissions(
            fake_self, request, operation
        ),
        invalidate_session=MagicMock(),
        enable_auth=True,
        security_config={"allowed_users": {}},
        security_layer=MagicMock(),
    )
    monkeypatch.setattr(real, "get_auth_middleware", lambda: middleware)
    monkeypatch.setattr(real, "verify_internal_api_key", lambda _provided: False)
    return SimpleNamespace(real=real, middleware=middleware)


@pytest.fixture
def auth_client(monkeypatch, gate):
    api_auth = importlib.import_module("api.auth")
    monkeypatch.setattr(api_auth, "resolve_human_user", gate.real.resolve_human_user)
    monkeypatch.setattr(api_auth, "get_auth_middleware", lambda: gate.middleware)
    app = FastAPI()
    app.include_router(api_auth.router, prefix="/api/auth")
    app.dependency_overrides[api_auth.check_admin_permission] = gate.real.check_admin_permission
    client = TestClient(app, raise_server_exceptions=False)
    client.api_auth = api_auth
    return client


# -- /auth/check ---------------------------------------------------------------------------------


def test_auth_check_refuses_a_revoked_jwt(monkeypatch, auth_client):
    _epoch_says(monkeypatch, revoked=True)
    response = auth_client.get("/api/auth/check")
    assert response.status_code == 401
    assert _REVOKED_DETAIL in response.json()["detail"]


def test_auth_check_accepts_a_fresh_jwt(monkeypatch, auth_client):
    _epoch_says(monkeypatch, revoked=False)
    response = auth_client.get("/api/auth/check")
    assert response.status_code == 200


# -- /auth/permissions/{operation} -----------------------------------------------------------------


def test_permission_check_refuses_a_revoked_jwt(monkeypatch, auth_client):
    _epoch_says(monkeypatch, revoked=True)
    assert auth_client.get("/api/auth/permissions/view").status_code == 401


def test_permission_check_accepts_a_fresh_jwt(monkeypatch, auth_client):
    _epoch_says(monkeypatch, revoked=False)
    response = auth_client.get("/api/auth/permissions/view")
    assert response.status_code == 200
    assert response.json()["permitted"] is True


# -- /auth/change-password -------------------------------------------------------------------------


@pytest.mark.parametrize(("revoked", "expected"), [(True, 401), (False, 429)])
def test_change_password_gate_refuses_only_a_revoked_jwt(monkeypatch, auth_client, revoked, expected):
    """A fresh JWT gets past the identity gate and meets the (stood-in) rate limit, a 429."""
    _epoch_says(monkeypatch, revoked=revoked)
    limited = AsyncMock(side_effect=HTTPException(status_code=429, detail="limited"))
    monkeypatch.setattr(auth_client.api_auth, "_check_password_change_rate_limit", limited)
    response = auth_client.post("/api/auth/change-password", json=_PASSWORD_BODY)
    assert response.status_code == expected


# -- /auth/refresh ---------------------------------------------------------------------------------


@pytest.mark.parametrize(("revoked", "expected"), [(True, 401), (False, 200)])
def test_refresh_does_not_mint_from_a_revoked_token(monkeypatch, auth_client, revoked, expected):
    _epoch_says(monkeypatch, revoked=revoked)
    claims = {"username": "alice", "role": "admin", "iat": 1}
    monkeypatch.setattr(auth_client.api_auth, "_decode_refresh_token", lambda _token: dict(claims))
    auth_client.api_auth.get_auth_middleware().create_jwt_token = MagicMock(return_value="new")
    auth_client.api_auth.get_auth_middleware().jwt_expiry_hours = 1
    response = auth_client.post("/api/auth/refresh", headers={"Authorization": "Bearer old"})
    assert response.status_code == expected


@pytest.mark.parametrize(("iat", "expected"), [(999, 401), (1001, 200)], ids=["before-change", "after-change"])
def test_refresh_judges_a_real_login_token_shape_by_its_username(monkeypatch, auth_client, iat, expected):
    """Login tokens carry ``username`` and no ``sub``: the REAL epoch helper still revokes them (#19061)."""
    from autobot_shared.user_management import password_epoch  # noqa: PLC0415

    monkeypatch.setattr(password_epoch, "get_password_epoch", AsyncMock(return_value=1000))
    claims = {"username": "alice", "role": "admin", "iat": iat, "token_type": "login"}
    monkeypatch.setattr(auth_client.api_auth, "_decode_refresh_token", lambda _token: dict(claims))
    middleware = auth_client.api_auth.get_auth_middleware()
    middleware.create_jwt_token = MagicMock(return_value="new")
    middleware.jwt_expiry_hours = 1
    response = auth_client.post("/api/auth/refresh", headers={"Authorization": "Bearer old"})
    assert response.status_code == expected


@pytest.mark.parametrize(("session", "expected"), [(None, 401), ({"user_data": {}}, 200)], ids=["logged-out", "active"])
def test_refresh_does_not_mint_from_a_logged_out_session(monkeypatch, auth_client, session, expected):
    """A token whose session was invalidated (logout) is not refreshable inside its window."""
    _epoch_says(monkeypatch, revoked=False)
    claims = {"username": "alice", "role": "admin", "iat": 1, "session_id": "s-1"}
    monkeypatch.setattr(auth_client.api_auth, "_decode_refresh_token", lambda _token: dict(claims))
    middleware = auth_client.api_auth.get_auth_middleware()
    middleware.get_session = lambda _sid: session
    middleware.create_jwt_token = MagicMock(return_value="new")
    middleware.jwt_expiry_hours = 1
    response = auth_client.post("/api/auth/refresh", headers={"Authorization": "Bearer old"})
    assert response.status_code == expected


# -- /auth/logout: idempotent, never fails, never names a void credential ----------------------------


@pytest.mark.parametrize(
    ("revoked", "named"), [(True, "unknown"), (False, _JWT_USER["user_id"])], ids=["revoked", "fresh"]
)
def test_logout_succeeds_for_a_revoked_jwt_and_does_not_name_it(monkeypatch, auth_client, revoked, named):
    _epoch_says(monkeypatch, revoked=revoked)
    emitted = MagicMock()
    monkeypatch.setattr(auth_client.api_auth, "_emit_event", emitted)
    response = auth_client.post("/api/auth/logout", json={"session_id": "s-1"})
    assert response.status_code == 200
    emitted.assert_called_once()
    assert emitted.call_args.args[1] == named
    # The session is invalidated either way: logging out with a stale token still ends the session.
    auth_client.api_auth.get_auth_middleware().invalidate_session.assert_called_once_with("s-1")


# -- /auth/validate: the caller, and the token being inspected --------------------------------------


def test_validate_refuses_a_revoked_caller(monkeypatch, auth_client):
    _epoch_says(monkeypatch, revoked=True)
    response = auth_client.post("/api/auth/validate", json={"token": "some.token.value"})
    assert response.status_code == 401


@pytest.mark.parametrize(("revoked", "valid"), [(True, False), (False, True)])
def test_validate_reports_a_password_change_revoked_token_as_revoked(monkeypatch, auth_client, revoked, valid):
    """Caller is a fresh admin; the INSPECTED token's verdict comes from the epoch."""
    import auth_revocation  # noqa: PLC0415

    inspected = {"username": "bob", "role": "user", "iat": 1, "exp": 9999999999}
    monkeypatch.setattr(
        auth_client.api_auth.get_auth_middleware(), "verify_jwt_token", lambda _t: inspected, raising=False
    )
    monkeypatch.setattr(auth_client.api_auth.get_auth_middleware(), "get_session", lambda _s: {}, raising=False)
    calls = []

    async def epoch(claims):
        subject = claims.get("sub") or claims["username"]  # login tokens carry no ``sub`` (#19061)
        calls.append(subject)
        return subject == "bob" and revoked

    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", epoch)
    response = auth_client.post("/api/auth/validate", json={"token": "some.token.value"})
    assert response.status_code == 200
    assert response.json()["revoked"] is revoked
    assert response.json()["valid"] is valid
    assert "bob" in calls


def test_validate_with_an_unanswerable_epoch_store_is_a_503(monkeypatch, auth_client):
    import auth_revocation  # noqa: PLC0415
    from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable  # noqa: PLC0415

    middleware = auth_client.api_auth.get_auth_middleware()
    monkeypatch.setattr(
        middleware, "verify_jwt_token", lambda _t: {"sub": "bob", "iat": 1, "exp": 9999999999}, raising=False
    )
    monkeypatch.setattr(middleware, "get_session", lambda _s: {}, raising=False)

    async def epoch(claims):
        if claims["sub"] == "bob":  # only the inspected token's lookup fails; the caller (alice) is cleared
            raise RevocationCheckUnavailable("epoch store unreachable")
        return False

    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", epoch)
    response = auth_client.post("/api/auth/validate", json={"token": "some.token.value"})
    assert response.status_code == 503


# -- check_file_permissions and its callers ---------------------------------------------------------


def _files_caller(name: str):
    module = importlib.import_module(name)
    if name == "api.conversation_files":
        return module, lambda request: module._authorize_file_operation(request, "session-1", "view")
    if name == "api.sandbox_files":
        return module, lambda request: module._check_permission(request, "view")
    return module, lambda request: module._check_file_permission(request, "view")


@pytest.fixture(params=["api.files", "api.sandbox_files", "api.conversation_files"])
def file_gate(request, monkeypatch, gate):
    module, call = _files_caller(request.param)
    monkeypatch.setattr(module, "get_auth_middleware", lambda: gate.middleware, raising=False)
    monkeypatch.setattr(importlib.import_module("api.files"), "get_auth_middleware", lambda: gate.middleware)
    if request.param == "api.conversation_files":
        monkeypatch.setattr(module, "validate_session_ownership", AsyncMock(return_value=None))
    return call


def test_a_file_route_refuses_a_revoked_jwt(monkeypatch, file_gate):
    _epoch_says(monkeypatch, revoked=True)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(file_gate(_request()))
    assert exc.value.status_code == 401
    assert _REVOKED_DETAIL in exc.value.detail


def test_a_file_route_accepts_a_fresh_jwt(monkeypatch, file_gate):
    _epoch_says(monkeypatch, revoked=False)
    user = asyncio.run(file_gate(_request()))
    assert user["username"] == "alice"


def test_check_file_permissions_fails_closed_when_the_epoch_store_is_down(monkeypatch, gate):
    """503 with Retry-After (auth_revocation.py), not a 403 'denied' and not a silent pass."""
    import auth_revocation  # noqa: PLC0415
    from autobot_shared.user_management.password_epoch import RevocationCheckUnavailable  # noqa: PLC0415

    down = AsyncMock(side_effect=RevocationCheckUnavailable("epoch store unreachable"))
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", down)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(gate.middleware.check_file_permissions(_request(), "view"))
    assert exc.value.status_code == 503
    assert "Retry-After" in exc.value.headers


def test_check_file_permissions_resolves_through_its_own_instance_not_the_singleton(monkeypatch, gate):
    """An instance with its own (ephemeral) signing key must verify the tokens it signed (#19061).

    The singleton here knows no one; the instance (``fake_self``) knows alice. Resolving through the
    singleton would answer (False, None).
    """
    _epoch_says(monkeypatch, revoked=False)
    gate.middleware.get_user_from_request = lambda _request: None
    granted, user = asyncio.run(gate.middleware.check_file_permissions(_request(), "view"))
    assert granted is True
    assert user["username"] == "alice"
