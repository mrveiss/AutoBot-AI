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
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from user_management.models import AuditLog, Role, User
from user_management.models.base import Base
from user_management.models.person_link import PersonLink
from user_management.services import person_link_service as service

_SQLITE_URL = "sqlite+aiosqlite://"  # canonical: ignore py-adhoc-db-engine (test-local engine, in-memory only)
_PERSON = service.SlmPerson(uuid.uuid4(), "root", "root@example.test", "Root", "$2b$kept-hash")


@compiles(JSONB, "sqlite")
def _compile_jsonb_as_json_on_sqlite(element, compiler, **kw):  # noqa: ANN001
    return "JSON"


@pytest_asyncio.fixture
async def factory() -> AsyncIterator:
    engine = create_async_engine(_SQLITE_URL)  # canonical: ignore py-adhoc-db-engine (test-local, in-memory)
    async with engine.begin() as conn:
        tables = [User.__table__, Role.__table__, AuditLog.__table__, PersonLink.__table__]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine (as above)
    finally:
        await engine.dispose()


async def _at_startup(factory, person=_PERSON) -> None:
    with (
        patch.object(service, "fetch_first_slm_admin", AsyncMock(return_value=person)),
        patch("user_management.database.get_async_session_factory", return_value=factory),
    ):
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
    engine = create_async_engine(url)  # canonical: ignore py-adhoc-db-engine (test-local, tmp file)
    async with engine.begin() as conn:
        tables = [User.__table__, Role.__table__, AuditLog.__table__, PersonLink.__table__]
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    try:
        yield async_sessionmaker(bind=engine, expire_on_commit=False)  # canonical: ignore py-adhoc-db-engine (as above)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_two_concurrent_starts_leave_one_linked_user(file_factory) -> None:
    """Two workers can both pass the checks; the loser must fail whole and leave no partial user."""
    await asyncio.gather(_at_startup(file_factory), _at_startup(file_factory))
    assert await _counts(file_factory) == (1, 1)
