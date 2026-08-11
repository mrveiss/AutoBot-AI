# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Company soft-delete must purge its contacts' PII (#13969 review M2).

``CompanyService.delete()`` soft-deletes the ``Organization`` row
(``deleted_at``), and every company listing filters ``deleted_at.is_(None)``
— so without this, a soft-deleted company's contacts would vanish from every
UI path while their name/email/phone/notes stayed at rest forever,
unreachable but not gone. That undercuts #13969's own "deletion removes its
PII" acceptance criterion at the level that matters (a company, not just a
single contact, going away).

Real-engine test (mirrors ``test_company_transition_greenlet_12309.py``'s
fixture shape) so the actual DELETE statement executes against a real table,
not a mock assertion about what *would* have been sent.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from llc.models.contact import LLCContact
from llc.services.company import CompanyService
from llc.services.contact import ContactService
from user_management.models.base import Base
from user_management.models.organization import Organization


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


async def _seed_company(session_factory, llc_status: str = "active") -> uuid.UUID:  # noqa: ANN001
    async with session_factory() as session:
        org = Organization(
            name="Acme Relations",
            slug=f"acme-{uuid.uuid4().hex[:8]}",
            settings={},
            llc_status=llc_status,
            issue_counter=0,
            budget_monthly_cents=0,
            spent_monthly_cents=0,
            require_approval_for_hires=False,
        )
        session.add(org)
        await session.commit()
        return org.id


@pytest.fixture()
async def session_factory() -> AsyncIterator:
    engine = create_async_engine("sqlite+aiosqlite://")  # canonical: ignore py-adhoc-db-engine (test-local engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[Organization.__table__, LLCContact.__table__])
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_company_delete_purges_its_contacts(session_factory):  # noqa: ANN001
    company_id = await _seed_company(session_factory)

    async with session_factory() as session:
        contact_svc = ContactService()
        contact = await contact_svc.create(session, company_id, "Ada Lovelace", email="ada@supplier.example.com")
        await session.commit()
        contact_id = contact.id

    async with session_factory() as session:
        company_svc = CompanyService(session=session)
        await company_svc.delete(company_id)
        await session.commit()

    async with session_factory() as session:
        row = (await session.execute(select(LLCContact).where(LLCContact.id == contact_id))).scalar_one_or_none()
    assert row is None, "company soft-delete must purge its contacts' PII, not just hide the company"


@pytest.mark.asyncio
async def test_company_delete_leaves_other_companies_contacts_untouched(session_factory):  # noqa: ANN001
    company_a = await _seed_company(session_factory)
    company_b = await _seed_company(session_factory)

    async with session_factory() as session:
        contact_svc = ContactService()
        contact_b = await contact_svc.create(session, company_b, "Brian Kernighan", email="brian@supplier.example.com")
        await session.commit()
        contact_b_id = contact_b.id

    async with session_factory() as session:
        company_svc = CompanyService(session=session)
        await company_svc.delete(company_a)
        await session.commit()

    async with session_factory() as session:
        row = (await session.execute(select(LLCContact).where(LLCContact.id == contact_b_id))).scalar_one_or_none()
    assert row is not None, "deleting company A must not purge company B's contacts"
