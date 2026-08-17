# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Contacts shared across companies (#13998).

Owner decision: one row per human, shared, with visibility per company.

The two load-bearing tests are about **not losing data**:

``test_unlinking_one_company_leaves_the_contact_for_the_other`` — the PII must
survive while any company still links to it. An implementation that deleted the
contact on unlink passes every "is it gone from my list?" assertion while
destroying a record another company is actively using.

``test_the_last_unlink_removes_the_pii`` — the other half. Keeping the row after
the final link goes would leave orphaned personal data nobody can see or erase,
breaking #13969's deletion criterion.

Both directions are needed: a test for either one alone is satisfied by an
implementation that always deletes, or never does.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.contact import LLCContact
from llc.models.contact_company_link import LLCContactCompanyLink
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.services.authz import NotAuthorisedError
from llc.services.contact_sharing import ContactSharingService

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
        LLCContactCompanyLink.__table__,
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


async def _seed_contact(  # noqa: ANN001
    session_factory, company_id: uuid.UUID, name: str, email: str | None = None
) -> uuid.UUID:
    contact_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(LLCContact(id=contact_id, company_id=company_id, full_name=name, email=email))
        await session.commit()
    return contact_id


async def _contact_exists(session_factory, contact_id: uuid.UUID) -> bool:  # noqa: ANN001
    async with session_factory() as session:
        found = await session.execute(sa.select(LLCContact.id).where(LLCContact.id == contact_id))
        return found.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_one_contact_is_visible_from_two_companies(session_factory):  # noqa: ANN001
    """The decision itself: sharing, not duplication."""
    service = ContactSharingService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)
    contact_id = await _seed_contact(session_factory, company_a, "Ada Lovelace")

    async with session_factory() as session:
        for company in (company_a, company_b):
            await service.link(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        for company in (company_a, company_b):
            visible = await service.list_for_company(session, company)
            assert [c.id for c in visible] == [contact_id]
        # One row, two views — not two rows.
        total = await session.execute(sa.select(sa.func.count()).select_from(LLCContact))
        assert total.scalar_one() == 1


@pytest.mark.asyncio
async def test_a_company_never_sees_a_contact_it_has_no_link_to(session_factory):  # noqa: ANN001
    """Shared is not public — this is what keeps #13992's boundary intact."""
    service = ContactSharingService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)
    contact_id = await _seed_contact(session_factory, company_b, "Their Supplier")

    async with session_factory() as session:
        await service.link(session, company_id=company_b, contact_id=contact_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        assert await service.list_for_company(session, company_a) == []
        assert len(await service.list_for_company(session, company_b)) == 1


@pytest.mark.asyncio
async def test_unlinking_one_company_leaves_the_contact_for_the_other(session_factory):  # noqa: ANN001
    """Data-loss guard: one company's tidying must not destroy another's record."""
    service = ContactSharingService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)
    contact_id = await _seed_contact(session_factory, company_a, "Shared Supplier")

    async with session_factory() as session:
        for company in (company_a, company_b):
            await service.link(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.unlink(session, company_id=company_a, contact_id=contact_id, actor_user_id=_ADMIN_USER)
            is True
        )
        await session.commit()

    assert await _contact_exists(session_factory, contact_id), "shared PII was destroyed"
    async with session_factory() as session:
        assert await service.list_for_company(session, company_a) == []
        assert len(await service.list_for_company(session, company_b)) == 1


@pytest.mark.asyncio
async def test_the_last_unlink_removes_the_pii(session_factory):  # noqa: ANN001
    """The other half: no orphaned personal data nobody can see or erase."""
    service = ContactSharingService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    contact_id = await _seed_contact(session_factory, company, "Only Here")

    async with session_factory() as session:
        await service.link(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        await service.unlink(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    assert not await _contact_exists(session_factory, contact_id), "orphaned PII survived"


@pytest.mark.asyncio
async def test_linking_twice_reports_no_change(session_factory):  # noqa: ANN001
    service = ContactSharingService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    contact_id = await _seed_contact(session_factory, company, "Ada")

    async with session_factory() as session:
        assert await service.link(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER) is True
        await session.commit()

    async with session_factory() as session:
        assert (
            await service.link(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER) is False
        )
        await session.commit()

    async with session_factory() as session:
        assert len(await service.list_for_company(session, company)) == 1


@pytest.mark.asyncio
async def test_merge_folds_links_and_removes_the_duplicate(session_factory):  # noqa: ANN001
    """The owner's 'merge into a single' — explicit, on ids a caller named."""
    service = ContactSharingService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)
    keep = await _seed_contact(session_factory, company_a, "Ada Lovelace", "ada@supplier.test")
    dupe = await _seed_contact(session_factory, company_a, "A. Lovelace", "ada@supplier.test")

    async with session_factory() as session:
        for contact in (keep, dupe):
            await service.link(session, company_id=company_a, contact_id=contact, actor_user_id=_ADMIN_USER)
        # The duplicate is also used by another company — that link must move,
        # not vanish, or merging would silently remove company B's contact.
        await service.link(session, company_id=company_b, contact_id=dupe, actor_user_id=_ADMIN_USER)
        await session.commit()

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
    assert not await _contact_exists(session_factory, dupe)
    async with session_factory() as session:
        # Company B still sees a contact — the survivor, inheriting the link.
        assert [c.id for c in await service.list_for_company(session, company_b)] == [keep]
        assert [c.id for c in await service.list_for_company(session, company_a)] == [keep]


@pytest.mark.asyncio
async def test_merge_refuses_a_contact_the_company_cannot_see(session_factory):  # noqa: ANN001
    """Otherwise merge doubles as a way to discover and destroy another company's data."""
    service = ContactSharingService()
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    await _grant_admin(session_factory, company_a)
    await _grant_admin(session_factory, company_b)
    mine = await _seed_contact(session_factory, company_a, "Mine")
    theirs = await _seed_contact(session_factory, company_b, "Theirs")

    async with session_factory() as session:
        await service.link(session, company_id=company_a, contact_id=mine, actor_user_id=_ADMIN_USER)
        await service.link(session, company_id=company_b, contact_id=theirs, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="not linked to company"):
            await service.merge(
                session,
                company_id=company_a,
                keep_id=mine,
                merge_id=theirs,
                actor_user_id=_ADMIN_USER,
            )

    assert await _contact_exists(session_factory, theirs), "another company's contact was deleted"


@pytest.mark.asyncio
async def test_merge_refuses_to_merge_a_contact_into_itself(session_factory):  # noqa: ANN001
    service = ContactSharingService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    contact_id = await _seed_contact(session_factory, company, "Ada")

    async with session_factory() as session:
        await service.link(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        with pytest.raises(ValueError, match="into itself"):
            await service.merge(
                session,
                company_id=company,
                keep_id=contact_id,
                merge_id=contact_id,
                actor_user_id=_ADMIN_USER,
            )

    assert await _contact_exists(session_factory, contact_id)


@pytest.mark.asyncio
async def test_duplicate_candidates_suggest_but_do_not_act(session_factory):  # noqa: ANN001
    """Detection groups by mailbox, case-insensitively, and changes nothing."""
    service = ContactSharingService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    first = await _seed_contact(session_factory, company, "Ada", "Ada@Supplier.test")
    second = await _seed_contact(session_factory, company, "A. Lovelace", "ada@supplier.test")
    alone = await _seed_contact(session_factory, company, "Grace", "grace@supplier.test")

    async with session_factory() as session:
        for contact in (first, second, alone):
            await service.link(session, company_id=company, contact_id=contact, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        groups = await service.find_duplicate_candidates(session, company)

    assert len(groups) == 1
    assert set(groups[0]) == {first, second}
    # Suggesting must not merge: all three rows are still there.
    for contact in (first, second, alone):
        assert await _contact_exists(session_factory, contact)


@pytest.mark.asyncio
async def test_a_member_cannot_link_unlink_or_merge(session_factory):  # noqa: ANN001
    service = ContactSharingService()
    company = uuid.uuid4()
    await _grant_admin(session_factory, company)
    contact_id = await _seed_contact(session_factory, company, "Ada")
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
        await service.link(session, company_id=company, contact_id=contact_id, actor_user_id=_ADMIN_USER)
        await session.commit()

    async with session_factory() as session:
        for call in (
            service.link(session, company_id=company, contact_id=contact_id, actor_user_id=member),
            service.unlink(session, company_id=company, contact_id=contact_id, actor_user_id=member),
        ):
            with pytest.raises(NotAuthorisedError):
                await call

    assert await _contact_exists(session_factory, contact_id)
