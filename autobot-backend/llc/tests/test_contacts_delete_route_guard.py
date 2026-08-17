# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Router-level regression for the #14464 review's blocking finding.

``ContactDirectoryService.delete`` refuses to delete a contact who still holds
an open role in another company (``ContactInUseError``). Nine tests already
covered that, but every one of them called ``ContactDirectoryService``
directly — none went through HTTP. That is exactly why the suite stayed green
while the legacy route bypassed the guard: ``delete_contact``
(``DELETE /api/llc/contacts/{company_id}/{contact_id}``) called
``ContactService.delete``, filtered only on ``(id, company_id)`` and gated only
by ``assert_company_access`` — a bare tenant-membership comparison, not an
admin check — so it never consulted ``companies_for_contact`` at all.

Discrimination, stated explicitly:

  * Against the PR #14464 head BEFORE this fix, both tests below would FAIL:
    the legacy route would return 204 (contact hard-deleted) in each scenario,
    because ``assert_company_access`` is the only gate it ran and
    ``ContactService.delete`` never looks past ``(id, company_id)``.
  * AFTER this fix — ``delete_contact`` now delegates to the same
    ``_delete_via_directory`` helper as ``/{company_id}/directory/{contact_id}``
    — both tests PASS: the plain-member case is refused by
    ``require_company_admin`` (403) and the admin-with-a-role-held-elsewhere
    case is refused by ``ContactInUseError`` (409). In both cases the contact
    row still exists afterward.

Data originates from real rows (``LLCContact``, ``LLCRoleAssignment``,
``LLCCompanyMembership``) inserted directly through the session factory, and
the HTTP layer is real (``httpx.AsyncClient`` over ``FastAPI``'s ASGI app) —
not a mocked service call standing in for either. That is the "start where
the data originates" requirement: the test exercises the actual guard the
route runs, not a stand-in for it.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import httpx
import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from llc.models.contact import LLCContact
from llc.models.enums import MembershipRole, RoleHolderType
from llc.models.membership import LLCCompanyMembership
from llc.models.role_assignment import LLCRoleAssignment

# Registers the SQLite compile shims for postgresql.JSONB / postgresql.UUID —
# must import before any of the model classes above are used against SQLite.
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base

pytestmark = pytest.mark.asyncio


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


async def _seed_contact(session_factory, company_id: uuid.UUID, name: str) -> uuid.UUID:  # noqa: ANN001
    contact_id = uuid.uuid4()
    async with session_factory() as session:
        session.add(LLCContact(id=contact_id, company_id=company_id, full_name=name))
        await session.commit()
    return contact_id


async def _hold_role(session_factory, company_id: uuid.UUID, contact_id: uuid.UUID) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(
            LLCRoleAssignment(
                id=uuid.uuid4(),
                company_id=company_id,
                role_id=uuid.uuid4(),
                holder_type=RoleHolderType.CONTACT.value,
                holder_contact_id=contact_id,
            )
        )
        await session.commit()


async def _add_membership(session_factory, company_id: uuid.UUID, user_id: uuid.UUID, role: str) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company_id, user_id=user_id, role=role))
        await session.commit()


async def _contact_still_exists(session_factory, contact_id: uuid.UUID) -> bool:  # noqa: ANN001
    async with session_factory() as session:
        found = await session.execute(sa.select(LLCContact.id).where(LLCContact.id == contact_id))
        return found.scalar_one_or_none() is not None


def _client_for(session_factory, caller_company_id: uuid.UUID, actor_user_id: uuid.UUID) -> httpx.AsyncClient:
    """A real ASGI app mounting the real router, with only auth/session faked.

    ``get_async_session`` yields a session from the same in-memory database the
    seed helpers write to — so the route reads back exactly what was seeded,
    rather than a mock standing in for the database.
    """
    from fastapi import FastAPI

    from api.user_management.dependencies import get_current_user, require_org_context
    from llc.api.contacts import router as contacts_router
    from user_management.database import get_async_session
    from user_management.services import TenantContext

    app = FastAPI()
    app.include_router(contacts_router, prefix="/api/llc")

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_async_session] = _override_session
    app.dependency_overrides[get_current_user] = lambda: {"id": str(actor_user_id)}
    app.dependency_overrides[require_org_context] = lambda: TenantContext(
        org_id=caller_company_id, user_id=actor_user_id, is_platform_admin=False
    )
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_legacy_delete_route_refuses_when_the_contact_holds_a_role_elsewhere(session_factory):  # noqa: ANN001
    """The exact scenario from the review: an admin of the contact's own
    (legacy) company deletes them through the old route while they still hold
    an open role in a company the admin has no membership in at all.

    Pre-fix this returns 204 and the row is gone — ``ContactService.delete``
    only ever checked ``(id, company_id)`` and had no idea a role existed
    elsewhere. Post-fix it returns 409 via ``ContactInUseError`` and the
    ``LLCRoleAssignment.holder_contact_id`` in company B is never orphaned.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    admin_of_a = uuid.uuid4()
    contact_id = await _seed_contact(session_factory, company_a, "Busy Supplier")
    await _hold_role(session_factory, company_b, contact_id)
    await _add_membership(session_factory, company_a, admin_of_a, MembershipRole.ADMIN.value)

    async with _client_for(session_factory, company_a, admin_of_a) as client:
        resp = await client.delete(f"/api/llc/contacts/{company_a}/{contact_id}")

    assert resp.status_code == 409, f"expected the cross-company role guard to refuse this delete, got: {resp.text}"
    assert resp.json()["detail"]["company_ids"] == [str(company_b)]
    assert await _contact_still_exists(session_factory, contact_id)


async def test_legacy_delete_route_refuses_a_plain_member_regardless_of_roles(session_factory):  # noqa: ANN001
    """The review's concrete failure, verbatim: a *plain member* (not an
    admin) of the contact's own company calls the old route. Pre-fix,
    ``assert_company_access`` is a bare tenant-membership comparison — it does
    not check the membership *role* — so this also returned 204. Post-fix,
    ``require_company_admin`` (reused, not reinvented) refuses with 403 before
    the contact-in-use check is even reached.
    """
    company_a, company_b = uuid.uuid4(), uuid.uuid4()
    member_of_a = uuid.uuid4()
    contact_id = await _seed_contact(session_factory, company_a, "Busy Supplier")
    await _hold_role(session_factory, company_b, contact_id)
    await _add_membership(session_factory, company_a, member_of_a, MembershipRole.MEMBER.value)

    async with _client_for(session_factory, company_a, member_of_a) as client:
        resp = await client.delete(f"/api/llc/contacts/{company_a}/{contact_id}")

    assert resp.status_code == 403, f"expected the admin gate to refuse a plain member, got: {resp.text}"
    assert await _contact_still_exists(session_factory, contact_id)
