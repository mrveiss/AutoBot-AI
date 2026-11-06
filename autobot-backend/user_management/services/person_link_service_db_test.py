# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#10200: the startup link against a real database: all of it or none of it, and only once."""

import asyncio
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError

from user_management.models import AuditLog, Role, User
from user_management.models.person_link import PersonLink
from user_management.services import person_link_service as service
from user_management.sqlite_test_engine import real_savepoint_session_factory

_PERSON = service.SlmPerson(uuid.uuid4(), "root", "root@example.test", "Root", "$2b$kept-hash")


_TABLES = [User.__table__, Role.__table__, AuditLog.__table__, PersonLink.__table__]


@pytest_asyncio.fixture
async def factory() -> AsyncIterator:
    async for session_factory in real_savepoint_session_factory(_TABLES):
        yield session_factory


def _slm_and_db(factory, person=_PERSON):
    return (
        patch.object(service, "fetch_first_slm_admin", AsyncMock(return_value=person)),
        patch("user_management.database.get_async_session_factory", return_value=factory),
    )


async def _at_startup(factory, person=_PERSON) -> None:
    slm, db = _slm_and_db(factory, person)
    with slm, db:
        await service.link_first_slm_admin_at_startup()


async def _counts(factory) -> tuple[int, int]:
    async with factory() as session:
        users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        links = (await session.execute(select(func.count()).select_from(PersonLink))).scalar_one()
    return users, links


@pytest.mark.asyncio
async def test_the_link_persists_with_the_slm_id_and_the_kept_password(factory) -> None:
    await _at_startup(factory)
    async with factory() as session:
        user = (await session.execute(select(User))).scalar_one()
        link = (await session.execute(select(PersonLink))).scalar_one()
    assert user.password_hash == _PERSON.password_hash and user.is_platform_admin is True
    assert (link.slm_user_id, link.user_id) == (_PERSON.id, user.id)


@pytest.mark.asyncio
async def test_a_second_start_creates_nothing_new(factory) -> None:
    await _at_startup(factory)
    await _at_startup(factory)
    assert await _counts(factory) == (1, 1)


@pytest.mark.asyncio
async def test_a_failure_part_way_leaves_nothing_and_does_not_raise(factory) -> None:
    with patch.object(service.logger, "info", side_effect=RuntimeError("late failure")) as last_step:
        await _at_startup(factory)
    last_step.assert_called_once()  # the user and link were flushed, so the rollback removed them
    assert await _counts(factory) == (0, 0)


@pytest.mark.asyncio
async def test_a_person_is_linked_to_one_user_only(factory) -> None:
    await _at_startup(factory)
    async with factory() as session:
        session.add(PersonLink(slm_user_id=_PERSON.id, user_id=uuid.uuid4()))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_a_deleted_user_is_not_brought_back_on_the_next_start(factory) -> None:
    """The row outlives the user with no user on it, which SQLite here does by hand and the foreign key does for real."""
    assert next(iter(PersonLink.__table__.c.user_id.foreign_keys)).ondelete == "SET NULL"
    await _at_startup(factory)
    async with factory() as session, session.begin():
        link = (await session.execute(select(PersonLink))).scalar_one()
        user_id, link.user_id = link.user_id, None
        await session.flush()
        await session.execute(delete(User).where(User.id == user_id))
    await _at_startup(factory)
    assert await _counts(factory) == (0, 1)


@pytest_asyncio.fixture
async def file_factory(tmp_path) -> AsyncIterator:
    """A file database: the in-memory one shares a single connection, so it cannot race."""
    url = f"sqlite+aiosqlite:///{tmp_path / 'race.db'}"
    async for session_factory in real_savepoint_session_factory(_TABLES, url):
        yield session_factory


@pytest.mark.asyncio
async def test_an_admin_without_a_hash_is_reported_not_ok_and_nothing_is_written(factory) -> None:
    no_hash = service.SlmPerson(uuid.uuid4(), "root", "root@example.test", "Root", None)
    await _at_startup(factory, no_hash)
    assert service.last_link_status == service.LINK_NO_HASH
    assert await _counts(factory) == (0, 0)


def _checks_meet_before_either_inserts():
    """Wrap the last check before the insert so both starts pass it before either goes on to insert."""
    arrived, release = [], asyncio.Event()
    real = service._main_store_may_hold_them

    async def wrapped(session, person):
        held = await real(session, person)
        arrived.append(held)
        if len(arrived) >= 2:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=10)  # fails the test, not hangs it, if one never arrives
        return held

    return patch.object(service, "_main_store_may_hold_them", wrapped), arrived


@pytest.mark.asyncio
async def test_two_concurrent_starts_both_report_ok_and_leave_one_linked_user(file_factory) -> None:
    """Both starts pass every check before either inserts, so the loser must hit the conflict path, roll back whole and still report ok."""
    slm, db = _slm_and_db(file_factory)
    meet, arrived = _checks_meet_before_either_inserts()
    with slm, db, meet, patch.object(service.logger, "error") as errors, patch.object(service.logger, "info") as infos:
        statuses = await asyncio.gather(
            service.link_first_slm_admin_at_startup(), service.link_first_slm_admin_at_startup()
        )
    assert arrived == [False, False]  # both saw nobody and so both went on to insert
    assert sorted(statuses) == [service.LINK_OK, service.LINK_OK]  # a benign double start is not a failure
    errors.assert_not_called()
    lost = [c for c in infos.call_args_list if "lost the startup race" in c.args[0]]
    assert len(lost) == 1  # exactly one start took the conflict path, rolled back and re-read
    assert service.last_link_status == service.LINK_OK
    assert await _counts(file_factory) == (1, 1)
