# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""GET /users/me returns the caller's stored profile (#18786).

Goes through the real route, so ``response_model`` validation runs. Only the
storage lookup and the authenticated principal are stood in.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api.user_management.dependencies as user_deps
from api.user_management.users import router
from testkit.canonical_gate import unauthenticated_canonical_gate

_CREATED = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
_UPDATED = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)


def _stored_user(user_id: uuid.UUID) -> SimpleNamespace:
    role = SimpleNamespace(id=uuid.uuid4(), name="editor", description="d", is_system=False)
    return SimpleNamespace(
        id=user_id,
        email="alice@example.test",
        username="alice",
        display_name="Alice A",
        bio=None,
        avatar_url=None,
        org_id=None,
        is_active=True,
        is_verified=True,
        mfa_enabled=True,
        is_platform_admin=False,
        preferences={"k": "v"},
        roles=[SimpleNamespace(role=role)],
        last_login_at=None,
        created_at=_CREATED,
        updated_at=_UPDATED,
    )


def _client(claims: dict | None, stored: SimpleNamespace | None) -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/user-management")
    service = SimpleNamespace(get_user=AsyncMock(return_value=stored))
    app.dependency_overrides[user_deps.get_user_service] = lambda: service
    if claims is not None:
        app.dependency_overrides[user_deps.get_current_user] = lambda: claims
    return TestClient(app, raise_server_exceptions=False)


def test_me_returns_the_stored_profile_with_id_roles_and_timestamps():
    uid = uuid.uuid4()
    client = _client({"username": "alice", "user_id": str(uid), "role": "user"}, _stored_user(uid))
    resp = client.get("/api/user-management/users/me")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(uid)
    assert body["roles"][0]["name"] == "editor"
    assert body["created_at"].startswith("2026-01-02T03:04:05")
    assert body["updated_at"].startswith("2026-02-03T04:05:06")


def test_two_calls_return_the_same_id():
    uid = uuid.uuid4()
    client = _client({"username": "alice", "user_id": str(uid), "role": "user"}, _stored_user(uid))
    first = client.get("/api/user-management/users/me").json()["id"]
    second = client.get("/api/user-management/users/me").json()["id"]
    assert first == second == str(uid)


@pytest.mark.parametrize(
    ("claims", "expected"),
    [
        ({"username": "root", "role": "admin", "user_id": str(uuid.uuid4())}, True),
        ({"username": "bob", "role": "user", "user_id": str(uuid.uuid4())}, False),
    ],
)
def test_is_platform_admin_comes_from_the_shared_claim_predicate(claims, expected):
    client = _client(claims, _stored_user(uuid.UUID(claims["user_id"])))
    assert client.get("/api/user-management/users/me").json()["is_platform_admin"] is expected


@pytest.mark.parametrize(
    "claims", [{"username": "envadmin", "role": "admin"}, {"username": "ghost", "user_id": str(uuid.uuid4())}]
)
def test_a_principal_with_no_stored_row_gets_404_not_an_invented_profile(claims):
    resp = _client(claims, None).get("/api/user-management/users/me")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "No stored profile for the current user"


def test_anonymous_is_401():
    with unauthenticated_canonical_gate():
        resp = _client(None, None).get("/api/user-management/users/me")
    assert resp.status_code == 401


def test_a_valid_jwt_through_the_real_gate_returns_the_stored_profile(monkeypatch):
    """Auth is NOT overridden: a real signed JWT passes the canonical gate to the stored row."""
    import auth_revocation  # noqa: PLC0415
    from autobot_shared.auth.interactive_principal import LOGIN_TOKEN_TYPE  # noqa: PLC0415
    from autobot_shared.auth.jwt_core import encode_jwt  # noqa: PLC0415
    from testkit.canonical_gate import install_canonical_gate  # noqa: PLC0415
    from tests.conftest import load_real_auth_middleware  # noqa: PLC0415

    secret = "s" * 40
    real = load_real_auth_middleware()
    middleware = real.AuthenticationMiddleware.__new__(real.AuthenticationMiddleware)
    middleware.jwt_secret = secret
    middleware.jwt_public_key = None
    middleware.failed_attempts = {}
    middleware.enable_auth = True
    middleware.get_session = {}.get
    install_canonical_gate(monkeypatch, middleware)
    monkeypatch.setattr(auth_revocation, "is_token_revoked_by_password_change", AsyncMock(return_value=False))

    uid = uuid.uuid4()
    claims = {"username": "alice", "role": "user", "user_id": str(uid), "token_type": LOGIN_TOKEN_TYPE}
    token = encode_jwt(claims, secret=secret, expiry_hours=1)
    # _client(None, ...) overrides only get_user_service, never get_current_user.
    client = _client(None, _stored_user(uid))

    resp = client.get("/api/user-management/users/me", headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == str(uid)
    assert body["created_at"].startswith("2026-01-02T03:04:05")
    assert body["updated_at"].startswith("2026-02-03T04:05:06")
