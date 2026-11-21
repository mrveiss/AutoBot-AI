# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Two concurrent demotions of the last two admins: one succeeds, one is refused 409 (#21018).

The guard locks the active-admin rows (and the target) in one id-ordered ``SELECT ... FOR UPDATE`` before
any lock on the target alone, so the two requests queue on the same rows instead of each holding one and
waiting for the other. SQLite has no row locks and a mocked session no deadlock detector, so this runs on
the real Postgres of the migration gate (``AUTOBOT_MIGRATION_TEST_ADMIN_URL``). The wait is proved by a
waiting lock in ``pg_stat_activity``, not by a sleep.
"""

import asyncio
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.db_session import async_session_scope
from autobot_shared.user_management import last_platform_admin, password_epoch
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.last_platform_admin import (
    LAST_PLATFORM_ADMIN_CODE,
    LAST_PLATFORM_ADMIN_RETRY_CODE,
    LastPlatformAdminError,
    LastPlatformAdminRetry,
    ensure_not_last_platform_admin,
    refuse_last_platform_admin,
)
from tests.migrations.conftest import create_all_schema, requires_postgres

pytestmark = [pytest.mark.asyncio, pytest.mark.migration_gate, requires_postgres]

#: Upper bound on polling ``pg_stat_activity`` for the waiting backend (a safety net, not the proof).
_POLL_ATTEMPTS = 200
_POLL_INTERVAL_SECONDS = 0.05
_RACE_ROUNDS = 5


@pytest.fixture(autouse=True)
def _epoch_store():
    """An in-memory epoch store: the revocation marker is not what is under test, and Redis is not here."""
    epochs: dict = {}

    async def get_epoch(subject):
        return epochs.get(subject)

    async def set_epoch(subject, *, now=None):
        epochs[subject] = now
        return now

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    yield
    password_epoch.reset_epoch_store()


@pytest.fixture
async def engine(fresh_db_url):
    await create_all_schema(fresh_db_url)
    engine = create_async_engine(fresh_db_url)
    yield engine
    await engine.dispose()


def _service(session):  # noqa: ANN001
    from autobot_shared.user_management.user_service import UserService
    from user_management.models import User  # the concrete mapped model; ``UserCore`` is abstract

    class _Bound(UserService):
        user_model = User

    return _Bound(session, TenantContext())


async def _create(engine, name: str, is_admin: bool) -> uuid.UUID:
    from user_management.models import User

    async with AsyncSession(engine) as session:
        user = User(email=f"{name}@example.test", username=name, is_platform_admin=is_admin)
        session.add(user)
        await session.flush()
        user_id = user.id
        await session.commit()
        return user_id


async def _demote(maker, user_id: uuid.UUID) -> int:
    """One PUT /admin as the route runs it: the change, the commit, or the committed 409. Any other error escapes."""
    async with async_session_scope(maker) as session:
        service = _service(session)
        try:
            await service.set_platform_admin(user_id, False)
        except LastPlatformAdminError as exc:
            return (await refuse_last_platform_admin(session, exc)).status_code
        await session.commit()
        return 200


async def _wait_until_blocked(maker, task):  # noqa: ANN001
    """Return once a backend of this database waits on a lock; fail if the task ends first."""
    for _ in range(_POLL_ATTEMPTS):
        async with maker() as probe:
            waiting = (
                await probe.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND wait_event_type = 'Lock'"
                    )
                )
            ).scalar_one()
        if waiting:
            return
        assert not task.done(), "the statement finished without ever waiting for the row lock"
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
    pytest.fail("no backend ever waited for the row lock")


async def _active_admins(engine) -> list[uuid.UUID]:
    from user_management.models import User

    async with AsyncSession(engine) as session:
        query = select(User.id).where(User.is_platform_admin.is_(True), User.is_active.is_(True))
        return list((await session.execute(query)).scalars().all())


async def test_a_demotion_in_flight_makes_the_other_wait_then_refuse(engine):  # noqa: ANN001
    first = await _create(engine, "a", True)
    second = await _create(engine, "b", True)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_scope(maker) as holder:
        await _service(holder).set_platform_admin(first, False)  # holds the admin rows, uncommitted
        other = asyncio.create_task(_demote(maker, second))
        await _wait_until_blocked(maker, other)
        await holder.commit()
        assert await asyncio.wait_for(other, timeout=10) == 409

    assert await _active_admins(engine) == [second]


async def test_concurrent_demotions_of_the_last_two_admins_never_deadlock(engine, monkeypatch):  # noqa: ANN001
    """Both requests are held at the guard's door until both have arrived, so whatever lock a request took
    BEFORE the guard is held while it waits for the other: the interleaving that deadlocks a target-first order."""
    from autobot_shared.user_management.user_service_lifecycle import UserLifecycleMixin

    real_guard = UserLifecycleMixin._guard_last_admin
    barrier = asyncio.Barrier(2)
    arrived: set = set()

    async def guard_after_both_arrive(self, user_id, action, attempt):  # noqa: ANN001
        if id(self) not in arrived:
            arrived.add(id(self))
            await asyncio.wait_for(barrier.wait(), timeout=10)
        return await real_guard(self, user_id, action, attempt)

    monkeypatch.setattr(UserLifecycleMixin, "_guard_last_admin", guard_after_both_arrive)
    database_errors: list = []  # the deadlock mapping would turn a deadlock into a 409: it must not be needed
    real_classify = last_platform_admin._is_serialization_failure
    monkeypatch.setattr(
        last_platform_admin, "_is_serialization_failure", lambda exc: database_errors.append(exc) or real_classify(exc)
    )
    maker = async_sessionmaker(engine, expire_on_commit=False)
    for round_no in range(_RACE_ROUNDS):
        arrived.clear()
        ids = [await _create(engine, f"a{round_no}", True), await _create(engine, f"b{round_no}", True)]
        async with engine.begin() as conn:  # earlier rounds' survivors are not part of this round's two
            await conn.execute(
                text("UPDATE users SET is_platform_admin = false WHERE NOT (id = ANY(:ids))"), {"ids": ids}
            )
        outcomes = await asyncio.gather(_demote(maker, ids[0]), _demote(maker, ids[1]))
        assert sorted(outcomes) == [200, 409], outcomes
        assert len(await _active_admins(engine)) == 1
        assert database_errors == [], "a database deadlock or serialization failure was mapped to the 409"


async def test_a_forced_deadlock_is_a_503_retry_never_the_409_refusal(engine):  # noqa: ANN001
    """Each session already holds one admin row (the order the guard prevents) and then runs the guard: Postgres
    kills one of them with 40P01. That one is answered as a retry (503 + Retry-After), the other is judged
    normally, and nothing is refused."""
    from user_management.models import User

    first, second = await _create(engine, "a", True), await _create(engine, "b", True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as one, maker() as two:
        for session, user_id in ((one, first), (two, second)):
            await session.execute(select(User.id).where(User.id == user_id).with_for_update())

        async def guard(session, user_id):  # noqa: ANN001
            try:
                await asyncio.wait_for(ensure_not_last_platform_admin(session, User, user_id), timeout=20)
            except LastPlatformAdminRetry as exc:
                return await refuse_last_platform_admin(session, exc)
            await session.rollback()
            return None

        answers = await asyncio.gather(guard(one, first), guard(two, second))
    retries = [answer for answer in answers if answer is not None]
    assert len(retries) == 1, answers  # exactly one deadlock victim; the other was judged (two admins: allowed)
    assert retries[0].status_code == 503 and retries[0].detail["code"] == LAST_PLATFORM_ADMIN_RETRY_CODE
    assert int(retries[0].headers["Retry-After"]) >= 1


async def test_the_refusal_is_a_409_with_the_stable_code(engine):  # noqa: ANN001
    only = await _create(engine, "only", True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with async_session_scope(maker) as session:
        with pytest.raises(LastPlatformAdminError) as caught:
            await _service(session).set_platform_admin(only, False)
        refused = await refuse_last_platform_admin(session, caught.value)
    assert isinstance(refused, HTTPException) and refused.detail["code"] == LAST_PLATFORM_ADMIN_CODE
    assert await _active_admins(engine) == [only]


async def test_a_non_admin_deactivation_queues_behind_a_demotion_then_goes_through(engine):  # noqa: ANN001
    """A non-admin target takes the same id-ordered lock (admins plus itself), so it waits for the in-flight
    demotion and is then judged on the committed rows; it is not refused, as it is no admin."""
    first = await _create(engine, "a", True)
    await _create(engine, "b", True)
    plain = await _create(engine, "plain", False)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_scope(maker) as holder:
        await _service(holder).set_platform_admin(first, False)  # the admin rows are locked, uncommitted
        other = asyncio.create_task(_deactivate(maker, plain))
        await _wait_until_blocked(maker, other)
        await holder.commit()
        assert await asyncio.wait_for(other, timeout=10) == 200


async def test_a_promotion_in_flight_holds_back_the_deactivation_of_its_target(engine):  # noqa: ANN001
    """The target looked like a non-admin when the deactivation started; a concurrent promotion of it commits
    first, and the deactivation is then judged on the committed rows (two admins: allowed), never on a stale
    read that would let a demotion of the other admin leave nobody."""
    first = await _create(engine, "a", True)
    plain = await _create(engine, "plain", False)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with async_session_scope(maker) as holder:
        await _service(holder).set_platform_admin(plain, True)  # the target row is locked, uncommitted
        other = asyncio.create_task(_deactivate(maker, plain))
        await _wait_until_blocked(maker, other)
        await holder.commit()
        assert await asyncio.wait_for(other, timeout=10) == 200
    assert await _active_admins(engine) == [first]


async def _deactivate(maker, user_id) -> int:  # noqa: ANN001
    async with async_session_scope(maker) as session:
        try:
            await _service(session).deactivate_user(user_id)
        except LastPlatformAdminError as exc:
            return (await refuse_last_platform_admin(session, exc)).status_code
        await session.commit()
        return 200
