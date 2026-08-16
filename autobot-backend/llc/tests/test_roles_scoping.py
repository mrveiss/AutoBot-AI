# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Company scoping for roles on the canonical ``roles`` table (#14221 step 1).

Two-company fixtures throughout: with one company's rows present, a dropped
``WHERE org_id`` predicate stays green while returning every company's roles.
That gap has been closed independently five times in this module (#13936,
#13969, #13942, #14222, #14210), so it is written first rather than found again.

The tests that matter most here are the **system-role** ones. This service
operates on a table it does not own — one shared with the platform's RBAC — so
"a company-scoped caller cannot see or touch a system role" is a property that
did not need testing when the role table was ours alone, and does now.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.services.authz import NotAuthorisedError
from llc.services.role import RoleService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [Role.__table__, LLCCompanyMembership.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        # The roles table carries an FK to organizations; SQLite does not
        # enforce FKs unless asked, and this suite is about the scoping
        # predicate rather than referential integrity.
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


#: Role CRUD is admin-gated (#14324 security review); this suite acts as one
#: admin. Who may mutate is tested separately, below and in
#: ``test_role_permissions.py``.
_ADMIN_USER = uuid.uuid4()


async def _grant_admin(session_factory, company_id: uuid.UUID) -> None:  # noqa: ANN001
    async with session_factory() as session:
        existing = await session.execute(
            sa.select(LLCCompanyMembership.id).where(
                LLCCompanyMembership.company_id == company_id,
                LLCCompanyMembership.user_id == _ADMIN_USER,
            )
        )
        if existing.scalar_one_or_none() is not None:
            return
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=_ADMIN_USER,
                role=MembershipRole.ADMIN.value,
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_company_a_never_sees_company_bs_roles(session_factory):  # noqa: ANN001
    """The reproduction: deleting the org_id predicate must fail this."""
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)

    async with session_factory() as session:
        await service.create(session, company_id=company_a, name="Head of Sales", actor_user_id=_ADMIN_USER)
        await service.create(session, company_id=company_b, name="SRE", actor_user_id=_ADMIN_USER)
        await service.create(session, company_id=company_b, name="Marketing Lead", actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        listed = await service.list_by_company(session, company_a)

    assert [role.name for role in listed] == [
        "Head of Sales"
    ], f"company B's roles leaked into company A: {[r.name for r in listed]}"


@pytest.mark.asyncio
async def test_a_user_can_hold_a_different_role_in_each_company(session_factory):  # noqa: ANN001
    """Owner requirement: roles are per company, so the same person differs by company.

    This is the property that made a separate ``llc_roles`` table unnecessary —
    two ``Role`` rows with different ``org_id`` already express it.
    """
    service = RoleService()
    marketing, it_company = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, marketing)
    await _grant_admin(session_factory, it_company)

    async with session_factory() as session:
        sales = await service.create(session, company_id=marketing, name="Head of Sales", actor_user_id=_ADMIN_USER)
        sre = await service.create(session, company_id=it_company, name="SRE", actor_user_id=_ADMIN_USER)
        await session.commit()

    assert sales.id != sre.id
    assert sales.org_id == marketing and sre.org_id == it_company


@pytest.mark.asyncio
async def test_a_system_role_is_invisible_to_a_company(session_factory):  # noqa: ANN001
    """System roles have org_id NULL and must never appear in a company's list."""
    service = RoleService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)

    async with session_factory() as session:
        session.add(Role(org_id=None, name="admin", is_system=True))
        await service.create(session, company_id=company, name="Head of Sales", actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        listed = await service.list_by_company(session, company)

    assert [r.name for r in listed] == ["Head of Sales"], "a system role leaked into a company"


@pytest.mark.asyncio
async def test_a_system_role_cannot_be_deleted_through_a_company_path(session_factory):  # noqa: ANN001
    """Even carrying an org_id, a system role must refuse company-scoped writes.

    Belt and braces: the org_id filter alone would hide a system role with a
    NULL org_id, but says nothing about one that has an org_id set.
    """
    service = RoleService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)

    async with session_factory() as session:
        system_role = Role(org_id=company, name="platform-admin", is_system=True)
        session.add(system_role)
        await session.commit()
        role_id = system_role.id

    async with session_factory() as session:
        with pytest.raises(ValueError, match="system role cannot be deleted"):
            await service.delete(session, company, role_id, actor_user_id=_ADMIN_USER)
        with pytest.raises(ValueError, match="system role cannot be modified"):
            await service.update(session, company, role_id, name="hijacked", actor_user_id=_ADMIN_USER)

    async with session_factory() as session:
        assert await service.get(session, company, role_id) is not None


@pytest.mark.asyncio
async def test_get_is_scoped_so_another_companys_role_is_invisible(session_factory):  # noqa: ANN001
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)

    async with session_factory() as session:
        theirs = await service.create(session, company_id=company_b, name="SRE", actor_user_id=_ADMIN_USER)
        await session.commit()
        theirs_id = theirs.id

    async with session_factory() as session:
        # Knowing the id must not be enough to read it from another company.
        assert await service.get(session, company_a, theirs_id) is None
        assert await service.get(session, company_b, theirs_id) is not None


@pytest.mark.asyncio
async def test_delete_never_removes_another_companys_role(session_factory):  # noqa: ANN001
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)

    async with session_factory() as session:
        theirs = await service.create(session, company_id=company_b, name="SRE", actor_user_id=_ADMIN_USER)
        await session.commit()
        theirs_id = theirs.id

    async with session_factory() as session:
        assert await service.delete(session, company_a, theirs_id, actor_user_id=_ADMIN_USER) is False
        await session.commit()

    async with session_factory() as session:
        assert await service.get(session, company_b, theirs_id) is not None


@pytest.mark.asyncio
async def test_two_companies_may_each_have_the_same_role_name(session_factory):  # noqa: ANN001
    """Uniqueness is per company — a 'Head of Sales' in each is two roles."""
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)

    async with session_factory() as session:
        a_role = await service.create(session, company_id=company_a, name="Head of Sales", actor_user_id=_ADMIN_USER)
        b_role = await service.create(session, company_id=company_b, name="Head of Sales", actor_user_id=_ADMIN_USER)
        await session.commit()

    assert a_role.id != b_role.id


@pytest.mark.asyncio
async def test_a_duplicate_name_within_one_company_is_refused(session_factory):  # noqa: ANN001
    """Enforced in the service: the shared roles table has no (org_id, name) constraint.

    If a unique constraint is ever added upstream this test still passes — it
    asserts the behaviour, not which layer produces it.
    """
    service = RoleService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)

    async with session_factory() as session:
        await service.create(session, company_id=company, name="Head of Sales", actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="already exists"):
            await service.create(session, company_id=company, name="  Head of Sales  ", actor_user_id=_ADMIN_USER)


@pytest.mark.asyncio
async def test_a_blank_name_is_rejected(session_factory):  # noqa: ANN001
    service = RoleService()
    company = uuid.uuid4()
    # Authorisation runs before input validation, so an unauthorised caller
    # cannot probe validation behaviour. That ordering is deliberate, and it is
    # why this test needs a real admin rather than an ad-hoc company id.
    await _grant_admin(session_factory, company)
    async with session_factory() as session:
        with pytest.raises(ValueError, match="name is required"):
            await service.create(session, company_id=company, name="   ", actor_user_id=_ADMIN_USER)


@pytest.mark.asyncio
async def test_create_requires_a_company(session_factory):  # noqa: ANN001
    service = RoleService()
    async with session_factory() as session:
        with pytest.raises(ValueError, match="company_id is required"):
            await service.create(session, company_id=None, name="Orphan", actor_user_id=_ADMIN_USER)


@pytest.mark.asyncio
async def test_update_is_scoped_and_still_trims(session_factory):  # noqa: ANN001
    service = RoleService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)

    async with session_factory() as session:
        theirs = await service.create(session, company_id=company_b, name="SRE", actor_user_id=_ADMIN_USER)
        await session.commit()
        theirs_id = theirs.id

    async with session_factory() as session:
        assert await service.update(session, company_a, theirs_id, name="Hijacked", actor_user_id=_ADMIN_USER) is None
        updated = await service.update(
            session, company_b, theirs_id, name="  Platform SRE  ", actor_user_id=_ADMIN_USER
        )
        assert updated is not None and updated.name == "Platform SRE"
        await session.commit()


class _RecordingActivityLog:
    """Captures ``record()`` calls — a stateful fake, not a MagicMock.

    A MagicMock makes "an event was emitted" and "nothing was written" look
    identical, which is the failure this module has hit before.
    """

    def __init__(self) -> None:
        self.events: list[dict] = []

    async def record(self, **kwargs) -> None:  # noqa: ANN003
        self.events.append(kwargs)


@pytest.mark.asyncio
async def test_mutations_emit_activity_log_events(session_factory):  # noqa: ANN001
    """``role.deleted`` needs the row read *before* the DELETE, or it has no entity."""
    log = _RecordingActivityLog()
    service = RoleService(activity_log=log)
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)

    async with session_factory() as session:
        role = await service.create(session, company_id=company, name="SRE", actor_user_id=_ADMIN_USER)
        await service.update(session, company, role.id, name="Platform SRE", actor_user_id=_ADMIN_USER)
        assert await service.delete(session, company, role.id, actor_user_id=_ADMIN_USER) is True
        await session.commit()

    assert [e["event_type"] for e in log.events] == [
        "role.created",
        "role.updated",
        "role.deleted",
    ]
    assert {e["entity_id"] for e in log.events} == {str(role.id)}
    assert all(e["entity_type"] == "role" for e in log.events)
    assert all(e["company_id"] == str(company) for e in log.events)


@pytest.mark.asyncio
async def test_a_scoped_out_delete_emits_nothing(session_factory):  # noqa: ANN001
    log = _RecordingActivityLog()
    service = RoleService(activity_log=log)
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)

    async with session_factory() as session:
        role = await service.create(session, company_id=company_b, name="SRE", actor_user_id=_ADMIN_USER)
        await session.commit()
        log.events.clear()

    async with session_factory() as session:
        assert await service.delete(session, company_a, role.id, actor_user_id=_ADMIN_USER) is False
        await session.commit()

    assert log.events == []


@pytest.mark.asyncio
async def test_a_member_cannot_create_or_delete_a_role(session_factory):  # noqa: ANN001
    """Role CRUD is admin-only (#14324 security review).

    Deleting a role destroys its permission grants and every current holder's
    access through it, so this is an availability and integrity boundary, not
    only a tidiness one.
    """
    service = RoleService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    member = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company,
                user_id=member,
                role=MembershipRole.MEMBER.value,
            )
        )
        await session.commit()

    async with session_factory() as session:
        existing = await service.create(session, company_id=company, name="SRE", actor_user_id=_ADMIN_USER)
        await session.commit()
        role_id = existing.id

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError, match="may not perform this change"):
            await service.create(session, company_id=company, name="Invented", actor_user_id=member)
        with pytest.raises(NotAuthorisedError):
            await service.delete(session, company, role_id, actor_user_id=member)
        with pytest.raises(NotAuthorisedError):
            await service.update(session, company, role_id, name="Hijacked", actor_user_id=member)

    async with session_factory() as session:
        remaining = await service.list_by_company(session, company)
    assert [r.name for r in remaining] == ["SRE"]
