# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A plain member cannot change roles, and nobody but a superadmin can orphan a company (#19654)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from llc.api import company_members as routes
from llc.models.activity import ActorType
from llc.models.enums import MembershipRole as Role
from llc.services.authz import NotAuthorisedError
from llc.services.membership_policy import LastOwnerError, authorize_member_change
from llc.services.membership_service import MembershipService

_POLICY = "llc.services.membership_policy"
_COMPANY = uuid.uuid4()
_ACTOR = uuid.uuid4()
_TARGET = uuid.uuid4()


async def _authorize(actor_role, current, new, *, owners=2, platform_admin=False):
    session = AsyncMock()
    session.execute.return_value = MagicMock(all=MagicMock(return_value=[object()] * owners))
    gate = AsyncMock(return_value=actor_role)
    if actor_role is None:
        gate.side_effect = NotAuthorisedError("no")
    with patch(f"{_POLICY}.require_company_admin", gate):
        await authorize_member_change(
            session, _COMPANY, _ACTOR, platform_admin=platform_admin, current_role=current, new_role=new
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("current,new", [(None, Role.MEMBER), (Role.MEMBER, Role.ADMIN), (Role.MEMBER, None)])
async def test_a_member_or_viewer_may_change_nothing(current, new):
    # require_company_admin is the gate that refuses both: neither role is in GRANTING_ROLES.
    with pytest.raises(NotAuthorisedError):
        await _authorize(None, current, new)


@pytest.mark.asyncio
@pytest.mark.parametrize("current,new", [(None, Role.OWNER), (Role.MEMBER, Role.OWNER), (Role.OWNER, None)])
async def test_an_admin_cannot_grant_or_revoke_owner(current, new):
    with pytest.raises(NotAuthorisedError):
        await _authorize("admin", current, new)
    with pytest.raises(NotAuthorisedError):
        await _authorize("admin", Role.OWNER, Role.MEMBER)


@pytest.mark.asyncio
async def test_an_admin_may_manage_the_other_roles():
    await _authorize("admin", Role.MEMBER, Role.ADMIN)
    await _authorize("admin", Role.ADMIN, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("new", [None, Role.ADMIN])
async def test_the_last_owner_cannot_be_removed_or_demoted(new):
    with pytest.raises(LastOwnerError):
        await _authorize("owner", Role.OWNER, new, owners=1)


@pytest.mark.asyncio
async def test_an_owner_may_step_down_while_another_owner_remains():
    await _authorize("owner", Role.OWNER, Role.ADMIN, owners=2)


@pytest.mark.asyncio
async def test_a_superadmin_needs_no_membership_and_can_assign_owner_anywhere():
    gate = AsyncMock(side_effect=NotAuthorisedError("not a member"))
    with patch(f"{_POLICY}.require_company_admin", gate):
        await authorize_member_change(
            AsyncMock(), _COMPANY, _ACTOR, platform_admin=True, current_role=None, new_role=Role.OWNER
        )
    gate.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_superadmin_can_remove_the_last_owner():
    await _authorize(None, Role.OWNER, None, owners=1, platform_admin=True)


def _ctx(admin=False) -> MagicMock:
    return MagicMock(org_id=_COMPANY, user_id=_ACTOR, is_platform_admin=admin)


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status_code", [(NotAuthorisedError("ids"), 403), (LastOwnerError("ids"), 409)])
async def test_the_role_route_answers_the_policys_refusal_and_rolls_back(error, status_code):
    session, svc = AsyncMock(), MagicMock(get_member=AsyncMock(return_value=MagicMock(role=Role.OWNER)))
    with (
        patch.object(routes, "authorize_member_change", AsyncMock(side_effect=error)),
        pytest.raises(HTTPException) as raised,
    ):
        await routes.change_member_role(
            _COMPANY, _TARGET, routes.MemberRoleRequest(role=Role.MEMBER), session, svc, {}, _ctx()
        )
    assert raised.value.status_code == status_code
    assert "ids" not in str(raised.value.detail)
    session.rollback.assert_awaited_once()
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_log_names_the_acting_user_not_the_target_and_records_before_and_after():
    log = MagicMock(record=AsyncMock())
    svc = MembershipService(activity_log=log)
    member = MagicMock(id=uuid.uuid4(), role=Role.MEMBER)
    with patch.object(svc, "get_member", AsyncMock(return_value=member)):
        await svc.change_role(AsyncMock(), str(_COMPANY), str(_TARGET), Role.ADMIN, actor_id=str(_ACTOR))
    kwargs = log.record.await_args.kwargs
    assert kwargs["actor_id"] == str(_ACTOR)
    assert kwargs["actor_type"] is ActorType.USER
    assert kwargs["before"]["role"] == "member"
    assert kwargs["after"]["role"] == "admin"


def test_the_role_route_exists_and_its_router_is_mounted():
    paths = {path for route in routes.router.routes if "PATCH" in route.methods for path in [route.path]}
    assert "/companies/{company_id}/members/{user_id}" in paths
    mount = Path(routes.__file__).with_name("__init__.py").read_text(encoding="utf-8")
    assert "router.include_router(company_members_router)" in mount
