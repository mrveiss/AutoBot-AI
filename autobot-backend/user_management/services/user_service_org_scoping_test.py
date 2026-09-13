# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A user in org A must get no results from org B (#16279).

`api/user_management/users.py`'s search-for-sharing route used to build a
hand-rolled platform-admin `TenantContext` with no org, so it searched every
organisation. The fix scopes it to the caller's own org via
`apply_tenant_filter`. `api/user_management/user_management_gates_test.py`
already covers the route-level plumbing (a mocked service sees the right
context) and the compiled-query shape (the caller's org is a bound
parameter) -- neither seeds a second organisation's data, so neither proves
exclusion actually happens.

This drives `UserService.list_users` against a real in-memory SQLite session
with two orgs' worth of real rows, following the `session_factory` idiom
`user_management/services/user_service_conflict_test.py` already established
for this backend (real engine, only the tables the code path under test
needs, teardown via `engine.dispose()`).
"""

from __future__ import annotations

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

_SQLITE_URL = "sqlite+aiosqlite://"


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


#: list_users eager-loads User.user_roles -> UserRole.role (user_service.py's
#: list_users), so both tables must exist even though no test row uses them --
#: SQLite raises "no such table" on the eager-load SELECT otherwise, not a
#: silent empty result.
_TABLES = [User.__table__, UserRole.__table__, Role.__table__]


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator:
    engine = create_async_engine(_SQLITE_URL)  # canonical: ignore py-adhoc-db-engine (test-local, in-memory only)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=_TABLES)
    try:
        yield async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local, in-memory only)
            bind=engine, expire_on_commit=False
        )
    finally:
        await engine.dispose()


async def _seed_user(session_factory, *, org_id: uuid.UUID, email: str, username: str) -> None:  # noqa: ANN001
    """Commit a real row directly, bypassing the service -- this is setup, not the thing under test."""
    async with session_factory() as session:
        session.add(
            User(
                id=uuid.uuid4(),
                email=email,
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
        )
        await session.commit()


@pytest.mark.asyncio
async def test_a_user_in_org_a_finds_no_results_from_org_b(session_factory):  # noqa: ANN001
    """The exclusion property #16279's fix exists for, proven against real rows."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    # Same domain in both emails: a query with no org filter would match both,
    # so a passing assertion here is evidence of scoping, not of a search term
    # that only ever matched one row by accident.
    await _seed_user(session_factory, org_id=org_a, email="alice@shared-domain.example", username="alice")
    await _seed_user(session_factory, org_id=org_b, email="bob@shared-domain.example", username="bob")

    async with session_factory() as session:
        service = UserService(session, TenantContext(org_id=org_a, user_id=uuid.uuid4()))
        users, total = await service.list_users(search="shared-domain.example")

    assert total == 1, f"org A's search must not count org B's row, got total={total}"
    assert [u.username for u in users] == ["alice"], f"org A's search returned {[u.username for u in users]}"


@pytest.mark.asyncio
async def test_the_other_orgs_caller_symmetrically_finds_only_their_own_row(session_factory):  # noqa: ANN001
    """The contrast case: org B's caller sees bob, never alice -- exclusion is not one-directional."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    await _seed_user(session_factory, org_id=org_a, email="alice@shared-domain.example", username="alice")
    await _seed_user(session_factory, org_id=org_b, email="bob@shared-domain.example", username="bob")

    async with session_factory() as session:
        service = UserService(session, TenantContext(org_id=org_b, user_id=uuid.uuid4()))
        users, total = await service.list_users(search="shared-domain.example")

    assert total == 1, f"org B's search must not count org A's row, got total={total}"
    assert [u.username for u in users] == ["bob"], f"org B's search returned {[u.username for u in users]}"


@pytest.mark.asyncio
async def test_a_caller_with_no_org_context_sees_every_organisation(session_factory):  # noqa: ANN001
    """The pre-#16279 shape, still reachable at the service layer: no org means no filter.

    Proves the exclusion above comes from `TenantContext.org_id` being set,
    not from some unrelated difference between the two seeded rows -- and
    pins exactly the behaviour the route no longer allows an anonymous caller
    to trigger (`require_org_context` demands an org before this context could
    ever be built from a real request).
    """
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    await _seed_user(session_factory, org_id=org_a, email="alice@shared-domain.example", username="alice")
    await _seed_user(session_factory, org_id=org_b, email="bob@shared-domain.example", username="bob")

    async with session_factory() as session:
        service = UserService(session, TenantContext())
        users, total = await service.list_users(search="shared-domain.example")

    assert total == 2, f"an org-less context must see both rows, got total={total}"
    assert {u.username for u in users} == {"alice", "bob"}
