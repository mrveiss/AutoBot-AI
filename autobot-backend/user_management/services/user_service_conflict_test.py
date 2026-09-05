# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Concurrent duplicate user creation must return the sequential 409, not a 500 (#15772).

``UserService.create_user`` reads (``_check_duplicate_user``) then inserts. Two
concurrent callers can both pass the pre-check SELECT and both attempt the
insert; the loser used to hit the unique index and raise an uncaught
``IntegrityError`` -- a 500, contradicting the 409 a *sequential* duplicate
already returns (#15736, #15752).

These tests drive the CONFLICT path directly rather than the pre-check: a
winning row is committed first, ``_check_duplicate_user`` is stubbed out so
the pre-check cannot itself catch the duplicate (simulating the race window
where it has already passed), and ``AsyncSession.begin_nested`` is patched to
raise ``IntegrityError`` synchronously -- the same idiom
``test_budget_provision.py::test_provision_budget_race_returns_existing``
uses for the identical reason: the SQLite asyncio driver does not implement
SAVEPOINT well enough for the ORM to recover a *real* constraint violation
without also invalidating unrelated pending work in the same transaction
(SQLAlchemy's own ``aiosqlite_serializable`` note). Patching the entry point
keeps the assertions about what the codebase's own SAVEPOINT idiom is
*for* -- translating the collision, not poisoning the session -- provable
on both dialects instead of exercising a known driver gap.

Asserting only the sequential 409 would pass against the defect this issue
fixes -- these assert the race path too.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from user_management.models import User
from user_management.models.base import Base
from user_management.services.user_service import DuplicateUserError, UserService

_SQLITE_URL = "sqlite+aiosqlite://"  # canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


class _RaisingNestedCtx:
    """Stand-in for the ``AsyncSessionTransaction`` ``begin_nested()`` returns,
    raising on entry to simulate a concurrent INSERT winning the race."""

    async def __aenter__(self):  # noqa: ANN204
        raise IntegrityError("duplicate key", None, None)

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN204
        return False


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator:
    engine = create_async_engine(_SQLITE_URL)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        await engine.dispose()


async def _seed_winning_user(session_factory, *, email: str, username: str) -> None:  # noqa: ANN001
    """Commit the row a concurrent request will lose against, bypassing the
    service entirely so no audit-log table is required for this setup step."""
    async with session_factory() as session:
        session.add(
            User(
                id=uuid.uuid4(),
                email=email.lower(),
                username=username.lower(),
                password_hash=None,
                display_name=username,
                org_id=None,
                is_platform_admin=False,
                is_active=True,
                is_verified=False,
                mfa_enabled=False,
                preferences={},
            )
        )
        await session.commit()


@pytest.mark.asyncio
async def test_race_after_precheck_passes_returns_409_naming_email(session_factory):  # noqa: ANN001
    """Second insert of a duplicate email, after the pre-check has passed."""
    await _seed_winning_user(session_factory, email="race@example.com", username="winner")

    with (
        patch.object(UserService, "_check_duplicate_user", AsyncMock(return_value=None)),
        patch.object(AsyncSession, "begin_nested", return_value=_RaisingNestedCtx()),
    ):
        async with session_factory() as session:
            session.sync_session.autoflush = False  # see module docstring
            service = UserService(session)
            with pytest.raises(DuplicateUserError) as exc_info:
                await service.create_user(email="race@example.com", username="loser")

            assert exc_info.value.field == "email"

            # The caller's transaction must still be usable: a plain query
            # on the same session works, and the losing insert never landed.
            count = (await session.execute(select(func.count()).select_from(User))).scalar()
            assert count == 1


@pytest.mark.asyncio
async def test_race_after_precheck_passes_returns_409_naming_username(session_factory):  # noqa: ANN001
    """Second insert of a duplicate username, after the pre-check has passed."""
    await _seed_winning_user(session_factory, email="original@example.com", username="racer")

    with (
        patch.object(UserService, "_check_duplicate_user", AsyncMock(return_value=None)),
        patch.object(AsyncSession, "begin_nested", return_value=_RaisingNestedCtx()),
    ):
        async with session_factory() as session:
            session.sync_session.autoflush = False  # see module docstring
            service = UserService(session)
            with pytest.raises(DuplicateUserError) as exc_info:
                await service.create_user(email="different@example.com", username="racer")

            assert exc_info.value.field == "username"
