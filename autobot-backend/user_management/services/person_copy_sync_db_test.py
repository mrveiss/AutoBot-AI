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
from sqlalchemy.orm import Session

from tests.helpers._sqlite_test_engine import real_savepoint_session_factory
from user_management.models import User
from user_management.services import person_copy_sync as sync


@pytest_asyncio.fixture
async def factory() -> AsyncIterator:
    async for session_factory in real_savepoint_session_factory([User.__table__]):
        event.listen(Session, "after_flush", sync._remember_changes)
        event.listen(Session, "after_rollback", sync._forget_changes)
        event.listen(Session, "after_commit", sync._push_committed_changes)
        try:
            yield session_factory
        finally:
            event.remove(Session, "after_flush", sync._remember_changes)
            event.remove(Session, "after_rollback", sync._forget_changes)
            event.remove(Session, "after_commit", sync._push_committed_changes)


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
