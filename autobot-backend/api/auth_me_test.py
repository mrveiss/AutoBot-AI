# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``GET /api/auth/me`` reports the caller's effective permissions and admin status (#16270 AC5)."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api import auth_me
from autobot_shared.auth.permissions import ROLE_PERMISSIONS, Permission, Role


def _me(user_data):
    """Call /me as a caller whose auth middleware resolves to *user_data*."""
    app = FastAPI()
    app.include_router(auth_me.router, prefix="/api/auth")
    middleware = MagicMock()
    middleware.get_user_from_request.return_value = user_data
    config = SimpleNamespace(mode=SimpleNamespace(value="single_company"))
    with (
        patch.object(auth_me, "get_auth_middleware", return_value=middleware),
        patch("user_management.config.get_deployment_config", return_value=config),
    ):
        return TestClient(app, raise_server_exceptions=False).get("/api/auth/me")


def test_a_superadmin_gets_no_granular_permissions_and_is_admin():
    """The AC5 case. A frontend gating on ``permissions`` alone would hide everything from this caller."""
    body = _me({"username": "root", "role": "superadmin"}).json()
    assert body["permissions"] == []
    assert body["is_admin"] is True


def test_an_admin_gets_every_permission():
    body = _me({"username": "a", "role": "admin"}).json()
    assert body["permissions"] == sorted(p.value for p in Permission)
    assert body["is_admin"] is True


@pytest.mark.parametrize("role", [Role.USER, Role.READONLY, Role.OPERATOR], ids=lambda r: r.value)
def test_a_non_admin_gets_exactly_its_role_permissions(role):
    body = _me({"username": "u", "role": role.value}).json()
    assert body["permissions"] == sorted(p.value for p in ROLE_PERMISSIONS[role])
    assert body["is_admin"] is False


def test_an_unknown_role_gets_nothing():
    """It fails closed, the way ``role_has_permission`` does."""
    body = _me({"username": "x", "role": "not-a-role"}).json()
    assert body["permissions"] == []
    assert body["is_admin"] is False


def test_the_identity_fields_are_unchanged():
    body = _me({"username": "u", "role": "user", "email": "u@example.test", "auth_method": "jwt"}).json()
    assert body["username"] == "u"
    assert body["role"] == "user"
    assert body["email"] == "u@example.test"
    assert body["auth_method"] == "jwt"
    assert body["authenticated"] is True
    assert body["deployment_mode"] == "single_company"


def test_no_session_is_a_401():
    assert _me(None).status_code == 401
