# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nothing removes the last active platform admin (#21018).

The guard runs real SQL against a real (file-backed SQLite) database through the real
``ensure_not_last_platform_admin`` and the real ``UserService`` lifecycle methods. SQLite has no row
locks, so the harness gives ``SELECT ... FOR UPDATE`` the one property that matters here: a second
transaction's locking read waits until the first commits, then reads the committed rows. The
production statement is asserted to compile to ``FOR UPDATE`` on PostgreSQL, so the harness and the
production query cannot drift apart.
"""

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import Boolean, DateTime, String, Uuid, select, update
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from api.schemas_admin_status import AdminStatusRequest
from api.user_management.admin_status import set_admin_status
from autobot_shared.db_session import POST_COMMIT_CALLBACKS
from autobot_shared.user_management.base_service import TenantContext
from autobot_shared.user_management.last_platform_admin import (
    LAST_PLATFORM_ADMIN_CODE,
    LastPlatformAdminError,
    ensure_not_last_platform_admin,
    lock_active_platform_admin_ids,
    refuse_last_platform_admin,
)
from autobot_shared.user_management.models.audit import IdentityAuditAction
from autobot_shared.user_management.user_service import UserService


class _Base(DeclarativeBase):
    pass


class _User(_Base):
    __tablename__ = "users"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    username: Mapped[str] = mapped_column(String)
    is_platform_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    deleted_at: Mapped[object] = mapped_column(DateTime, nullable=True)


class _LockingSession(AsyncSession):
    """A session whose locking read waits for the previous holder to commit (the FOR UPDATE contract)."""

    row_lock: asyncio.Lock
    holds_lock = False

    async def execute(self, statement, *args, **kwargs):
        if getattr(statement, "_for_update_arg", None) is not None and not self.holds_lock:
            await self.row_lock.acquire()
            self.holds_lock = True
        return await super().execute(statement, *args, **kwargs)

    def _release(self) -> None:
        if self.holds_lock:
            self.holds_lock = False
            self.row_lock.release()

    async def commit(self):
        try:
            await super().commit()
        finally:
            self._release()

    async def rollback(self):
        try:
            await super().rollback()
        finally:
            self._release()


@pytest_asyncio.fixture
async def maker(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'users.db'}")  # canonical: ignore py-adhoc-db-engine
    async with engine.begin() as conn:
        await conn.run_sync(_Base.metadata.create_all)
    row_lock = asyncio.Lock()

    def make() -> _LockingSession:
        session = _LockingSession(engine, expire_on_commit=False)
        session.row_lock = row_lock
        return session

    yield make
    await engine.dispose()


async def _seed(maker, admins: int, others: int = 0) -> list[uuid.UUID]:
    ids = []
    async with maker() as session:
        for index in range(admins + others):
            ids.append(uuid.uuid4())
            session.add(_User(id=ids[-1], username=f"u{index}", is_platform_admin=index < admins))
        await session.commit()
    return ids


class _Svc(UserService):
    user_model = _User


def _service(session) -> _Svc:
    svc = _Svc(session, TenantContext())
    session.info[POST_COMMIT_CALLBACKS] = []
    svc._audits = []

    async def write_audit(action, _type, resource_id, details, outcome="success") -> None:
        svc._audits.append((action, resource_id, details, outcome))

    svc._audit_log = AsyncMock(side_effect=write_audit)
    svc._admin_transitions = AsyncMock(return_value=[])
    svc.reassign_sessions = AsyncMock(return_value={})
    return svc


def _wire(svc: _Svc) -> _Svc:
    async def get_user(user_id, include_deleted=False):
        return await svc.session.get(_User, user_id)

    svc.get_user = get_user
    return svc


def test_the_production_query_locks_the_active_admin_rows_in_id_order():
    session = MagicMock()
    captured = []

    async def run(statement):
        captured.append(statement)
        return MagicMock(scalars=lambda: MagicMock(all=lambda: []))

    session.execute = run
    asyncio.run(lock_active_platform_admin_ids(session, _User))
    sql = str(captured[0].compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE" in sql and "ORDER BY users.id" in sql
    assert "is_platform_admin IS true" in sql and "deleted_at IS NULL" in sql


@pytest.mark.asyncio
async def test_demoting_the_only_admin_is_refused_and_the_row_is_unchanged(maker):
    (admin,) = await _seed(maker, 1)
    async with maker() as session:
        svc = _wire(_service(session))
        with pytest.raises(LastPlatformAdminError) as caught:
            await svc.set_platform_admin(admin, False)
    assert caught.value.status_code == 409 and caught.value.code == LAST_PLATFORM_ADMIN_CODE
    async with maker() as session:
        assert (await session.get(_User, admin)).is_platform_admin is True


@pytest.mark.asyncio
async def test_deactivating_the_only_admin_is_refused(maker):
    admin, *_ = await _seed(maker, 1, 2)
    async with maker() as session:
        with pytest.raises(LastPlatformAdminError):
            await _wire(_service(session)).deactivate_user(admin)
    async with maker() as session:
        assert (await session.get(_User, admin)).is_active is True


@pytest.mark.asyncio
@pytest.mark.parametrize("hard_delete", [False, True])
async def test_deleting_the_only_admin_is_refused(maker, hard_delete):
    admin, _plain = await _seed(maker, 1, 1)
    async with maker() as session:
        with pytest.raises(LastPlatformAdminError):
            await _wire(_service(session)).delete_user(admin, hard_delete=hard_delete)
    async with maker() as session:
        row = await session.get(_User, admin)
        assert row is not None and row.deleted_at is None and row.is_active is True


@pytest.mark.asyncio
async def test_with_two_admins_one_demotion_deactivation_and_deletion_each_succeed(maker):
    """The control: the refusals above come from the guard, not from the harness."""
    first, second, third = await _seed(maker, 3)
    async with maker() as session:
        svc = _wire(_service(session))
        assert (await svc.set_platform_admin(first, False)).changed is True
        await svc.deactivate_user(second)
        await session.commit()
    async with maker() as session:
        with pytest.raises(LastPlatformAdminError):  # now third is the only one left
            await _wire(_service(session)).delete_user(third)


@pytest.mark.asyncio
async def test_a_user_who_is_not_an_admin_is_never_guarded(maker):
    _, plain = await _seed(maker, 1, 1)
    async with maker() as session:
        svc = _wire(_service(session))
        await svc.deactivate_user(plain)
        await svc.delete_user(plain)


@pytest.mark.asyncio
async def test_an_inactive_admin_does_not_count_as_a_second_admin(maker):
    first, second = await _seed(maker, 2)
    async with maker() as session:
        await session.execute(update(_User).where(_User.id == second).values(is_active=False))
        await session.commit()
    async with maker() as session:
        with pytest.raises(LastPlatformAdminError):
            await ensure_not_last_platform_admin(session, _User, first)


@pytest.mark.asyncio
async def test_concurrent_demotion_of_the_last_two_admins_lets_exactly_one_through(maker):
    first, second = await _seed(maker, 2)
    started = asyncio.Event()

    async def demote(admin: uuid.UUID) -> bool:
        async with maker() as session:
            try:
                await ensure_not_last_platform_admin(session, _User, admin)
            except LastPlatformAdminError:
                await session.rollback()
                return False
            started.set()
            await asyncio.sleep(0.05)  # the window in which the other would read the stale 2
            await session.execute(update(_User).where(_User.id == admin).values(is_platform_admin=False))
            await session.commit()
            return True

    outcomes = await asyncio.gather(demote(first), demote(second))
    assert sorted(outcomes) == [False, True]
    async with maker() as session:
        remaining = (await session.execute(select(_User.id).where(_User.is_platform_admin.is_(True)))).scalars().all()
    assert len(remaining) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("call", "action", "attempt"),
    [
        (lambda s, a: s.set_platform_admin(a, False), IdentityAuditAction.PLATFORM_ADMIN_CHANGED, "demote"),
        (lambda s, a: s.deactivate_user(a), IdentityAuditAction.USER_DEACTIVATED, "deactivate"),
        (lambda s, a: s.delete_user(a), IdentityAuditAction.USER_DELETED, "delete"),
    ],
)
async def test_each_refusal_is_audited_as_denied(maker, call, action, attempt):
    (admin,) = await _seed(maker, 1)
    async with maker() as session:
        svc = _wire(_service(session))
        with pytest.raises(LastPlatformAdminError):
            await call(svc, admin)
    assert svc._audits == [(action, admin, {"attempt": attempt, "reason": LAST_PLATFORM_ADMIN_CODE}, "denied")]


@pytest.mark.asyncio
async def test_the_route_answers_409_with_the_stable_code_and_commits_the_refusal(maker):
    """Self-demotion is the same path: the caller is the only admin, so it is refused."""
    (admin,) = await _seed(maker, 1)
    async with maker() as session:
        svc = _wire(_service(session))
        session.commit = AsyncMock()
        with pytest.raises(HTTPException) as caught:
            await set_admin_status(admin, AdminStatusRequest(is_platform_admin=False), svc)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == LAST_PLATFORM_ADMIN_CODE
    session.commit.assert_awaited_once()  # the denied audit row is not lost to the rollback


@pytest.mark.asyncio
async def test_self_demotion_succeeds_when_another_active_admin_exists(maker):
    caller, _other = await _seed(maker, 2)
    async with maker() as session:
        svc = _wire(_service(session))
        session.info[POST_COMMIT_CALLBACKS] = []
        result = await svc.set_platform_admin(caller, False)
    assert result.changed is True


@pytest.mark.asyncio
async def test_refuse_returns_the_409_after_committing(maker):
    session = MagicMock(commit=AsyncMock())
    error = await refuse_last_platform_admin(session, LastPlatformAdminError())
    assert error.status_code == 409 and error.detail["code"] == LAST_PLATFORM_ADMIN_CODE
    session.commit.assert_awaited_once()
