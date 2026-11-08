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
from sqlalchemy.exc import IntegrityError

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
        patch.object(routes, "lock_company_members", AsyncMock()),
        patch.object(routes, "require_company_admin_unless_platform", AsyncMock()),
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


def _member_routes():
    """Each write route, ready to call with (session, svc, ctx)."""
    add = routes.MemberAddRequest(user_id=_TARGET, role=Role.MEMBER)
    change = routes.MemberRoleRequest(role=Role.MEMBER)
    return {
        "add": lambda session, svc, ctx: routes.add_member(_COMPANY, add, session, svc, {}, ctx),
        "change": lambda session, svc, ctx: routes.change_member_role(_COMPANY, _TARGET, change, session, svc, {}, ctx),
        "remove": lambda session, svc, ctx: routes.remove_member(_COMPANY, _TARGET, session, svc, {}, ctx),
    }


def _member_service() -> MagicMock:
    member = MagicMock(role=Role.MEMBER, id=uuid.uuid4(), company_id=_COMPANY, user_id=_TARGET, created_at=None)
    return MagicMock(
        get_member=AsyncMock(return_value=member),
        add_member=AsyncMock(return_value=member),
        change_role=AsyncMock(return_value=member),
        remove_member=AsyncMock(),
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["add", "change", "remove"])
async def test_the_lock_is_taken_before_any_role_is_read_or_judged(name):
    order: list = []
    svc = _member_service()
    member = svc.get_member.return_value

    async def read(*_args):
        order.append("read")
        return member

    svc.get_member = read

    def step(label):
        async def record(*_args, **_kwargs):
            order.append(label)

        return record

    with (
        patch.object(routes, "lock_company_members", step("lock")),
        patch.object(routes, "require_company_admin_unless_platform", step("gate")),
        patch.object(routes, "authorize_member_change", step("authorize")),
    ):
        await _member_routes()[name](AsyncMock(), svc, _ctx())
    assert order[0] == "lock"
    assert "authorize" in order


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["add", "change", "remove"])
async def test_a_plain_member_gets_403_on_every_write_route(name):
    session = AsyncMock()
    with (
        patch.object(routes, "lock_company_members", AsyncMock()),
        patch(f"{_POLICY}.require_company_admin", AsyncMock(side_effect=NotAuthorisedError("ids"))),
        patch("llc.services.authz.require_company_admin", AsyncMock(side_effect=NotAuthorisedError("ids"))),
        pytest.raises(HTTPException) as raised,
    ):
        await _member_routes()[name](session, _member_service(), _ctx())
    assert raised.value.status_code == 403
    session.commit.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["change", "remove"])
async def test_a_plain_member_cannot_probe_who_belongs(name):
    """The 403 comes before the target is read, so a missing target is not a 404 they can tell apart."""
    svc = _member_service()
    svc.get_member.return_value = None
    with (
        patch.object(routes, "lock_company_members", AsyncMock()),
        patch("llc.services.authz.require_company_admin", AsyncMock(side_effect=NotAuthorisedError("ids"))),
        pytest.raises(HTTPException) as raised,
    ):
        await _member_routes()[name](AsyncMock(), svc, _ctx())
    assert raised.value.status_code == 403
    svc.get_member.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["add", "change", "remove"])
async def test_another_companys_caller_gets_404_on_every_write_route(name):
    ctx = MagicMock(org_id=uuid.uuid4(), user_id=_ACTOR, is_platform_admin=False)
    session = AsyncMock()
    with pytest.raises(HTTPException) as raised:
        await _member_routes()[name](session, _member_service(), ctx)
    assert raised.value.status_code == 404
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_superadmins_add_to_a_missing_company_is_404_not_500():
    svc = _member_service()
    svc.add_member.side_effect = IntegrityError("insert", {}, Exception("fk"))
    session = AsyncMock()
    with (
        patch.object(routes, "lock_company_members", AsyncMock()),
        pytest.raises(HTTPException) as raised,
    ):
        await _member_routes()["add"](session, svc, _ctx(admin=True))
    assert raised.value.status_code == 404
    session.rollback.assert_awaited_once()
