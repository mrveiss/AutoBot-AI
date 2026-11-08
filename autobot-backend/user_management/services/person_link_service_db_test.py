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

from autobot_shared.user_management import user_service_conflict as conflict
from autobot_shared.user_management.user_service_errors import DuplicateUserError
from llc.models.membership import LLCCompanyMembership
from tests.helpers._sqlite_test_engine import real_savepoint_session_factory
from user_management.models import AuditLog, Role, User
from user_management.models.person_link import PersonLink
from user_management.services import person_link_service as service

_PERSON = service.SlmPerson(uuid.uuid4(), "root", "root@example.test", "Root", "$2b$kept-hash")


_TABLES = [User.__table__, Role.__table__, AuditLog.__table__, PersonLink.__table__, LLCCompanyMembership.__table__]


@pytest.fixture(autouse=True)
def _no_copy_sync_listeners():
    """The startup also starts the SLM copy sync, whose commit listener would push in the background
    over this file's single in-memory connection; these tests are about the link only."""
    with patch("user_management.services.person_copy_sync.start_person_copy_sync"):
        yield


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
    """Hold both starts just after ``create_user``'s own duplicate pre-check, before either inserts.

    Both therefore pass every check (the person lookup and the user duplicate check) and the loser can
    only fail in the INSERT, inside the SAVEPOINT.
    """
    arrived, release = [], asyncio.Event()
    real = service.UserService._check_duplicate_user

    async def wrapped(self, *args, **kwargs):
        await real(self, *args, **kwargs)  # a duplicate here would raise: the pre-check must pass for both
        arrived.append(args)
        if len(arrived) >= 2:
            release.set()
        await asyncio.wait_for(release.wait(), timeout=10)  # fails the test, not hangs it, if one never arrives

    return patch.object(service.UserService, "_check_duplicate_user", wrapped), arrived


def _spy_on_savepoint_conflict():
    """Count the calls that turn the SAVEPOINT's IntegrityError into a ``DuplicateUserError``."""
    resolved = []
    real = conflict._resolve_conflict

    async def spy(*args, **kwargs):
        error = await real(*args, **kwargs)
        resolved.append(error)
        return error

    return patch.object(conflict, "_resolve_conflict", spy), resolved


@pytest.mark.asyncio
async def test_two_concurrent_starts_both_report_ok_and_leave_one_linked_user(file_factory) -> None:
    """Both starts pass every check before either inserts, so the loser must hit the conflict path, roll back whole and still report ok."""
    slm, db = _slm_and_db(file_factory)
    meet, arrived = _checks_meet_before_either_inserts()
    spy, resolved = _spy_on_savepoint_conflict()
    with (
        slm,
        db,
        meet,
        spy,
        patch.object(service.logger, "error") as errors,
        patch.object(service.logger, "info") as infos,
    ):
        statuses = await asyncio.gather(
            service.link_first_slm_admin_at_startup(), service.link_first_slm_admin_at_startup()
        )
    assert len(arrived) == 2  # both passed the duplicate pre-check, so both went on to insert
    assert len(resolved) == 1 and isinstance(resolved[0], DuplicateUserError)  # the SAVEPOINT conflict path ran
    assert sorted(statuses) == [service.LINK_OK, service.LINK_OK]  # a benign double start is not a failure
    errors.assert_not_called()
    lost = [c for c in infos.call_args_list if "lost the startup race" in c.args[0]]
    assert len(lost) == 1  # exactly one start took the conflict path, rolled back and re-read
    assert service.last_link_status == service.LINK_OK
    assert await _counts(file_factory) == (1, 1)


async def _rows(factory, model) -> int:
    async with factory() as session:
        return (await session.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_a_user_is_linked_to_one_person_only(factory) -> None:
    """Unique both ways (#21150): a second person for the same main-app user is refused by the schema."""
    await _at_startup(factory)
    async with factory() as session:
        linked_user = (await session.execute(select(PersonLink.user_id))).scalar_one()
        session.add(PersonLink(slm_user_id=uuid.UUID("5e1f0000-0000-4000-8000-00000000beef"), user_id=linked_user))
        with pytest.raises(IntegrityError):
            await session.flush()


@pytest.mark.asyncio
async def test_linking_leaves_existing_ids_in_both_stores_unchanged(factory) -> None:
    """The SLM person keeps its id on the link and an unrelated main-app user keeps theirs (#21150)."""
    bystander_id = uuid.UUID("b1b2c3d4-0000-4000-8000-00000000b001")
    async with factory() as session, session.begin():
        session.add(User(id=bystander_id, email="other@example.test", username="other", password_hash="x"))
    await _at_startup(factory)
    async with factory() as session:
        link = (await session.execute(select(PersonLink))).scalar_one()
        ids = set((await session.execute(select(User.id))).scalars())
    assert link.slm_user_id == _PERSON.id
    assert bystander_id in ids and link.user_id in ids and len(ids) == 2


@pytest.mark.asyncio
async def test_re_running_the_first_admin_link_keeps_one_user_one_link_and_no_new_membership(factory) -> None:
    """#21151: a fresh install has no company, so linking adds no membership; a second run adds nothing either."""
    await _at_startup(factory)
    async with factory() as session:
        first_link = (await session.execute(select(PersonLink))).scalar_one()
        first = (first_link.id, first_link.user_id)
    memberships = await _rows(factory, LLCCompanyMembership)
    await _at_startup(factory)
    async with factory() as session:
        second_link = (await session.execute(select(PersonLink))).scalar_one()
    assert (second_link.id, second_link.user_id) == first
    assert (await _rows(factory, User), await _rows(factory, PersonLink)) == (1, 1)
    assert await _rows(factory, LLCCompanyMembership) == memberships == 0
