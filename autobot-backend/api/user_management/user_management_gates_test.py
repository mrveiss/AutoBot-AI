# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests that the gates added by #16276 (teams), #15738 (users) and #16279 (search) refuse the callers they should.

Every request goes through FastAPI with only ``get_current_user``,
``get_db_session`` and, for the admitted cases, the service replaced. The
gates themselves run for real. Each refusal is pinned to the platform-admin
detail string, not just the bare status: ``dependencies_test.py`` notes that
403 is also what a missing org membership returns, so a bare 403 would prove
little.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from api.user_management.dependencies import (
    _PLATFORM_ADMIN_DENIED,
    get_current_user,
    get_db_session,
    get_team_service,
    get_user_service,
)
from api.user_management.router import router as user_management_router
from user_management.services import TenantContext, UserService

# Fixed, not uuid4(): these appear in the parametrize ids below, and each
# xdist worker imports this module on its own. Random values gave every
# worker a different test list, failing collection on #16240 (shard 3).
_CALLER = uuid.UUID("00000000-0000-0000-0000-000000000001")
_OTHER = uuid.UUID("00000000-0000-0000-0000-000000000002")
_TEAM = uuid.UUID("00000000-0000-0000-0000-000000000003")
_ROLE = uuid.UUID("00000000-0000-0000-0000-000000000004")
_ORG = uuid.UUID("00000000-0000-0000-0000-000000000005")

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

#: #16279: the sharing search, now login plus the caller's own org.
_SEARCH = "/user-management/users/search?q=a"


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


def _refuse_login():
    raise HTTPException(status_code=401, detail="Authentication required")


def test_the_search_refuses_an_anonymous_caller():
    """#16279: the search used to answer anonymous callers with names from every organisation."""
    app = FastAPI()
    app.include_router(user_management_router)
    app.dependency_overrides[get_current_user] = _refuse_login
    app.dependency_overrides[get_db_session] = _no_session
    response = TestClient(app, raise_server_exceptions=False).get(_SEARCH)
    assert response.status_code == 401, response.text


def test_the_search_refuses_a_caller_with_no_organisation():
    """Without an org there is no organisation to confine the search to, so ``require_org_context`` refuses."""
    response = _client({"role": "user", "user_id": str(_CALLER)}).get(_SEARCH)
    assert response.status_code == 400, response.text


def test_the_search_runs_in_the_callers_own_organisation():
    """The search's service carries the caller's org, not the org-less admin context it used to build."""
    seen: list[TenantContext] = []

    async def _capture(self, **_kwargs):
        seen.append(self.context)
        return [], 0

    with patch.object(UserService, "list_users", _capture):
        response = _client(_MEMBER).get(_SEARCH)
    assert response.status_code == 200, response.text
    assert response.json()["available"] is True
    assert len(seen) == 1, f"list_users ran {len(seen)} times"
    assert seen[0].org_id == _ORG
    assert seen[0].is_platform_admin is False


def test_the_user_query_is_confined_to_the_callers_organisation():
    """The query-level half of #16279: the WHERE clause binds the caller's org, so another org's users cannot match."""
    service = UserService(MagicMock(), TenantContext(org_id=_ORG, user_id=_CALLER))
    query = service._build_user_list_base_query(include_inactive=False, search="a")
    assert _ORG in query.compile().params.values(), "the user query does not filter on the caller's org"
