# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Concurrent duplicate user creation must return the sequential 409, not a 500 (#15772, #10200).

``UserService.create_user`` reads (``_check_duplicate_user``) then inserts. Two concurrent callers can both
pass the pre-check and both insert; the loser used to raise an uncaught ``IntegrityError`` -- a 500.

Every case here runs against a REAL SQLite database (``sqlite_test_engine``), never a mocked ``begin_nested``:
a mock cannot see ``session.add`` flushing OUTSIDE the SAVEPOINT, which killed the caller's transaction
(#10200). The pre-check is stubbed out only to reach the conflict branch, as in the race it is already past.
"""

from __future__ import annotations

import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select

from autobot_shared.user_management.user_service_conflict import insert_user_or_raise_duplicate
from autobot_shared.user_management.user_service_errors import DuplicateUserError
from user_management.models import User
from user_management.services.user_service import UserService
from user_management.sqlite_test_engine import real_savepoint_session_factory

# Deterministic ids. uuid5 rather than an all-digit literal: SQLite stores a UUID as 32 hex characters, and a
# string of digits only is coerced to a float by the column's numeric affinity.
_WINNER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "winner.user-service-conflict.test")
_LOSER_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "loser.user-service-conflict.test")
_NEXT_ID = uuid.uuid5(uuid.NAMESPACE_DNS, "next.user-service-conflict.test")


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator:
    async for factory in real_savepoint_session_factory([User.__table__]):
        yield factory


def _user(user_id: uuid.UUID, *, email: str, username: str) -> User:
    return User(
        id=user_id,
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


async def _seed_winning_user(session_factory, *, email: str, username: str) -> None:  # noqa: ANN001
    """Commit the row a concurrent request will lose against, bypassing the service entirely."""
    async with session_factory() as session:
        session.add(_user(_WINNER_ID, email=email, username=username))
        await session.commit()


def _finder(session):  # noqa: ANN001, ANN202
    async def _find(email: str, username: str):  # noqa: ANN202
        stmt = select(User).where((User.email == email.lower()) | (User.username == username.lower()))
        return (await session.execute(stmt)).scalars().first()

    return _find


async def _count(session) -> int:  # noqa: ANN001
    return (await session.execute(select(func.count()).select_from(User))).scalar()


@pytest.mark.asyncio
async def test_duplicate_insert_leaves_the_callers_transaction_usable(session_factory):  # noqa: ANN001
    """The #10200 regression: a lost insert rolls back only itself; the same session keeps working and commits."""
    async with session_factory() as session:
        first = _user(_WINNER_ID, email="a@example.com", username="alpha")
        await insert_user_or_raise_duplicate(session, first, "a@example.com", "alpha", _finder(session))

        dup = _user(_LOSER_ID, email="a@example.com", username="beta")
        with pytest.raises(DuplicateUserError) as exc_info:
            await insert_user_or_raise_duplicate(session, dup, "a@example.com", "beta", _finder(session))
        assert exc_info.value.field == "email"

        assert await _count(session) == 1  # the next query works; only the first user is pending
        nxt = _user(_NEXT_ID, email="c@example.com", username="gamma")
        await insert_user_or_raise_duplicate(session, nxt, "c@example.com", "gamma", _finder(session))
        await session.commit()

    async with session_factory() as session:
        rows = (await session.execute(select(User.id))).scalars().all()
        assert sorted(rows) == [_WINNER_ID, _NEXT_ID]  # the duplicate (_LOSER_ID) never persisted


@pytest.mark.asyncio
async def test_duplicate_username_names_the_username_field(session_factory):  # noqa: ANN001
    async with session_factory() as session:
        await insert_user_or_raise_duplicate(
            session,
            _user(_WINNER_ID, email="a@example.com", username="racer"),
            "a@example.com",
            "racer",
            _finder(session),
        )
        dup = _user(_LOSER_ID, email="b@example.com", username="racer")
        with pytest.raises(DuplicateUserError) as exc_info:
            await insert_user_or_raise_duplicate(session, dup, "b@example.com", "racer", _finder(session))
        assert exc_info.value.field == "username"


@pytest.mark.asyncio
async def test_conflict_with_no_row_on_reread_still_raises_duplicate(session_factory):  # noqa: ANN001
    """The defensive branch: the index rejected the insert but the re-read finds nothing -- fail closed."""
    await _seed_winning_user(session_factory, email="a@example.com", username="alpha")
    async with session_factory() as session:
        dup = _user(_LOSER_ID, email="a@example.com", username="beta")
        with pytest.raises(DuplicateUserError) as exc_info:
            await insert_user_or_raise_duplicate(session, dup, "a@example.com", "beta", AsyncMock(return_value=None))
        assert exc_info.value.field == "email"
        assert await _count(session) == 1


@pytest.mark.asyncio
async def test_create_user_race_after_precheck_returns_409_naming_email(session_factory):  # noqa: ANN001
    """Second insert of a duplicate email, after the pre-check has passed, through ``UserService.create_user``."""
    await _seed_winning_user(session_factory, email="race@example.com", username="winner")

    with patch.object(UserService, "_check_duplicate_user", AsyncMock(return_value=None)):
        async with session_factory() as session:
            with pytest.raises(DuplicateUserError) as exc_info:
                await UserService(session).create_user(email="race@example.com", username="loser")
            assert exc_info.value.field == "email"
            assert await _count(session) == 1  # the transaction is still usable and the loser never landed


@pytest.mark.asyncio
async def test_create_user_race_after_precheck_returns_409_naming_username(session_factory):  # noqa: ANN001
    await _seed_winning_user(session_factory, email="original@example.com", username="racer")

    with patch.object(UserService, "_check_duplicate_user", AsyncMock(return_value=None)):
        async with session_factory() as session:
            with pytest.raises(DuplicateUserError) as exc_info:
                await UserService(session).create_user(email="different@example.com", username="racer")
            assert exc_info.value.field == "username"
