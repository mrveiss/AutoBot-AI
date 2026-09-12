# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A user in one organisation never finds a user in another (#16279).

``GET /user-management/users/search`` runs ``UserService.list_users`` under the
caller's tenant context (``get_user_service``). These tests put real users for
two organisations into a real in-memory SQLite database and search through that
context, so the organisation filter is judged by what comes back, not by
inspecting the query it builds.
"""

import uuid
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from user_management.models import Role, User, UserRole
from user_management.models.base import Base
from user_management.services.base_service import TenantContext
from user_management.services.user_service import UserService

_SQLITE_URL = "sqlite+aiosqlite://"  # canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_ORG_A = uuid.UUID(int=0xA)
_ORG_B = uuid.UUID(int=0xB)


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


def _user(username: str, org_id: uuid.UUID) -> User:
    return User(
        id=uuid.uuid4(),
        email=f"{username}@example.com",
        username=username,
        password_hash=None,
        display_name=username,
        org_id=org_id,
        is_platform_admin=False,
        is_active=True,
        is_verified=False,
        mfa_enabled=False,
        preferences={},
    )


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator:
    """One user in org A (``alice_a``) and one in org B (``bob_b``)."""
    engine = create_async_engine(_SQLITE_URL)  # canonical: ignore py-adhoc-db-engine (test-local engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__, Role.__table__, UserRole.__table__])
    factory = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local session factory)
        bind=engine, expire_on_commit=False
    )
    try:
        async with factory() as session:
            session.add_all([_user("alice_a", _ORG_A), _user("bob_b", _ORG_B)])
            await session.commit()
        yield factory
    finally:
        await engine.dispose()


async def _search(factory, org_id: uuid.UUID, query: str) -> list:  # noqa: ANN001
    async with factory() as session:
        users, _ = await UserService(session, TenantContext(org_id=org_id)).list_users(search=query)
    return [user.username for user in users]


@pytest.mark.asyncio
async def test_a_user_in_org_a_gets_no_results_from_org_b(session_factory):
    assert await _search(session_factory, _ORG_A, "bob_b") == []


@pytest.mark.asyncio
async def test_a_user_in_org_b_gets_no_results_from_org_a(session_factory):
    assert await _search(session_factory, _ORG_B, "alice_a") == []


@pytest.mark.asyncio
async def test_a_query_matching_both_orgs_returns_only_the_callers_own(session_factory):
    """Both e-mail addresses match; only the caller's organisation comes back."""
    assert await _search(session_factory, _ORG_A, "example.com") == ["alice_a"]
    assert await _search(session_factory, _ORG_B, "example.com") == ["bob_b"]


@pytest.mark.asyncio
async def test_a_same_org_search_still_finds_the_user(session_factory):
    """The control: the empty results above come from the org filter, not an empty table."""
    assert await _search(session_factory, _ORG_A, "alice_a") == ["alice_a"]
