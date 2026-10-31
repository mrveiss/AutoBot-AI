# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The members list tells the viewer their own company role and what they may grant (#20073).

Computed from the verified tenant context, so a client can only reflect it; the writes still refuse
what the caller may not do (#19654). Calls the real route function against an in-memory database.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.user_management.models.role import Role, UserRole
from llc.api.companies import list_members
from llc.models.membership import LLCCompanyMembership
from llc.services.membership_policy import grantable_roles
from llc.services.membership_service import MembershipService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.user import User
from user_management.services import TenantContext

# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"
_ALL = ["owner", "admin", "member", "guest", "lead"]
_NO_OWNER = ["admin", "member", "guest", "lead"]


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(_SQLITE_MEMORY_URL)  # canonical: ignore py-adhoc-db-engine (test-local engine)
    tables = [User.__table__, UserRole.__table__, Role.__table__, LLCCompanyMembership.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._rebind_enums_by_value(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )
    await engine.dispose()


@pytest.mark.parametrize(
    "role,platform_admin,expected",
    [
        ("owner", False, _ALL),
        ("admin", False, _NO_OWNER),
        ("member", False, []),
        ("guest", False, []),
        ("lead", False, []),
        (None, False, []),
        (None, True, _ALL),
        ("member", True, _ALL),
    ],
)
def test_grantable_roles_follow_the_policy(role, platform_admin, expected):
    assert grantable_roles(role, platform_admin=platform_admin) == expected


async def _list_as(session_factory, company_id, viewer_id, *, platform_admin=False):  # noqa: ANN001
    ctx = TenantContext(org_id=company_id, user_id=viewer_id, is_platform_admin=platform_admin)
    async with session_factory() as session:
        return await list_members(
            company_id=company_id, session=session, svc=MembershipService(), _current_user={}, ctx=ctx
        )


async def _seed(session_factory, company_id, roles: dict[uuid.UUID, str]) -> None:  # noqa: ANN001
    async with session_factory() as session:
        for uid, role in roles.items():
            session.add(User(id=uid, email=f"{uid}@example.test", username=f"u{uid.hex[:8]}", is_active=True))
            session.add(LLCCompanyMembership(id=uuid.uuid4(), company_id=company_id, user_id=uid, role=role))
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role,grantable", [("owner", _ALL), ("admin", _NO_OWNER), ("member", []), ("guest", []), ("lead", [])]
)
async def test_each_row_carries_the_callers_own_role_and_grantable_roles(
    session_factory, role, grantable
):  # noqa: ANN001
    company, viewer, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {viewer: role, other: "owner" if role != "owner" else "member"})

    rows = await _list_as(session_factory, company, viewer)

    assert len(rows) == 2
    assert {r["viewer_role"] for r in rows} == {role}
    assert all(r["viewer_grantable_roles"] == grantable for r in rows)


@pytest.mark.asyncio
async def test_a_platform_admin_outside_the_company_may_grant_everything(session_factory):  # noqa: ANN001
    company, member = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {member: "owner"})

    rows = await _list_as(session_factory, company, uuid.uuid4(), platform_admin=True)

    assert rows[0]["viewer_role"] is None
    assert rows[0]["viewer_grantable_roles"] == _ALL


@pytest.mark.asyncio
async def test_the_role_is_the_callers_not_another_members(session_factory):  # noqa: ANN001
    company, owner, plain = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company, {owner: "owner", plain: "member"})

    rows = await _list_as(session_factory, company, plain)

    assert {r["viewer_role"] for r in rows} == {"member"}
    assert {r["viewer_grantable_roles"] == [] for r in rows} == {True}
