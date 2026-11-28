# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""User-management routes use the shared admin permission (#15738).

The real ``require_platform_admin`` chain runs; only the identity it reads and
the database session are replaced, as in ``user_management_gates_test.py``.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.user_management.dependencies import (
    _PLATFORM_ADMIN_DENIED,
    get_current_user,
    get_db_session,
    get_user_service,
)
from api.user_management.router import router as user_management_router
from autobot_shared.user_management.user_service_errors import UserNotFoundError

_CALLER = uuid.UUID("00000000-0000-0000-0000-000000000001")
_OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
_ORG = uuid.UUID("00000000-0000-0000-0000-000000000005")

_MEMBER = {"role": "user", "user_id": str(_CALLER), "org_id": str(_ORG)}
_ADMIN = {"role": "admin", "is_platform_admin": True, "user_id": str(_CALLER)}

_ROUTES = [
    ("GET", "/user-management/users"),
    ("POST", f"/user-management/users/{_OTHER}/activate"),
    ("POST", f"/user-management/users/{_OTHER}/deactivate"),
]


async def _no_session():
    yield object()


def _client(current_user: dict, service=None) -> TestClient:
    app = FastAPI()
    app.include_router(user_management_router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db_session] = _no_session
    if service is not None:
        app.dependency_overrides[get_user_service] = lambda: service
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("method", "path"), _ROUTES)
def test_user_management_routes_require_admin(method, path):
    response = _client(_MEMBER).request(method, path)
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == _PLATFORM_ADMIN_DENIED


@pytest.mark.parametrize(("method", "path"), _ROUTES)
def test_user_management_routes_admit_an_admin(method, path):
    service = MagicMock()
    service.list_users = AsyncMock(return_value=([], 0))
    # An unknown target stops the handler at its own 404, past the gate and before any commit.
    service.activate_user = AsyncMock(side_effect=UserNotFoundError("x"))
    service.deactivate_user = AsyncMock(side_effect=UserNotFoundError("x"))
    response = _client(_ADMIN, service).request(method, path)
    assert response.status_code in (200, 404), response.text
