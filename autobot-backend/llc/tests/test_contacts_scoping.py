# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Company-scoping regression test for LLCContact (#13969).

Companies inside one AutoBot installation are organisational units, not
customer-isolation tenants (umbrella #13935 owner correction) — so this is a
*correctness* test, not a security boundary test: asking for company A's
contacts must not return company B's, the same way asking for the marketing
company's contacts must never return the IT company's.

#13936's review (PR #13945) found exactly this predicate untested on the
query carrying user PII — every test there used a single company against a
fresh engine, so a dropped ``WHERE company_id`` filter stayed green while
leaking rows. Contacts are entirely PII by definition, so this needs its own
two-company case rather than repeating that gap.

Uses a minimal self-contained SQLite fixture (only User + LLCContact tables)
rather than the full ``_e2e_harness`` loop schema — LLCContact does not
participate in the e2e loop, and importing ``_e2e_harness`` only for its
already-registered compile shims (JSONB/PG_UUID -> SQLite) and its
column-scrubbing helpers keeps this file from duplicating that logic.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.contact import LLCContact
from llc.services.contact import ContactService

# Importing the harness registers the SQLite compile shims for
# postgresql.JSONB / postgresql.UUID (module-level side effect, safe to reuse
# without modifying the shared file).
from llc.tests import _e2e_harness as harness
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


async def _seed_contact(  # noqa: ANN001
    session_factory, company_id: uuid.UUID, *, full_name: str, email: str
) -> uuid.UUID:
    async with session_factory() as session:
        svc = ContactService()
        contact = await svc.create(session, company_id, full_name, email=email)
        await session.commit()
        return contact.id


@pytest.mark.asyncio
async def test_company_a_never_sees_company_bs_contacts(session_factory):  # noqa: ANN001
    """Row-level company scoping on ContactService.list_by_company.

    This pins the ``WHERE company_id`` predicate itself — dropping it leaves
    every other CRUD test in this suite green while returning every
    company's contacts from every company's list call.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()

    await _seed_contact(session_factory, company_a, full_name="Ada Lovelace", email="ada@supplier.test")
    await _seed_contact(session_factory, company_b, full_name="Brian Kernighan", email="brian@supplier.test")
    await _seed_contact(session_factory, company_b, full_name="Grace Hopper", email="grace@supplier.test")

    async with session_factory() as session:
        svc = ContactService()
        company_a_contacts = await svc.list_by_company(session, company_a)
        company_b_contacts = await svc.list_by_company(session, company_b)

    assert [c.full_name for c in company_a_contacts] == ["Ada Lovelace"]
    assert sorted(c.full_name for c in company_b_contacts) == ["Brian Kernighan", "Grace Hopper"]


@pytest.mark.asyncio
async def test_get_is_scoped_to_the_requesting_company(session_factory):  # noqa: ANN001
    """A contact fetched with the wrong company_id resolves to None, not the row.

    Complements the list-level test above: ``get()`` is the lookup the API's
    GET/PATCH/DELETE routes use, and has its own independent WHERE clause.
    """
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    contact_id = await _seed_contact(session_factory, company_a, full_name="Ada Lovelace", email="ada@supplier.test")

    async with session_factory() as session:
        svc = ContactService()
        own_company = await svc.get(session, company_a, contact_id)
        other_company = await svc.get(session, company_b, contact_id)

    assert own_company is not None
    assert own_company.full_name == "Ada Lovelace"
    assert other_company is None


@pytest.mark.asyncio
async def test_delete_scoped_to_company_never_deletes_another_companys_row(session_factory):  # noqa: ANN001
    """Deleting with the wrong company_id must not remove the row."""
    company_a = uuid.uuid4()
    company_b = uuid.uuid4()
    contact_id = await _seed_contact(session_factory, company_a, full_name="Ada Lovelace", email="ada@supplier.test")

    async with session_factory() as session:
        svc = ContactService()
        deleted = await svc.delete(session, company_b, contact_id)
        await session.commit()

    assert deleted is False

    async with session_factory() as session:
        svc = ContactService()
        still_there = await svc.get(session, company_a, contact_id)
    assert still_there is not None
