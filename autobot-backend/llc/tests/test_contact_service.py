# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ContactService CRUD (#13969), including PII deletion.

Row-level company scoping has its own dedicated file
(``test_contacts_scoping.py``) with the two-company regression case; this
file covers ordinary CRUD correctness and the deletion-removes-PII
acceptance criterion.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.contact import LLCContact
from llc.services.contact import ContactService
from llc.tests import _e2e_harness as harness  # registers SQLite compile shims
from user_management.models.base import Base

# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def engine() -> AsyncIterator:
    eng = create_async_engine(_SQLITE_MEMORY_URL)
    tables = [LLCContact.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with eng.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):  # noqa: ANN001, ANN201
    # canonical: ignore py-adhoc-db-engine (test-local session factory)
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


@pytest.mark.asyncio
async def test_create_and_get_round_trip(session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    async with session_factory() as session:
        svc = ContactService()
        created = await svc.create(
            session,
            company_id,
            "Ada Lovelace",
            email="ada@supplier.test",
            phone="+1-555-0100",
            role_title="Accounts Payable, Acme Supplies",
            notes="Prefers email over phone",
        )
        await session.commit()

    async with session_factory() as session:
        svc = ContactService()
        fetched = await svc.get(session, company_id, created.id)

    assert fetched is not None
    assert fetched.full_name == "Ada Lovelace"
    assert fetched.email == "ada@supplier.test"
    assert fetched.phone == "+1-555-0100"
    assert fetched.role_title == "Accounts Payable, Acme Supplies"


@pytest.mark.asyncio
async def test_create_requires_only_full_name(session_factory):  # noqa: ANN001
    """email/phone/role_title/notes are all optional."""
    company_id = uuid.uuid4()
    async with session_factory() as session:
        svc = ContactService()
        created = await svc.create(session, company_id, "Anonymous Contact")
        await session.commit()

    assert created.email is None
    assert created.phone is None


@pytest.mark.asyncio
async def test_update_changes_only_provided_fields(session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    async with session_factory() as session:
        svc = ContactService()
        created = await svc.create(session, company_id, "Ada Lovelace", email="ada@supplier.test")
        await session.commit()
        contact_id = created.id

    async with session_factory() as session:
        svc = ContactService()
        updated = await svc.update(session, company_id, contact_id, phone="+1-555-0199")
        await session.commit()

    assert updated is not None
    assert updated.phone == "+1-555-0199"
    assert updated.email == "ada@supplier.test"  # untouched


@pytest.mark.asyncio
async def test_update_missing_contact_returns_none(session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    async with session_factory() as session:
        svc = ContactService()
        result = await svc.update(session, company_id, uuid.uuid4(), full_name="Nobody")
    assert result is None


@pytest.mark.asyncio
async def test_delete_removes_the_row_and_its_pii_entirely(session_factory):  # noqa: ANN001
    """The core revocability acceptance criterion: after delete, the PII is gone
    at rest — not soft-flagged, not queryable by any path, including a bare
    SELECT against the table with no company filter at all."""
    company_id = uuid.uuid4()
    async with session_factory() as session:
        svc = ContactService()
        created = await svc.create(
            session,
            company_id,
            "Ada Lovelace",
            email="ada@supplier.test",
            phone="+1-555-0100",
            notes="sensitive process notes",
        )
        await session.commit()
        contact_id = created.id

    async with session_factory() as session:
        svc = ContactService()
        deleted = await svc.delete(session, company_id, contact_id)
        await session.commit()
    assert deleted is True

    async with session_factory() as session:
        # Bare SELECT by id, no company filter, no service layer at all — proves
        # the row (and therefore its PII) is gone, not merely excluded by scope.
        result = await session.execute(select(LLCContact).where(LLCContact.id == contact_id))
        row = result.scalar_one_or_none()
    assert row is None


@pytest.mark.asyncio
async def test_delete_missing_contact_returns_false(session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    async with session_factory() as session:
        svc = ContactService()
        deleted = await svc.delete(session, company_id, uuid.uuid4())
    assert deleted is False


@pytest.mark.asyncio
async def test_list_by_company_orders_by_full_name(session_factory):  # noqa: ANN001
    company_id = uuid.uuid4()
    async with session_factory() as session:
        svc = ContactService()
        await svc.create(session, company_id, "Zeta Vendor")
        await svc.create(session, company_id, "Alpha Vendor")
        await session.commit()

    async with session_factory() as session:
        svc = ContactService()
        contacts = await svc.list_by_company(session, company_id)

    assert [c.full_name for c in contacts] == ["Alpha Vendor", "Zeta Vendor"]
