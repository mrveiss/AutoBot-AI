# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who may move a company, and how a move is asked for (#19634, #19589, #19593).

The maintainer's rulings (2026-10-26) for any ``parent_org_id`` change, enforced in
``CompanyService.move`` so every caller inherits it:

1. a platform admin always passes every check;
2. an org WITH a parent is moved out of it (promotion or sideways) by an owner/admin
   of that parent, with no role needed in the sub-org; the sub-org's own owner may not;
3. a top-level org joining a parent needs its own owner/admin;
4. joining a new parent needs owner/admin of that parent, else not found -- #12233's
   rule (``may_attach_under``), shared with ``create_company``.

#19589: an explicit ``"parent_org_id": null`` promotes, an absent field moves nothing.

SQLite harness (``test_llc_org_chart``), like ``test_ceo_heartbeat_15907``. The
two-session lock race needs Postgres row locks and lives in
``tests/migrations/test_company_move_cycle_lock_19593.py``; here the lock's *set*
and *order* are pinned.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import sqlalchemy as sa
from fastapi import FastAPI
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import DBAPIError

from api.user_management.dependencies import get_current_user, require_org_context
from llc.api import companies
from llc.models.company import CompanyCreate, CompanyUpdate
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.services.authz import NotAuthorisedError, may_attach_under
from llc.services.company import CompanyMoveForbiddenError, CompanyNotFoundError, CompanyService
from llc.services.company_ceo import CompanyCEOService
from llc.services.company_move_lock import MOVE_LOCK_MAX_PASSES, CompanyMoveContendedError
from llc.services.membership_service import MembershipService
from llc.tests import test_llc_org_chart as _org_chart_harness
from user_management.models.organization import Organization
from user_management.services import TenantContext

engine = _org_chart_harness.engine
session_factory = _org_chart_harness.session_factory

_ACTOR = uuid.uuid4()
_ORG_ID = uuid.uuid4()


async def _org(session_factory, name: str, *, parent=None, role=MembershipRole.OWNER) -> uuid.UUID:  # noqa: ANN001
    """Create an org; ``_ACTOR`` holds *role* in it (``None`` = no membership at all)."""
    async with session_factory() as session:
        org = await CompanyService(session).create(CompanyCreate(name=name, slug=name.lower(), parent_org_id=parent))
        if role is not None:
            await MembershipService().add_member(session, str(org.id), str(_ACTOR), role)
        await session.commit()
        return org.id


async def _update(  # noqa: ANN001
    session_factory, org_id: uuid.UUID, data: CompanyUpdate, platform_admin: bool = False
) -> None:
    async with session_factory() as session:
        await CompanyService(session).update(org_id, data, actor_user_id=_ACTOR, platform_admin=platform_admin)
        await session.commit()


async def _parent_of(session_factory, org_id: uuid.UUID) -> uuid.UUID | None:  # noqa: ANN001
    async with session_factory() as session:
        return (await session.get(Organization, org_id)).parent_org_id


# ---------------------------------------------------------------------------
# #19634 -- authorization, enforced in the service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_top_level_orgs_non_admin_cannot_attach_it(session_factory):  # noqa: ANN001
    """A top-level org decides itself to join a parent: its owner/admin, not a plain member."""
    parent = await _org(session_factory, "Parent")
    org = await _org(session_factory, "Acme", role=MembershipRole.MEMBER)
    with pytest.raises(NotAuthorisedError):
        await _update(session_factory, org, CompanyUpdate(parent_org_id=parent))
    assert await _parent_of(session_factory, org) is None


@pytest.mark.asyncio
async def test_an_unseen_new_parent_is_not_found_so_no_cross_tenant_graft(session_factory):  # noqa: ANN001
    foreign = await _org(session_factory, "Foreign", role=None)
    org = await _org(session_factory, "Acme")
    with pytest.raises(CompanyNotFoundError):
        await _update(session_factory, org, CompanyUpdate(parent_org_id=foreign))
    assert await _parent_of(session_factory, org) is None


@pytest.mark.asyncio
async def test_a_plain_member_of_the_new_parent_may_not_attach_under_it(session_factory):  # noqa: ANN001
    """A child inherits the parent's KB and ancestor visibility, so membership is not enough (2026-10-26)."""
    parent = await _org(session_factory, "Parent", role=MembershipRole.MEMBER)
    org = await _org(session_factory, "Acme")
    with pytest.raises(CompanyNotFoundError):
        await _update(session_factory, org, CompanyUpdate(parent_org_id=parent))
    assert await _parent_of(session_factory, org) is None


@pytest.mark.asyncio
async def test_an_admin_of_the_new_parent_may_attach_under_it(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.ADMIN)
    org = await _org(session_factory, "Acme")
    await _update(session_factory, org, CompanyUpdate(parent_org_id=parent))
    assert await _parent_of(session_factory, org) == parent


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("role", "platform_admin", "allowed"),
    [
        (MembershipRole.OWNER, False, True),
        (MembershipRole.ADMIN, False, True),
        (MembershipRole.MEMBER, False, False),
        (None, False, False),
        (None, True, True),
    ],
)
async def test_may_attach_under_needs_owner_or_admin_unless_platform_admin(  # noqa: ANN001
    session_factory, role, platform_admin, allowed
):
    parent = await _org(session_factory, "Parent", role=role)
    async with session_factory() as session:
        assert await may_attach_under(session, parent, _ACTOR, platform_admin=platform_admin) is allowed


@pytest.mark.asyncio
async def test_a_platform_admin_moves_an_org_that_has_no_admin_at_all(session_factory):  # noqa: ANN001
    """No lockout (maintainer principle, 2026-10-26): an org whose admins are gone stays movable."""
    parent = await _org(session_factory, "Parent", role=None)
    org = await _org(session_factory, "Acme", role=MembershipRole.MEMBER)  # its only member, not an admin
    await _update(session_factory, org, CompanyUpdate(parent_org_id=parent), platform_admin=True)
    assert await _parent_of(session_factory, org) == parent


@pytest.mark.asyncio
async def test_a_platform_admin_promotes_a_sub_org_whose_parent_has_no_admin(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.MEMBER)  # no admin left on the parent
    org = await _org(session_factory, "Acme", parent=parent, role=None)
    await _update(session_factory, org, CompanyUpdate(parent_org_id=None), platform_admin=True)
    assert await _parent_of(session_factory, org) is None


@pytest.mark.asyncio
async def test_a_platform_admin_moves_a_sub_org_sideways_whose_parent_has_no_admin(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.MEMBER)  # no admin left on the parent
    other = await _org(session_factory, "Other", role=None)
    org = await _org(session_factory, "Acme", parent=parent, role=None)
    await _update(session_factory, org, CompanyUpdate(parent_org_id=other), platform_admin=True)
    assert await _parent_of(session_factory, org) == other


@pytest.mark.asyncio
async def test_the_under_lock_role_check_locks_the_membership_row():
    from llc.services.authz import require_company_admin

    session = MagicMock()
    session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value="owner")))
    assert await require_company_admin(session, uuid.uuid4(), _ACTOR, for_update=True) == "owner"
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "FROM llc_company_memberships" in sql
    assert sql.rstrip().endswith("FOR UPDATE")


@pytest.mark.asyncio
async def test_an_owner_who_is_not_an_admin_moves_and_promotes(session_factory):  # noqa: ANN001
    """The OWNER role counts as admin everywhere a move checks (GRANTING_ROLES)."""
    parent = await _org(session_factory, "Parent", role=MembershipRole.OWNER)
    org = await _org(session_factory, "Acme", role=MembershipRole.OWNER)
    await _update(session_factory, org, CompanyUpdate(parent_org_id=parent))
    assert await _parent_of(session_factory, org) == parent
    await _update(session_factory, org, CompanyUpdate(parent_org_id=None))
    assert await _parent_of(session_factory, org) is None


@pytest.mark.asyncio
async def test_a_role_revoked_while_the_move_waited_for_its_locks_stops_it(session_factory):  # noqa: ANN001
    """Proves the role is RE-READ under the lock (same SQLite session, so not serialization).

    That a concurrent revoke actually waits for the move is the Postgres two-session
    test ``test_a_revoke_waits_for_the_moves_membership_lock`` in
    ``tests/migrations/test_company_move_cycle_lock_19593.py``.
    """
    parent = await _org(session_factory, "Parent")
    org = await _org(session_factory, "Acme")
    async with session_factory() as session:
        svc = CompanyService(session)
        real = svc._lock_move_rows

        async def _revoke_then_lock(company_id, parent_org_id) -> None:  # noqa: ANN001
            await session.execute(sa.delete(LLCCompanyMembership).where(LLCCompanyMembership.company_id == org))
            await real(company_id, parent_org_id)

        svc._lock_move_rows = _revoke_then_lock
        with pytest.raises(NotAuthorisedError):
            await svc.move(org, parent, actor_user_id=_ACTOR)


@pytest.mark.asyncio
async def test_a_non_admin_of_the_current_parent_cannot_promote(session_factory):  # noqa: ANN001
    """Leaving a parent is done from the parent org: the sub-org's own OWNER is refused (2026-10-26)."""
    parent = await _org(session_factory, "Parent", role=MembershipRole.MEMBER)
    org = await _org(session_factory, "Acme", parent=parent)  # _ACTOR owns the sub-org
    with pytest.raises(NotAuthorisedError, match="owner/admin of the parent org"):
        await _update(session_factory, org, CompanyUpdate(parent_org_id=None))
    assert await _parent_of(session_factory, org) == parent


@pytest.mark.asyncio
async def test_a_parent_admin_with_no_membership_in_the_sub_org_promotes_it(session_factory):  # noqa: ANN001
    """An org with a parent is moved from the parent org; no role in the sub-org is needed (2026-10-26)."""
    parent = await _org(session_factory, "Parent", role=MembershipRole.ADMIN)
    org = await _org(session_factory, "Acme", parent=parent, role=None)
    await _update(session_factory, org, CompanyUpdate(parent_org_id=None))
    assert await _parent_of(session_factory, org) is None


@pytest.mark.asyncio
async def test_a_parent_admin_moves_the_sub_org_sideways_under_a_parent_it_also_admins(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.ADMIN)
    other = await _org(session_factory, "Other", role=MembershipRole.ADMIN)
    org = await _org(session_factory, "Acme", parent=parent, role=None)
    await _update(session_factory, org, CompanyUpdate(parent_org_id=other))
    assert await _parent_of(session_factory, org) == other


@pytest.mark.asyncio
async def test_a_parent_admin_still_needs_admin_on_the_new_parent_for_a_sideways_move(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.ADMIN)
    other = await _org(session_factory, "Other", role=MembershipRole.MEMBER)
    org = await _org(session_factory, "Acme", parent=parent, role=None)
    with pytest.raises(CompanyNotFoundError):
        await _update(session_factory, org, CompanyUpdate(parent_org_id=other))
    assert await _parent_of(session_factory, org) == parent


@pytest.mark.asyncio
async def test_a_new_parent_role_revoked_before_the_locks_is_caught_under_them(session_factory):  # noqa: ANN001
    """The new-parent check is repeated under the lock (a re-read; same session, see above)."""
    parent = await _org(session_factory, "Parent")
    org = await _org(session_factory, "Acme")
    async with session_factory() as session:
        svc = CompanyService(session)
        real = svc._lock_move_rows

        async def _revoke_then_lock(company_id, parent_org_id) -> None:  # noqa: ANN001
            await session.execute(sa.delete(LLCCompanyMembership).where(LLCCompanyMembership.company_id == parent))
            await real(company_id, parent_org_id)

        svc._lock_move_rows = _revoke_then_lock
        with pytest.raises(CompanyNotFoundError):
            await svc.move(org, parent, actor_user_id=_ACTOR)


@pytest.mark.asyncio
async def test_the_under_lock_checks_lock_memberships_in_company_id_order(session_factory, monkeypatch):  # noqa: ANN001
    from llc.services import authz, company

    parent = await _org(session_factory, "Parent")
    other = await _org(session_factory, "Other")
    org = await _org(session_factory, "Acme", parent=parent)
    locked: list[uuid.UUID] = []
    real = authz.require_company_admin

    async def _record(session, company_id, actor, *, for_update=False):  # noqa: ANN001, ANN202
        if for_update:
            locked.append(company_id)
        return await real(session, company_id, actor, for_update=for_update)

    monkeypatch.setattr(authz, "require_company_admin", _record)
    monkeypatch.setattr(company, "require_company_admin", _record)
    await _update(session_factory, org, CompanyUpdate(parent_org_id=other))
    assert locked == sorted([parent, other])  # the parent being left, and the new parent


@pytest.mark.asyncio
async def test_a_deadlock_on_a_membership_lock_is_a_retryable_refusal():
    org = SimpleNamespace(id=uuid.uuid4(), parent_org_id=None)
    session = MagicMock()
    session.execute = AsyncMock(side_effect=DBAPIError("SELECT", {}, _PgError("40P01")))
    with pytest.raises(CompanyMoveContendedError):
        await CompanyService(session)._authorize_locked_move(org, uuid.uuid4(), _ACTOR, False)


@pytest.mark.asyncio
async def test_the_parent_owner_who_is_not_an_admin_promotes(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.OWNER)
    org = await _org(session_factory, "Acme", parent=parent, role=MembershipRole.ADMIN)
    await _update(session_factory, org, CompanyUpdate(parent_org_id=None))
    assert await _parent_of(session_factory, org) is None


@pytest.mark.asyncio
async def test_a_mixed_patch_without_move_rights_is_403_before_any_field_check(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent")
    org = await _org(session_factory, "Acme", role=MembershipRole.MEMBER)
    async with session_factory() as session:
        svc = CompanyService(session)
        svc._assert_prefix_unique = AsyncMock(side_effect=AssertionError("field check ran before authz"))
        with pytest.raises(NotAuthorisedError):
            await svc.update(org, CompanyUpdate(parent_org_id=parent, issue_prefix="NEW"), actor_user_id=_ACTOR)


@pytest.mark.asyncio
async def test_a_budget_in_a_moving_patch_is_checked_against_the_new_parent(session_factory):  # noqa: ANN001
    old_parent = await _org(session_factory, "Old")
    new_parent = await _org(session_factory, "New")
    org = await _org(session_factory, "Acme", parent=old_parent)
    async with session_factory() as session:
        svc = CompanyService(session)
        svc._assert_budget_fits = AsyncMock()
        data = CompanyUpdate(parent_org_id=new_parent, budget_monthly_cents=100)
        await svc.update(org, data, actor_user_id=_ACTOR)
    assert svc._assert_budget_fits.await_args.args[0].id == new_parent


@pytest.mark.asyncio
async def test_a_non_admin_of_the_current_parent_cannot_move_out_sideways(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.MEMBER)
    other = await _org(session_factory, "Other")
    org = await _org(session_factory, "Acme", parent=parent)
    with pytest.raises(NotAuthorisedError):
        await _update(session_factory, org, CompanyUpdate(parent_org_id=other))
    assert await _parent_of(session_factory, org) == parent


@pytest.mark.asyncio
async def test_a_move_without_an_actor_is_refused(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent")
    org = await _org(session_factory, "Acme")
    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError):
            await CompanyService(session).move(org, parent, actor_user_id=None)


# ---------------------------------------------------------------------------
# #19589 -- explicit null promotes, absent moves nothing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_an_explicit_null_promotes_and_designates_a_ceo(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent")
    org = await _org(session_factory, "Acme", parent=parent)
    async with session_factory() as session:
        assert await CompanyCEOService().designation(session, org) is None

    await _update(session_factory, org, CompanyUpdate.model_validate({"parent_org_id": None}))

    assert await _parent_of(session_factory, org) is None
    async with session_factory() as session:
        assert await CompanyCEOService().designation(session, org) is not None


@pytest.mark.asyncio
async def test_an_absent_parent_field_moves_nothing_and_needs_no_move_rights(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=None)
    org = await _org(session_factory, "Acme", parent=parent, role=None)
    await _update(session_factory, org, CompanyUpdate.model_validate({"name": "Renamed"}))
    assert await _parent_of(session_factory, org) == parent


def test_only_parent_org_id_tells_null_from_absent():
    assert "parent_org_id" in CompanyUpdate.model_validate({"parent_org_id": None}).model_fields_set
    assert "parent_org_id" not in CompanyUpdate.model_validate({"name": "x"}).model_fields_set


# ---------------------------------------------------------------------------
# #19593 -- the rows a move locks, and their order
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_move_locks_itself_and_the_whole_new_parent_chain_in_one_pass(session_factory):  # noqa: ANN001
    top = await _org(session_factory, "Top")
    mid = await _org(session_factory, "Mid", parent=top)
    org = await _org(session_factory, "Acme")
    async with session_factory() as session:
        svc = CompanyService(session)
        calls: list[set[uuid.UUID]] = []
        real = svc._lock_ids

        async def _record(ids: set[uuid.UUID]) -> None:
            calls.append(set(ids))
            await real(ids)

        svc._lock_ids = _record
        await svc.move(org, mid, actor_user_id=_ACTOR)
    assert calls == [{org, mid, top}]


@pytest.mark.asyncio
async def test_a_chain_that_keeps_changing_is_refused_after_the_pass_cap():
    svc = CompanyService(MagicMock())
    grown: list[uuid.UUID] = []

    async def _growing_chain(_start) -> list[uuid.UUID]:  # noqa: ANN001
        grown.append(uuid.uuid4())
        return list(grown)

    locks: list[set[uuid.UUID]] = []

    async def _record(ids: set[uuid.UUID]) -> None:
        locks.append(set(ids))

    svc._chain_ids = _growing_chain
    svc._lock_ids = _record
    with pytest.raises(CompanyMoveContendedError):
        await svc._lock_move_rows(uuid.uuid4(), uuid.uuid4())
    assert len(locks) == MOVE_LOCK_MAX_PASSES
    # Every pass re-locks the FULL set (one id-ordered statement), never just the new rows.
    assert all(earlier < later for earlier, later in zip(locks, locks[1:]))


class _PgError(Exception):
    def __init__(self, sqlstate: str) -> None:
        super().__init__(sqlstate)
        self.sqlstate = sqlstate


@pytest.mark.asyncio
async def test_a_deadlock_while_locking_is_a_retryable_refusal():
    session = MagicMock()
    session.execute = AsyncMock(side_effect=DBAPIError("SELECT", {}, _PgError("40P01")))
    with pytest.raises(CompanyMoveContendedError):
        await CompanyService(session)._lock_ids({uuid.uuid4()})


@pytest.mark.asyncio
async def test_any_other_database_error_while_locking_propagates():
    session = MagicMock()
    session.execute = AsyncMock(side_effect=DBAPIError("SELECT", {}, _PgError("57014")))
    with pytest.raises(DBAPIError):
        await CompanyService(session)._lock_ids({uuid.uuid4()})


@pytest.mark.asyncio
async def test_the_lock_statement_takes_rows_for_update_in_id_order():
    session = MagicMock()
    session.execute = AsyncMock()
    await CompanyService(session)._lock_ids({uuid.uuid4(), uuid.uuid4()})
    sql = str(session.execute.await_args.args[0].compile(dialect=postgresql.dialect()))
    assert "ORDER BY organizations.id" in sql
    assert sql.rstrip().endswith("FOR UPDATE")


# ---------------------------------------------------------------------------
# The route: actor and admin flag reach the service; refusal is a 403
# ---------------------------------------------------------------------------


def _app(svc) -> FastAPI:  # noqa: ANN001
    app = FastAPI()
    app.include_router(companies.router, prefix="/api/llc")
    app.dependency_overrides[companies._get_service] = lambda: svc
    app.dependency_overrides[get_current_user] = lambda: {"user_id": str(_ACTOR)}
    ctx = TenantContext(org_id=_ORG_ID, user_id=_ACTOR, is_platform_admin=False)
    app.dependency_overrides[require_org_context] = lambda: ctx
    return app


@pytest.mark.asyncio
async def test_the_route_answers_a_refused_move_with_403_and_rolls_back():
    svc = SimpleNamespace(session=AsyncMock(), update=AsyncMock(side_effect=NotAuthorisedError("no")))
    transport = httpx.ASGITransport(app=_app(svc))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(f"/api/llc/companies/{_ORG_ID}", json={"parent_org_id": None})
    assert resp.status_code == 403
    assert resp.json()["detail"] == "Forbidden"  # never the exception's internal text
    svc.session.rollback.assert_awaited_once()
    svc.session.commit.assert_not_called()
    _, body = svc.update.await_args.args
    assert "parent_org_id" in body.model_fields_set and body.parent_org_id is None
    assert svc.update.await_args.kwargs == {"actor_user_id": _ACTOR, "platform_admin": False}


@pytest.mark.asyncio
async def test_the_route_answers_a_contended_move_with_409():
    svc = SimpleNamespace(session=AsyncMock(), update=AsyncMock(side_effect=CompanyMoveContendedError("busy")))
    transport = httpx.ASGITransport(app=_app(svc))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(f"/api/llc/companies/{_ORG_ID}", json={"parent_org_id": None})
    assert resp.status_code == 409
    assert "try again" in resp.json()["detail"]
    svc.session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_the_route_shows_only_the_fixed_text_of_a_move_refusal(session_factory):  # noqa: ANN001
    parent = await _org(session_factory, "Parent", role=MembershipRole.MEMBER)
    org = await _org(session_factory, "Acme", parent=parent)
    async with session_factory() as session:
        with pytest.raises(CompanyMoveForbiddenError) as refused:
            await CompanyService(session).update(org, CompanyUpdate(parent_org_id=None), actor_user_id=_ACTOR)
    svc = SimpleNamespace(session=AsyncMock(), update=AsyncMock(side_effect=refused.value))
    transport = httpx.ASGITransport(app=_app(svc))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.patch(f"/api/llc/companies/{_ORG_ID}", json={"parent_org_id": None})
    detail = resp.json()["detail"]
    assert resp.status_code == 403
    assert detail == "Moving this company out of its parent must be done by an owner/admin of the parent org"
    assert str(org) not in detail and str(parent) not in detail and str(_ACTOR) not in detail


@pytest.mark.asyncio
async def test_a_deadlock_during_the_ceo_sync_is_a_retryable_refusal(session_factory, monkeypatch):  # noqa: ANN001
    """The flush and the CEO sync run under the move's locks too, so a deadlock there is a 409, not a 500."""
    from llc.services.company_ceo import CompanyCEOService

    parent = await _org(session_factory, "Parent")
    org = await _org(session_factory, "Acme", parent=parent)
    deadlock = AsyncMock(side_effect=DBAPIError("UPDATE", {}, _PgError("40P01")))
    monkeypatch.setattr(CompanyCEOService, "sync_with_parent", deadlock)
    async with session_factory() as session:
        with pytest.raises(CompanyMoveContendedError):
            await CompanyService(session).update(org, CompanyUpdate(parent_org_id=None), actor_user_id=_ACTOR)
    deadlock.assert_awaited_once()
    assert await _parent_of(session_factory, org) == parent
