# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Admin-status changes against a real database: per-user revision, pending check, clocks (#20670).

The mocked tests in ``tests/security/test_admin_status_20670.py`` cannot reach what the database
decides: the order of a user's changes, rows of two users side by side, and a server whose time zone
is not the application's. Here the real ``UserService`` runs on a real schema through the real
``commit_or_503``; only the epoch store (in memory) and the application clock (a stepped counter) are
stood in for. The database session time zone is deliberately not UTC.

Needs the disposable Postgres the migration gate provides (skipped without it).
"""

import uuid
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from autobot_shared.user_management import password_epoch
from autobot_shared.user_management.base_service import TenantContext
from tests.migrations.conftest import create_all_schema, requires_postgres

pytestmark = [pytest.mark.migration_gate, requires_postgres]

NOT_UTC = {"server_settings": {"timezone": "Pacific/Auckland"}}
START = 1_900_000_000


@pytest.fixture
async def engine(fresh_db_url):
    await create_all_schema(fresh_db_url)
    engine = create_async_engine(fresh_db_url, connect_args=NOT_UTC)
    yield engine
    await engine.dispose()


@pytest.fixture
def clock(monkeypatch):
    """The application clock, shared by the recorded time and the epoch marker; tests step it."""
    state = SimpleNamespace(now=START)
    fake = SimpleNamespace(time=lambda: state.now)
    from autobot_shared.user_management import user_service_lifecycle

    monkeypatch.setattr(password_epoch, "time", fake)
    monkeypatch.setattr(user_service_lifecycle, "time", fake)
    monkeypatch.setattr(password_epoch, "MEMBERSHIP_EPOCH_BUMP_BACKOFF_SECONDS", 0.0)
    return state


@pytest.fixture
def store():
    """An in-memory epoch store that can be taken down: a down store records nothing."""
    state = SimpleNamespace(epochs={}, down=False)

    async def get_epoch(subject):
        return state.epochs.get(subject)

    async def set_epoch(subject, *, now=None):
        if state.down:
            return None
        state.epochs[subject] = now
        return now

    password_epoch.use_epoch_store(get_epoch=get_epoch, set_epoch=set_epoch)
    yield state
    password_epoch.reset_epoch_store()


def _service_class():
    from autobot_shared.user_management.user_service import UserService
    from user_management.models import User  # the concrete mapped model; ``UserCore`` is abstract

    class _Bound(UserService):
        user_model = User

    return _Bound


async def _create_user(engine, name: str, is_admin: bool) -> uuid.UUID:
    from user_management.models import User

    async with AsyncSession(engine) as session:
        user = User(email=f"{name}@example.test", username=name, is_platform_admin=is_admin)
        session.add(user)
        await session.commit()
        return user.id


async def _request(engine, user_id: uuid.UUID, is_admin: bool):
    """One PUT /admin: a fresh session, the change, the commit. A downed store answers 503."""
    from autobot_shared.user_management.revocation_outcome import commit_or_503

    async with AsyncSession(engine) as session:
        service = _service_class()(session, TenantContext())
        outcome = await service.set_platform_admin(user_id, is_admin)
        await commit_or_503(session)
        return outcome


async def _request_with_store_down(engine, store, user_id: uuid.UUID, is_admin: bool) -> None:
    store.down = True
    try:
        with pytest.raises(HTTPException) as failed:
            await _request(engine, user_id, is_admin)
    finally:
        store.down = False
    assert failed.value.status_code == 503


async def _revisions(engine, user_id: uuid.UUID) -> list[int]:
    from autobot_shared.user_management.models.audit import AuditLog

    async with AsyncSession(engine) as session:
        rows = await session.execute(select(AuditLog.details).where(AuditLog.resource_ref == str(user_id)))
        return sorted(d["revision"] for d in rows.scalars().all())


async def test_a_same_second_promotion_does_not_confirm_a_failed_demotion(engine, clock, store):
    """MED 1: promote at T (marker T), demote at T whose marker fails; the repeat must still revoke at T+1."""
    alice = await _create_user(engine, "alice", False)
    assert (await _request(engine, alice, True)).changed is True
    assert store.epochs["alice"] == START
    await _request_with_store_down(engine, store, alice, False)
    assert store.epochs["alice"] == START, "the failed demotion wrote nothing"

    retry = await _request(engine, alice, False)

    assert retry.changed is False and retry.sessions_revoked is True
    assert store.epochs["alice"] == START + 1, "a token minted in the demotion's second is void"
    assert (await _request(engine, alice, False)).sessions_revoked is False, "now confirmed: no repeat"


async def test_revisions_are_per_user_and_two_users_do_not_see_each_others_changes(engine, clock, store):
    alice = await _create_user(engine, "alice", False)
    bob = await _create_user(engine, "bob", True)
    await _request(engine, alice, True)
    await _request(engine, bob, False)
    clock.now += 5
    await _request(engine, alice, False)
    await _request(engine, alice, True)

    assert await _revisions(engine, alice) == [1, 2, 3]
    assert await _revisions(engine, bob) == [1]
    # bob's demotion is confirmed; alice's last change is a promotion, so a repeat demotion of bob is a no-op
    assert (await _request(engine, bob, False)).sessions_revoked is False


async def test_the_latest_change_is_the_highest_revision_not_the_newest_timestamp(engine, clock, store):
    """MED 2: the database time of a row says nothing about lock order; the revision does."""
    alice = await _create_user(engine, "alice", True)
    await _request_with_store_down(engine, store, alice, False)  # revision 1: demotion, marker lost
    async with engine.begin() as conn:  # make the demotion's row look like the OLDEST by database time
        await conn.execute(text("UPDATE audit_logs SET created_at = created_at - interval '1 day'"))
    clock.now += 1
    await _request(engine, alice, True)  # revision 2: promotion
    async with engine.begin() as conn:  # and the promotion's row the oldest of all
        await conn.execute(
            text("UPDATE audit_logs SET created_at = created_at - interval '2 days' WHERE details->>'revision' = '2'")
        )
    clock.now += 1
    await _request(engine, alice, False)  # revision 3: demotion, confirmed

    assert await _revisions(engine, alice) == [1, 2, 3]
    assert (await _request(engine, alice, False)).sessions_revoked is False, "revision 3 is latest and confirmed"


async def test_a_failed_promotion_marker_is_retried_by_a_repeat_call(engine, clock, store):
    """LOW 5: the promotion committed, its marker did not; the repeat records it, a second repeat does not."""
    alice = await _create_user(engine, "alice", False)
    await _request_with_store_down(engine, store, alice, True)
    assert "alice" not in store.epochs

    retry = await _request(engine, alice, True)

    assert retry.changed is False and retry.sessions_revoked is True
    assert store.epochs["alice"] == START
    assert (await _request(engine, alice, True)).sessions_revoked is False


async def test_the_recorded_time_is_the_application_clock_whatever_the_database_zone(engine, clock, store):
    """LOW 3: recorded_at and the epoch share one clock; the server zone (not UTC here) never enters."""
    from autobot_shared.user_management.models.audit import AuditLog

    alice = await _create_user(engine, "alice", True)
    await _request(engine, alice, False)

    async with AsyncSession(engine) as session:
        details = (await session.execute(select(AuditLog.details))).scalars().one()
        zone = (await session.execute(text("SHOW TIME ZONE"))).scalar_one()
    assert zone == "Pacific/Auckland"
    assert details["recorded_at"] == START and store.epochs["alice"] == START + 1
