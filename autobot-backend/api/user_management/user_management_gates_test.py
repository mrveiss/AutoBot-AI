# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests that the gates added by #16276 (teams) and #15738 (users) refuse the callers they should.

Every request goes through FastAPI with only ``get_current_user``,
``get_db_session`` and, for the admitted cases, the service replaced. The
gates themselves run for real. Each refusal is pinned to the platform-admin
detail string, not just the bare status: ``dependencies_test.py`` notes that
403 is also what a missing org membership returns, so a bare 403 would prove
little.
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
    get_team_service,
    get_user_service,
)
from api.user_management.router import router as user_management_router

_CALLER = uuid.uuid4()
_OTHER = uuid.uuid4()
_TEAM = uuid.uuid4()
_ROLE = uuid.uuid4()
_ORG = uuid.uuid4()

#: A logged-in org member with no admin claim, and a platform admin.
_MEMBER = {"role": "user", "user_id": str(_CALLER), "org_id": str(_ORG)}
_ADMIN = {"role": "admin", "is_platform_admin": True, "user_id": str(_CALLER)}

#: Every route #16276 and #15738 made admin-only.
_ADMIN_ONLY = [
    ("GET", "/user-management/teams"),
    ("POST", "/user-management/teams"),
    ("GET", f"/user-management/teams/{_TEAM}"),
    ("PATCH", f"/user-management/teams/{_TEAM}"),
    ("DELETE", f"/user-management/teams/{_TEAM}"),
    ("GET", f"/user-management/teams/{_TEAM}/members"),
    ("POST", f"/user-management/teams/{_TEAM}/members/{_OTHER}"),
    ("DELETE", f"/user-management/teams/{_TEAM}/members/{_OTHER}"),
    ("PATCH", f"/user-management/teams/{_TEAM}/members/{_OTHER}"),
    ("POST", "/user-management/users"),
    ("DELETE", f"/user-management/users/{_OTHER}"),
    ("POST", f"/user-management/users/{_OTHER}/roles/{_ROLE}"),
    ("DELETE", f"/user-management/users/{_OTHER}/roles/{_ROLE}"),
]

#: The #15738 routes that act for the account owner or an admin.
_SELF_OR_ADMIN = [
    ("GET", "/user-management/users/{user_id}"),
    ("PATCH", "/user-management/users/{user_id}"),
]


async def _no_session():
    """Stands in for the session. These requests carry no org header or ``company_id``, so nothing queries it."""
    yield object()


def _client(current_user: dict, *, user_service=None, team_service=None) -> TestClient:
    app = FastAPI()
    app.include_router(user_management_router)
    app.dependency_overrides[get_current_user] = lambda: current_user
    app.dependency_overrides[get_db_session] = _no_session
    if user_service is not None:
        app.dependency_overrides[get_user_service] = lambda: user_service
    if team_service is not None:
        app.dependency_overrides[get_team_service] = lambda: team_service
    return TestClient(app, raise_server_exceptions=False)


@pytest.mark.parametrize(("method", "path"), _ADMIN_ONLY)
def test_a_member_is_refused_an_admin_only_route(method, path):
    response = _client(_MEMBER).request(method, path, json={})
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == _PLATFORM_ADMIN_DENIED


@pytest.mark.parametrize(("method", "template"), _SELF_OR_ADMIN)
def test_a_member_is_refused_another_users_account(method, template):
    response = _client(_MEMBER).request(method, template.format(user_id=_OTHER), json={})
    assert response.status_code == 403, response.text
    assert response.json()["detail"] == _PLATFORM_ADMIN_DENIED


def test_a_member_reaches_their_own_account():
    """The contrast case: the gate admits the owner, and the request reaches the handler."""
    service = MagicMock()
    service.get_user = AsyncMock(return_value=None)
    response = _client(_MEMBER, user_service=service).get(f"/user-management/users/{_CALLER}")
    assert response.status_code == 404, response.text  # past the gate: the handler's own not-found
    service.get_user.assert_awaited_once_with(_CALLER)


def test_an_admin_reaches_an_admin_only_route():
    """The contrast case for the admin-only gate."""
    service = MagicMock()
    service.delete_team = AsyncMock(return_value=True)
    response = _client(_ADMIN, team_service=service).delete(f"/user-management/teams/{_TEAM}")
    assert response.status_code == 200, response.text
    service.delete_team.assert_awaited_once()


def test_my_teams_stays_open_to_a_logged_in_member():
    """``/my-teams`` returns only the caller's own teams, so it is not admin-gated (#16276), and it is reachable (#16277)."""
    service = MagicMock()
    service.get_user_teams = AsyncMock(return_value=[])
    response = _client(_MEMBER, team_service=service).get("/user-management/teams/my-teams")
    assert response.status_code == 200, response.text
    assert response.json() == []
    service.get_user_teams.assert_awaited_once_with(_CALLER)
