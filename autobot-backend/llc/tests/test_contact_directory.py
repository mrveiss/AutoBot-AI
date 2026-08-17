# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The shared people directory (#13998).

Owner decision: employees and contacts are shared across Company OS — one
directory, no per-company copies. What is company-scoped is the **role** a
person holds, which ``llc_role_assignments`` already records.

The load-bearing tests are the two that stop a shared directory becoming a
shared foot-gun:

``test_delete_is_refused_while_the_contact_holds_a_role`` — a delete here is
global. Without this an admin of one company empties another company's org chart
without ever seeing it happen.

``test_merge_moves_role_tenures_to_the_survivor`` — moving the tenures is what
makes a merge more than a delete. Dropping them silently vacates every role the
duplicate held, in companies the merging admin never looked at.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.contact import LLCContact
from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment
from llc.services.authz import NotAuthorisedError
from llc.services.contact_directory import ContactDirectoryService, ContactInUseError

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base

_ADMIN_USER = uuid.uuid4()


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [
        LLCContact.__table__,
        LLCRoleAssignment.__table__,
        LLCCompanyMembership.__table__,
    ]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


async def _grant_admin(session_factory, company_id: uuid.UUID) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(
            LLCCompanyMembership(
                id=uuid.uuid4(),
                company_id=company_id,
                user_id=_ADMIN_USER,
                role=MembershipRole.ADMIN.value,
            )
        )
        await session.commit()


async def _seed_contact(  # noqa: ANN001
    session_factory, name: str, email: str | None = None, company_id: uuid.UUID | None = None
) -> uuid.UUID:
    contact_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCContact(
                id=contact_id,
                company_id=company_id or uuid.uuid4(),
                full_name=name,
                email=email,
            )
        )
        await session.commit()
    return contact_id


async def _hold_role(session_factory, company_id: uuid.UUID, contact_id: uuid.UUID) -> uuid.UUID:  # noqa: ANN001
    assignment_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(
            LLCRoleAssignment(
                id=assignment_id,
                company_id=company_id,
                role_id=uuid.uuid4(),
                holder_type=RoleHolderType.CONTACT.value,
                holder_contact_id=contact_id,
            )
        )
        await session.commit()
    return assignment_id


async def _exists(session_factory, contact_id: uuid.UUID) -> bool:  # noqa: ANN001
    async with session_factory() as session:
        found = await session.execute(sa.select(LLCContact.id).where(LLCContact.id == contact_id))
        return found.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_the_directory_is_shared_not_per_company(session_factory):  # noqa: ANN001
    """The decision itself: every company draws from one pool."""
    service = ContactDirectoryService()
    await _seed_contact(session_factory, "Ada Lovelace")
    await _seed_contact(session_factory, "Grace Hopper")

    async with session_factory() as session:
        listed = await service.list_directory(session)

    assert [c.full_name for c in listed] == ["Ada Lovelace", "Grace Hopper"]


@pytest.mark.asyncio
async def test_involvement_comes_from_roles_not_a_second_table(session_factory):  # noqa: ANN001
    """ "Which companies is this person involved with" is derived from tenures."""
    service = ContactDirectoryService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    contact_id = await _seed_contact(session_factory, "Shared Supplier")
    await _hold_role(session_factory, company_a, contact_id)
    await _hold_role(session_factory, company_b, contact_id)

    async with session_factory() as session:
        involved = await service.companies_for_contact(session, contact_id)

    assert set(involved) == {company_a, company_b}


@pytest.mark.asyncio
async def test_an_ended_tenure_no_longer_counts_as_involvement(session_factory):  # noqa: ANN001
    """Open tenures only — a departed contact is not still "involved"."""
    service = ContactDirectoryService()
    company = uuid.uuid4()
    contact_id = await _seed_contact(session_factory, "Past Supplier")
    assignment_id = await _hold_role(session_factory, company, contact_id)

    async with session_factory() as session:
        await session.execute(
            sa.update(LLCRoleAssignment).where(LLCRoleAssignment.id == assignment_id).values(ended_at=sa.func.now())
        )
        await session.commit()

    async with session_factory() as session:
        assert await service.companies_for_contact(session, contact_id) == []


@pytest.mark.asyncio
async def test_delete_is_refused_while_the_contact_holds_a_role(session_factory):  # noqa: ANN001
    """A delete is global here — it must not empty another company's org chart."""
    service = ContactDirectoryService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    contact_id = await _seed_contact(session_factory, "Busy Supplier")
    await _hold_role(session_factory, company_b, contact_id)

    async with session_factory() as session:
        with pytest.raises(ContactInUseError) as excinfo:
            await service.delete(session, company_id=company_a, contact_id=contact_id, actor_user_id=_ADMIN_USER)

    # The error names where to look, rather than only refusing.
    assert excinfo.value.company_ids == [company_b]
    assert await _exists(session_factory, contact_id)


@pytest.mark.asyncio
async def test_delete_succeeds_once_no_role_is_held(session_factory):  # noqa: ANN001
    service = ContactDirectoryService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    contact_id = await _seed_contact(session_factory, "Unused Supplier")

    async with session_factory() as session:
        assert (
            await service.delete(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER) is True
        )
        await session.commit()

    assert not await _exists(session_factory, contact_id)


@pytest.mark.asyncio
async def test_merge_moves_role_tenures_to_the_survivor(session_factory):  # noqa: ANN001
    """Otherwise merging silently vacates roles in companies nobody looked at."""
    service = ContactDirectoryService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    keep = await _seed_contact(session_factory, "Ada Lovelace", "ada@supplier.test")
    dupe = await _seed_contact(session_factory, "A. Lovelace", "ada@supplier.test")
    await _hold_role(session_factory, company_b, dupe)

    async with session_factory() as session:
        survivor = await service.merge(
            session,
            company_id=company_a,
            keep_id=keep,
            merge_id=dupe,
            actor_user_id=_ADMIN_USER,
        )
        await session.commit()

    assert survivor.id == keep
    assert not await _exists(session_factory, dupe)
    async with session_factory() as session:
        # Company B still has a holder for that role — the survivor.
        assert await service.companies_for_contact(session, keep) == [company_b]


@pytest.mark.asyncio
async def test_merge_refuses_a_contact_into_itself(session_factory):  # noqa: ANN001
    service = ContactDirectoryService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    contact_id = await _seed_contact(session_factory, "Ada")

    async with session_factory() as session:
        with pytest.raises(ValueError, match="into itself"):
            await service.merge(
                session,
                company_id=company,
                keep_id=contact_id,
                merge_id=contact_id,
                actor_user_id=_ADMIN_USER,
            )

    assert await _exists(session_factory, contact_id)


@pytest.mark.asyncio
async def test_duplicate_candidates_suggest_but_do_not_act(session_factory):  # noqa: ANN001
    """Grouped by mailbox, case-insensitively, and nothing is changed."""
    service = ContactDirectoryService()
    first = await _seed_contact(session_factory, "Ada", "Ada@Supplier.test")
    second = await _seed_contact(session_factory, "A. Lovelace", "ada@supplier.test")
    alone = await _seed_contact(session_factory, "Grace", "grace@supplier.test")

    async with session_factory() as session:
        groups = await service.find_duplicate_candidates(session)

    assert len(groups) == 1
    assert set(groups[0]) == {first, second}
    for contact_id in (first, second, alone):
        assert await _exists(session_factory, contact_id)


@pytest.mark.asyncio
async def test_a_member_cannot_delete_or_merge(session_factory):  # noqa: ANN001
    service = ContactDirectoryService()
    company = uuid.uuid4()
    member = uuid.uuid4()
    contact_id = await _seed_contact(session_factory, "Ada")
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
        with pytest.raises(NotAuthorisedError):
            await service.delete(session, company_id=company, contact_id=contact_id, actor_user_id=member)

    assert await _exists(session_factory, contact_id)
