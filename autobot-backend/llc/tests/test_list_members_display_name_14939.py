# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`list_members` owns the whole display-name ladder (#14939).

The two LLC endpoints disagreed about who owns the last rung: `_compose_human_nodes`
resolved an orphaned membership (user row gone) to its user id server-side, while
`list_members` returned `display_name: null` and left every client to invent a
label -- which is why the frontend grew a `|| member.user_id` rung in two places.
The server now resolves it through `resolve_display_name`, so the value is never
null and the clients render it as given.

Calls the real route function against an in-memory database, so the SQL-side
`full_name` rule (`coalesce(nullif(display_name, ''), username)`) is exercised too.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.user_management.models.role import Role, UserRole
from llc.api.companies import list_members
from llc.models.enums import MembershipRole
from llc.models.membership import LLCCompanyMembership
from llc.services.membership_service import MembershipService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base
from user_management.models.user import User
from user_management.services import TenantContext

# canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_SQLITE_MEMORY_URL = "sqlite+aiosqlite:///:memory:"


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


async def _seed(
    session_factory, company_id: uuid.UUID, users: list[User], member_ids: list[uuid.UUID]
) -> None:  # noqa: ANN001
    async with session_factory() as session:
        session.add_all(users)
        for user_id in member_ids:
            session.add(
                LLCCompanyMembership(
                    id=uuid.uuid4(), company_id=company_id, user_id=user_id, role=MembershipRole.ADMIN.value
                )
            )
        await session.commit()


async def _names(session_factory, company_id: uuid.UUID) -> dict[str, str | None]:  # noqa: ANN001
    """user_id -> display_name, as the real endpoint returns them."""
    ctx = TenantContext(org_id=company_id, user_id=uuid.uuid4(), is_platform_admin=False)
    async with session_factory() as session:
        rows = await list_members(
            company_id=company_id, session=session, svc=MembershipService(), _current_user={}, ctx=ctx
        )
    return {row["user_id"]: row["display_name"] for row in rows}


def _user(username: str, display_name: str | None) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{username}@example.test",
        username=username,
        display_name=display_name,
        is_active=True,
    )


@pytest.mark.asyncio
async def test_an_orphaned_membership_renders_its_user_id_not_null(session_factory):  # noqa: ANN001
    """The #14939 reproduction: the user row is gone, so there is no name to select."""
    company_id, orphan_id = uuid.uuid4(), uuid.uuid4()
    await _seed(session_factory, company_id, users=[], member_ids=[orphan_id])

    assert await _names(session_factory, company_id) == {str(orphan_id): str(orphan_id)}


@pytest.mark.asyncio
async def test_a_present_user_still_resolves_display_name_then_username(session_factory):  # noqa: ANN001
    """The rungs above the new one are unchanged -- and an empty display name counts as absent."""
    company_id = uuid.uuid4()
    named, unnamed = _user("ada", "Ada Lovelace"), _user("grace", "")
    await _seed(session_factory, company_id, users=[named, unnamed], member_ids=[named.id, unnamed.id])

    assert await _names(session_factory, company_id) == {str(named.id): "Ada Lovelace", str(unnamed.id): "grace"}


@pytest.mark.asyncio
async def test_no_member_row_ever_carries_a_null_display_name(session_factory):  # noqa: ANN001
    """The invariant the frontend now relies on: it renders the value without a fallback."""
    company_id, orphan_id = uuid.uuid4(), uuid.uuid4()
    present = _user("linus", None)
    await _seed(session_factory, company_id, users=[present], member_ids=[present.id, orphan_id])

    names = await _names(session_factory, company_id)
    assert len(names) == 2
    assert all(name for name in names.values()), names
