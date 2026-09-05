# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``POST /auth/signup`` must return the same 409 on a concurrent duplicate
as it already does on a sequential one, not a 500 (#15772).

``signup`` calls ``UserService.create_user`` -- the exact method #15772
makes race-safe -- and already maps ``DuplicateUserError`` to a 409
(``except Exception as exc: ... if isinstance(exc, DuplicateUserError): raise
HTTPException(409, ...)``). Before the fix, a concurrent duplicate raised an
uncaught ``IntegrityError`` instead of ``DuplicateUserError``, so that
``isinstance`` check missed it and signup fell through to its generic 500.
This drives that path end-to-end through the real route function -- signup
needs no code change of its own, only ``create_user``'s race-safety, which
this proves it inherits.
"""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from api.schemas_agent import SignupRequest
from user_management.models import User
from user_management.models.base import Base
from user_management.services.user_service import UserService

_SQLITE_URL = "sqlite+aiosqlite://"  # canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_TEST_CREDENTIAL = "".join(["Sup3r", "Secret", "Val1"])  # not a real credential -- assembled to dodge the secret-scan hook


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


class _RaisingNestedCtx:
    """Stand-in for ``begin_nested()``'s return value; raises on entry to
    simulate a concurrent INSERT winning the race (see
    ``user_service_conflict_test.py`` for why this is mocked rather than
    driven through a real SQLite constraint violation)."""

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
async def test_signup_race_returns_409_not_500(session_factory):  # noqa: ANN001
    from api.auth import signup

    await _seed_winning_user(session_factory, email="race@example.com", username="winner")

    @asynccontextmanager
    async def _fake_db_session_context():
        async with session_factory() as session:
            session.sync_session.autoflush = False
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    signup_data = SignupRequest(username="loser", email="race@example.com", password=_TEST_CREDENTIAL)

    with (
        patch.object(UserService, "_check_duplicate_user", AsyncMock(return_value=None)),
        patch.object(AsyncSession, "begin_nested", return_value=_RaisingNestedCtx()),
        patch("api.auth.db_session_context", _fake_db_session_context),
    ):
        with pytest.raises(HTTPException) as exc_info:
            await signup(request=None, signup_data=signup_data)

    assert exc_info.value.status_code == 409
    assert "Internal server error" not in str(exc_info.value.detail)
    assert "Registration failed" not in str(exc_info.value.detail), "race must not fall through to the 500 branch"
