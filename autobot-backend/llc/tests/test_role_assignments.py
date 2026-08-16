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
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.authz import NotAuthorisedError
from llc.services.role import RoleService
from llc.services.role_assignment import RoleAssignmentService

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.role import Role


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [Role.__table__, LLCRoleAssignment.__table__, LLCCompanyMembership.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


#: Every mutation is admin-gated, so the suite acts as one admin throughout.
#: Authorisation itself is tested in ``test_role_permissions.py`` and by
#: ``test_a_member_cannot_assign_themselves_to_a_role`` below; these tests are
#: about occupancy semantics, not about who may change it.
_ADMIN_USER = uuid.uuid4()


async def _grant_admin(session_factory, company_id: uuid.UUID) -> None:  # noqa: ANN001
    """Make ``_ADMIN_USER`` an admin of this company, once."""
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


async def _seed_role(session_factory, company_id: uuid.UUID, name: str) -> uuid.UUID:  # noqa: ANN001
    await _grant_admin(session_factory, company_id)
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
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.USER,
            holder_id=holder,
        )
        await session.commit()
        assignment_id = assignment.id

    async with session_factory() as session:
        ended = await service.end_tenure(session, company, assignment_id, actor_user_id=_ADMIN_USER)
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
            actor_user_id=_ADMIN_USER,
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
                actor_user_id=_ADMIN_USER,
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
            actor_user_id=_ADMIN_USER,
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
                actor_user_id=_ADMIN_USER,
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
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=holder,
        )
        await session.commit()
        first_id = first.id

    async with session_factory() as session:
        await service.end_tenure(session, company, first_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        await service.assign(
            session,
            actor_user_id=_ADMIN_USER,
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
    # Admin of company_a too: without this the authorisation gate fires
    # first and the test would no longer reach the scoping check.
    await _grant_admin(session_factory, company_a)
    theirs = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="does not exist in company"):
            await service.assign(
                session,
                actor_user_id=_ADMIN_USER,
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
            actor_user_id=_ADMIN_USER,
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
    # Admin of company_a too: without this the authorisation gate fires
    # first and the test would no longer reach the scoping check.
    await _grant_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        assignment = await service.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company_b,
            role_id=role_b,
            holder_type=RoleHolderType.AGENT,
            holder_id=uuid.uuid4(),
        )
        await session.commit()
        assignment_id = assignment.id

    async with session_factory() as session:
        assert await service.end_tenure(session, company_a, assignment_id, actor_user_id=_ADMIN_USER) is None
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
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=uuid.uuid4(),
        )
        await session.commit()
        assignment_id = assignment.id

    async with session_factory() as session:
        await service.end_tenure(session, company, assignment_id, ended_at=original, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        assert await service.end_tenure(session, company, assignment_id, actor_user_id=_ADMIN_USER) is None
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
                actor_user_id=_ADMIN_USER,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.USER,
                holder_id=leaver,
            )
        await service.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company,
            role_id=sre,
            holder_type=RoleHolderType.USER,
            holder_id=stayer,
        )
        await session.commit()

    async with session_factory() as session:
        closed = await service.vacate_holder(session, company, RoleHolderType.USER, leaver, actor_user_id=_ADMIN_USER)
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
                actor_user_id=_ADMIN_USER,
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
                actor_user_id=_ADMIN_USER,
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
async def test_offboarding_emits_one_event_per_vacated_role(session_factory):  # noqa: ANN001
    """Each role losing its holder is its own event, not one 'they left'.

    A single departure event would make "which roles fell vacant on the 3rd"
    unanswerable — which is the question offboarding exists to answer.
    """
    log = _RecordingActivityLog()
    service = RoleAssignmentService(activity_log=log)
    company = uuid.uuid4()
    sre = await _seed_role(session_factory, company, "SRE")
    lead = await _seed_role(session_factory, company, "Team Lead")
    leaver = uuid.uuid4()

    async with session_factory() as session:
        for role_id in (sre, lead):
            await service.assign(
                session,
                actor_user_id=_ADMIN_USER,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.USER,
                holder_id=leaver,
            )
        await session.commit()

    assert [e["event_type"] for e in log.events] == ["role_assignment.created"] * 2
    log.events.clear()

    async with session_factory() as session:
        await service.vacate_holder(session, company, RoleHolderType.USER, leaver, actor_user_id=_ADMIN_USER)
        await session.commit()

    assert [e["event_type"] for e in log.events] == ["role_assignment.ended"] * 2
    assert {e["after"]["role_id"] for e in log.events} == {str(sre), str(lead)}
    assert all(e["entity_type"] == "llc_role_assignment" for e in log.events)
    assert all(e["company_id"] == str(company) for e in log.events)


@pytest.mark.asyncio
async def test_a_scoped_out_end_tenure_emits_nothing(session_factory):  # noqa: ANN001
    """Failing to end another company's tenure must not log an ending."""
    log = _RecordingActivityLog()
    service = RoleAssignmentService(activity_log=log)
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    # Admin of company_a too: without this the authorisation gate fires
    # first and the test would no longer reach the scoping check.
    await _grant_admin(session_factory, company_a)
    role_b = await _seed_role(session_factory, company_b, "SRE")

    async with session_factory() as session:
        assignment = await service.assign(
            session,
            actor_user_id=_ADMIN_USER,
            company_id=company_b,
            role_id=role_b,
            holder_type=RoleHolderType.AGENT,
            holder_id=uuid.uuid4(),
        )
        await session.commit()
        assignment_id = assignment.id
        log.events.clear()

    async with session_factory() as session:
        assert await service.end_tenure(session, company_a, assignment_id, actor_user_id=_ADMIN_USER) is None
        await session.commit()

    assert log.events == []


@pytest.mark.asyncio
async def test_a_member_cannot_assign_themselves_to_a_role(session_factory):  # noqa: ANN001
    """The privilege escalation this gate exists to close.

    Permission *granting* was admin-only, but occupancy was not — so a plain
    member could assign themselves to a role an admin had granted permissions
    to and inherit them immediately. ``effective_permissions()`` honours any
    open tenure and cannot see who created it, so gating the grant path alone
    was fully bypassable once the routes existed.
    """
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "Head of Sales")
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
        with pytest.raises(NotAuthorisedError, match="may not perform this change"):
            await service.assign(
                session,
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.USER,
                holder_id=member,
                actor_user_id=member,
            )

    async with session_factory() as session:
        assert await service.current_holders(session, company, role_id) == []


@pytest.mark.asyncio
async def test_a_member_cannot_end_another_holders_tenure(session_factory):  # noqa: ANN001
    """Otherwise any member could strip an owner of their role."""
    service = RoleAssignmentService()
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    member, holder = uuid.uuid4(), uuid.uuid4()
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
        tenure = await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=holder,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()
        tenure_id = tenure.id

    async with session_factory() as session:
        with pytest.raises(NotAuthorisedError):
            await service.end_tenure(session, company, tenure_id, actor_user_id=member)

    async with session_factory() as session:
        assert len(await service.current_holders(session, company, role_id)) == 1


@pytest.mark.asyncio
async def test_the_database_itself_rejects_a_duplicate_open_tenure(session_factory):  # noqa: ANN001
    """The partial unique index, exercised — not just the service pre-check.

    ``assign()`` guards with a SELECT-then-INSERT, which a concurrent caller can
    race. The real protection is the partial unique index, and it was declared
    only in the migration — so ``create_all`` never built it and no test touched
    it. This inserts directly, bypassing the service, and asserts the *database*
    refuses.
    """
    company = uuid.uuid4()
    role_id = await _seed_role(session_factory, company, "SRE")
    holder = uuid.uuid4()

    async with session_factory() as session:
        await RoleAssignmentService().assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=holder,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        session.add(
            LLCRoleAssignment(
                company_id=company,
                role_id=role_id,
                holder_type=RoleHolderType.AGENT.value,
                holder_agent_id=holder,
            )
        )
        with pytest.raises(IntegrityError):
            await session.commit()


@pytest.mark.asyncio
async def test_the_database_allows_a_second_tenure_once_the_first_ended(session_factory):  # noqa: ANN001
    """The partial index must not forbid returning to a role you once held."""
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
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()
        first_id = first.id

    async with session_factory() as session:
        await service.end_tenure(session, company, first_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        await service.assign(
            session,
            company_id=company,
            role_id=role_id,
            holder_type=RoleHolderType.AGENT,
            holder_id=holder,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        assert len(await service.history(session, company, role_id)) == 2


@pytest.mark.asyncio
async def test_vacate_holder_is_company_scoped(session_factory):  # noqa: ANN001
    """The one mutating method that had no cross-company test."""
    service = RoleAssignmentService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    role_b = await _seed_role(session_factory, company_b, "SRE")
    await _grant_admin(session_factory, company_a)
    holder = uuid.uuid4()

    async with session_factory() as session:
        await service.assign(
            session,
            company_id=company_b,
            role_id=role_b,
            holder_type=RoleHolderType.USER,
            holder_id=holder,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.vacate_holder(session, company_a, RoleHolderType.USER, holder, actor_user_id=_ADMIN_USER)
            == []
        )
        await session.commit()

    async with session_factory() as session:
        assert len(await service.current_holders(session, company_b, role_b)) == 1
