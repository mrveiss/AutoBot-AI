# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: a real session's commit triggers the push, for the watched fields only."""

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session

from user_management.models import User
from user_management.models.base import Base
from user_management.services import person_copy_sync as sync

_SQLITE_URL = "sqlite+aiosqlite://"  # canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


@pytest_asyncio.fixture
async def factory() -> AsyncIterator:
    engine = create_async_engine(_SQLITE_URL)  # canonical: ignore py-adhoc-db-engine (test-local, in-memory)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all, tables=[User.__table__])
    event.listen(Session, "after_flush", sync._remember_changes)
    event.listen(Session, "after_rollback", sync._forget_changes)
    event.listen(Session, "after_commit", sync._push_committed_changes)
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine (as above)
    finally:
        event.remove(Session, "after_flush", sync._remember_changes)
        event.remove(Session, "after_rollback", sync._forget_changes)
        event.remove(Session, "after_commit", sync._push_committed_changes)
        await engine.dispose()


async def _user(factory) -> User:
    user = User(id=uuid.uuid4(), email="a@example.test", username="a", password_hash="old", display_name="A")
    async with factory() as session:
        session.add(user)
        await session.commit()
    return user


async def _change(factory, user_id, field, value, *, commit=True) -> AsyncMock:
    push = AsyncMock()
    with patch.object(sync, "_push_in_own_session", push):
        async with factory() as session:
            setattr(await session.get(User, user_id), field, value)
            await session.flush()
            await (session.commit() if commit else session.rollback())
    return push


@pytest.mark.asyncio
@pytest.mark.parametrize("field, value", [("password_hash", "new"), ("is_active", False)])
async def test_a_committed_change_pushes_that_person(factory, field, value) -> None:
    user = await _user(factory)
    push = await _change(factory, user.id, field, value)
    push.assert_called_once_with({user.id})


@pytest.mark.asyncio
async def test_another_field_pushes_nothing(factory) -> None:
    user = await _user(factory)
    (await _change(factory, user.id, "display_name", "B")).assert_not_called()


@pytest.mark.asyncio
async def test_a_rollback_pushes_nothing(factory) -> None:
    user = await _user(factory)
    (await _change(factory, user.id, "is_active", False, commit=False)).assert_not_called()
