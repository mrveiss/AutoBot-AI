# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company-scoped team writes: owner/admin only, scoped by the path's company, audited (#14106).

The real ``TeamService`` runs; only the lookups that need a database are patched, so the
audit rows it adds to the session and the organisation it filters on are the real ones.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from api.schemas_agent import TeamCreate
from autobot_shared.user_management.models.audit import AuditLog
from autobot_shared.user_management.models.team import Team
from llc.api import company_teams as routes
from user_management.services import TeamService

_COMPANY = uuid.uuid4()
_OTHER = uuid.uuid4()
_ACTOR = uuid.uuid4()
_USER = uuid.uuid4()
_TEAM_ID = uuid.uuid4()
_SERVICE = "autobot_shared.user_management.team_service"


def _ctx(org=_COMPANY, admin=False) -> MagicMock:
    return MagicMock(org_id=org, user_id=_ACTOR, is_platform_admin=admin)


def _session(company_user: bool = True) -> AsyncMock:
    """A session whose only direct query is 'is this user in the company'."""
    session = AsyncMock()
    session.add = MagicMock()
    session.execute.return_value = MagicMock(first=MagicMock(return_value=(1,) if company_user else None))
    return session


def _team() -> Team:
    return Team(id=_TEAM_ID, org_id=_COMPANY, name="Platform", settings={}, is_default=False)


def _as(role):
    return patch("llc.services.authz.membership_role", AsyncMock(return_value=role))


def _audits(session) -> list[AuditLog]:
    return [c.args[0] for c in session.add.call_args_list if isinstance(c.args[0], AuditLog)]


async def _call(name: str, session, ctx):
    """Invoke one route the way FastAPI would, for the same ids."""
    if name == "create":
        return await routes.create_company_team(_COMPANY, TeamCreate(name="Platform"), session, {}, ctx)
    if name == "delete":
        return await routes.delete_company_team(_COMPANY, _TEAM_ID, session, {}, ctx)
    if name == "add":
        return await routes.add_company_team_member(_COMPANY, _TEAM_ID, _USER, "member", session, {}, ctx)
    return await routes.remove_company_team_member(_COMPANY, _TEAM_ID, _USER, session, {}, ctx)


def _real_service_lookups():
    """Patch the database lookups of the real TeamService; membership writes still audit."""
    return (
        patch.object(TeamService, "_find_team_by_name", AsyncMock(return_value=None)),
        patch.object(TeamService, "get_team", AsyncMock(return_value=_team())),
        patch.object(TeamService, "_get_membership", AsyncMock(return_value=None)),
        patch(f"{_SERVICE}.run_after_commit"),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["owner", "admin"])
@pytest.mark.parametrize(
    "route,action", [("create", "team.create"), ("delete", "team.delete"), ("add", "team.member_add")]
)
async def test_an_owner_or_admin_manages_the_teams_and_it_is_audited(role, route, action):
    session = _session()
    lookups = _real_service_lookups()
    with _as(role), lookups[0], lookups[1], lookups[2], lookups[3]:
        await _call(route, session, _ctx())
    session.commit.assert_awaited_once()
    rows = _audits(session)
    assert any(row.org_id == _COMPANY and row.user_id == _ACTOR and row.action == action for row in rows), [
        r.action for r in rows
    ]


@pytest.mark.asyncio
async def test_removing_a_member_is_audited():
    session = _session()
    lookups = _real_service_lookups()
    membership = MagicMock(role="member")
    with (
        _as("admin"),
        lookups[0],
        lookups[1],
        lookups[3],
        patch.object(TeamService, "_get_membership", AsyncMock(return_value=membership)),
    ):
        await _call("remove", session, _ctx())
    session.commit.assert_awaited_once()
    assert any(row.org_id == _COMPANY and row.action == "team.member_remove" for row in _audits(session))


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["member", "viewer", None])
@pytest.mark.parametrize("route", ["create", "delete", "add", "remove"])
async def test_a_plain_member_is_refused_and_nothing_is_written(role, route):
    session = _session()
    with _as(role), pytest.raises(HTTPException) as raised:
        await _call(route, session, _ctx())
    assert raised.value.status_code == 403
    session.commit.assert_not_awaited()
    assert not _audits(session)


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["create", "delete", "add", "remove"])
async def test_another_companys_caller_gets_404_even_as_its_owner(route):
    session = _session()
    with _as("owner"), pytest.raises(HTTPException) as raised:
        await _call(route, session, _ctx(org=_OTHER))
    assert raised.value.status_code == 404
    session.commit.assert_not_awaited()
    assert not _audits(session)


@pytest.mark.asyncio
async def test_scope_is_the_paths_company_not_the_ambient_one_for_a_platform_admin():
    session = _session()
    seen = []
    real = routes._team_service

    def spy(*args):
        service = real(*args)
        seen.append(service.context.org_id)
        return service

    lookups = _real_service_lookups()
    with patch.object(routes, "_team_service", spy), lookups[0], lookups[1], lookups[2], lookups[3]:
        await _call("create", session, _ctx(org=_OTHER, admin=True))
    assert seen == [_COMPANY]
    assert all(row.org_id == _COMPANY for row in _audits(session))


@pytest.mark.asyncio
async def test_another_companys_team_is_not_found_and_the_lookup_is_filtered_by_the_path_company():
    session = AsyncMock()
    session.execute.return_value = MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    with _as("admin"), pytest.raises(HTTPException) as raised:
        await _call("delete", session, _ctx())
    assert raised.value.status_code == 404
    session.rollback.assert_awaited_once()
    sql = session.execute.await_args.args[0].compile().params
    assert _COMPANY in sql.values() and _TEAM_ID in sql.values()


@pytest.mark.asyncio
async def test_a_user_outside_the_company_cannot_be_added_and_looks_like_an_unknown_user():
    session = _session(company_user=False)
    with (
        _as("admin"),
        patch.object(TeamService, "add_member", AsyncMock()) as add,
        pytest.raises(HTTPException) as raised,
    ):
        await _call("add", session, _ctx())
    assert raised.value.status_code == 404
    add.assert_not_awaited()
    session.commit.assert_not_awaited()


def test_the_routes_exist_and_the_router_is_mounted():
    paths = {(m, r.path) for r in routes.router.routes for m in r.methods}
    assert ("POST", "/companies/{company_id}/teams") in paths
    assert ("DELETE", "/companies/{company_id}/teams/{team_id}") in paths
    assert ("POST", "/companies/{company_id}/teams/{team_id}/members/{user_id}") in paths
    assert ("DELETE", "/companies/{company_id}/teams/{team_id}/members/{user_id}") in paths
    mount = Path(routes.__file__).with_name("__init__.py").read_text(encoding="utf-8")
    assert "router.include_router(company_teams_router)" in mount
