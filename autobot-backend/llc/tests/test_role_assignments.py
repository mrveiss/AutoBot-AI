# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Occupancy, history survival and company scoping for role assignments (#14221 step 2).

The load-bearing test here is ``test_ending_a_tenure_never_removes_the_row``.
The owner's requirement is that work left behind still belongs somewhere:

    work items do not go anywhere, they remain behind when an employee leaves

An implementation that DELETEs on departure passes every "is this person still
a holder?" assertion while destroying exactly the history that requirement
depends on — so the invariant is asserted directly rather than inferred from
the absence of the holder.

Two companies throughout: with one company's rows in the database, a dropped
``WHERE company_id`` stays green. That gap has been closed independently five
times in this module (#13936, #13969, #13942, #14222, #14210).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import RoleHolderType
from llc.models.role import LLCRole
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.role import RoleService
from llc.services.role_assignment import RoleAssignmentService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [LLCRole.__table__, LLCRoleAssignment.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _seed_role(session_factory, company_id: uuid.UUID, name: str) -> uuid.UUID:  # noqa: ANN001
    async with session_factory() as session:
        role = await RoleService().create(session, company_id=company_id, name=name)
        await session.commit()
        return role.id


@pytest.mark.asyncio
async def test_ending_a_tenure_never_removes_the_row(session_factory):  # noqa: ANN001
    """The owner's requirement, asserted directly.

    A DELETE-on-departure implementation passes "is she still a holder?" while
    destroying the history that work left behind depends on.
    """
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
    holder = uuid.uuid4()

    async with session_factory() as session:
        assignment = await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.USER,
            holder_id=holder,
        )
        await session.commit()
        assignment_id = assignment.id

    async with session_factory() as session:
        ended = await service.end_tenure(session, company, assignment_id)
        await session.commit()
        assert ended is not None and ended.ended_at is not None

    async with session_factory() as session:
        assert await service.current_holders(session, company, role_id) == []
        past = await service.history(session, company, role_id)

    assert len(past) == 1, "the tenure row was destroyed on departure"
    assert past[0].holder_user_id == holder
    assert past[0].ended_at is not None


@pytest.mark.asyncio
async def test_a_contact_can_hold_a_role_without_being_a_user(session_factory):  # noqa: ANN001
    """Not all humans are users — a contact person can occupy a role."""
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Supplier escalation contact")
    contact = uuid.uuid4()

    async with session_factory() as session:
        assignment = await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.CONTACT,
            holder_id=contact,
        )
        await session.commit()

    assert assignment.holder_contact_id == contact
    assert assignment.holder_user_id is None and assignment.holder_agent_id is None
    assert assignment.holder_id == contact


@pytest.mark.asyncio
async def test_one_role_may_have_several_concurrent_holders(session_factory):  # noqa: ANN001
    """Three people can all be 'SRE' — there is no single-holder constraint."""
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        for _ in range(3):
            await service.assign(
                session,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.AGENT,
                holder_id=uuid.uuid4(),
            )
        await session.commit()

    async with session_factory() as session:
        assert len(await service.current_holders(session, company, role_id)) == 3


@pytest.mark.asyncio
async def test_the_same_holder_cannot_hold_one_role_twice_at_once(session_factory):  # noqa: ANN001
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    holder = uuid.uuid4()

    async with session_factory() as session:
        await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=holder,
        )
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="already holds"):
            await service.assign(
                session,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.AGENT,
                holder_id=holder,
            )


@pytest.mark.asyncio
async def test_reassigning_after_a_tenure_ended_is_allowed(session_factory):  # noqa: ANN001
    """Returning to a role you once held is legitimate, not a duplicate."""
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    holder = uuid.uuid4()

    async with session_factory() as session:
        first = await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=holder,
        )
        await session.commit()
        first_id = first.id

    async with session_factory() as session:
        await service.end_tenure(session, company, first_id)
        await session.commit()

    async with session_factory() as session:
        await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=holder,
        )
        await session.commit()

    async with session_factory() as session:
        assert len(await service.history(session, company, role_id)) == 2
        assert len(await service.current_holders(session, company, role_id)) == 1


@pytest.mark.asyncio
async def test_cannot_assign_to_another_companys_role(session_factory):  # noqa: ANN001
    """Knowing a role id must not be enough to assign into it."""
    service = RoleAssignmentService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    theirs = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="does not exist in company"):
            await service.assign(
                session,
                company_id=company_a,
                role_id=theirs,
                holder_type=RoleHolderType.AGENT,
                holder_id=uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_current_holders_and_history_are_company_scoped(session_factory):  # noqa: ANN001
    service = RoleAssignmentService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        await service.assign(
            session,
            company_id=company_b,
            role_id=role_b,
            holder_type=RoleHolderType.AGENT,
            holder_id=uuid.uuid4(),
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.current_holders(session, company_a, role_b) == []
        assert await service.history(session, company_a, role_b) == []
        assert len(await service.current_holders(session, company_b, role_b)) == 1


@pytest.mark.asyncio
async def test_end_tenure_is_company_scoped(session_factory):  # noqa: ANN001
    service = RoleAssignmentService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        assignment = await service.assign(
            session,
            company_id=company_b,
            role_id=role_b,
            holder_type=RoleHolderType.AGENT,
            holder_id=uuid.uuid4(),
        )
        await session.commit()
        assignment_id = assignment.id

    async with session_factory() as session:
        assert await service.end_tenure(session, company_a, assignment_id) is None
        await session.commit()

    async with session_factory() as session:
        assert len(await service.current_holders(session, company_b, role_b)) == 1


@pytest.mark.asyncio
async def test_ending_an_already_ended_tenure_does_not_rewrite_it(session_factory):  # noqa: ANN001
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    original = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async with session_factory() as session:
        assignment = await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=uuid.uuid4(),
        )
        await session.commit()
        assignment_id = assignment.id

    async with session_factory() as session:
        await service.end_tenure(session, company, assignment_id, ended_at=original)
        await session.commit()

    async with session_factory() as session:
        assert await service.end_tenure(session, company, assignment_id) is None
        await session.commit()

    async with session_factory() as session:
        rows = await service.history(session, company, role_id)
    assert rows[0].ended_at.replace(tzinfo=timezone.utc) == original


@pytest.mark.asyncio
async def test_vacate_holder_ends_every_role_and_keeps_the_history(session_factory):  # noqa: ANN001
    """Offboarding: the person leaves, the roles and their history stay."""
    service = RoleAssignmentService()
    company = uuid.uuid4()
    sre = await _seed_role(session_factory, company, "SRE")
    lead = await _seed_role(session_factory, company, "Team Lead")
    leaver = uuid.uuid4()
    stayer = uuid.uuid4()

    async with session_factory() as session:
        for role_id in (sre, lead):
            await service.assign(
                session,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.USER,
                holder_id=leaver,
            )
        await service.assign(
            session,
            company_id=company,
            role_id=sre,
            holder_type=RoleHolderType.USER,
            holder_id=stayer,
        )
        await session.commit()

    async with session_factory() as session:
        closed = await service.vacate_holder(session, company, RoleHolderType.USER, leaver)
        await session.commit()

    assert len(closed) == 2, "offboarding must surface every role left vacant"

    async with session_factory() as session:
        # The other holder is untouched, and both roles still exist.
        assert len(await service.current_holders(session, company, sre)) == 1
        assert await service.current_holders(session, company, lead) == []
        assert len(await service.history(session, company, lead)) == 1
        assert await service.roles_held_by(session, company, RoleHolderType.USER, leaver) == []


@pytest.mark.asyncio
async def test_roles_held_by_is_scoped_and_lists_only_open_tenures(session_factory):  # noqa: ANN001
    service = RoleAssignmentService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_a = await _seed_role(session_factory, company_a, "SRE")
    role_b = await _seed_role(session_factory, company_b, "SRE")
    holder = uuid.uuid4()

    async with session_factory() as session:
        for company, role_id in ((company_a, role_a), (company_b, role_b)):
            await service.assign(
                session,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.USER,
                holder_id=holder,
            )
        await session.commit()

    async with session_factory() as session:
        held = await service.roles_held_by(session, company_a, RoleHolderType.USER, holder)

    assert [r.id for r in held] == [role_a], "another company's tenure leaked into this holder's roles"


@pytest.mark.asyncio
async def test_an_invalid_holder_type_is_rejected_before_it_reaches_the_column(session_factory):  # noqa: ANN001
    """``String(16)`` would store 'humna' happily; the enum must refuse it."""
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="invalid holder_type"):
            await service.assign(
                session,
                company_id=company,
                role_id=role_id,
                holder_type="human",  # AssigneeType/CoWorkerType's word, never this enum's
                holder_id=uuid.uuid4(),
            )


@pytest.mark.asyncio
async def test_holder_id_returns_none_when_the_discriminator_does_not_match(session_factory):  # noqa: ANN001
    """A corrupt row must not silently report whichever id happens to be set."""
    assignment = LLCRoleAssignment(
        company_id=uuid.uuid4(),
        role_id=uuid.uuid4(),
        holder_type="contact",
        holder_user_id=uuid.uuid4(),
    )
    assert assignment.holder_id is None
