# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Post-commit goal work must cross the boundary as data, and survive the trip (#15612).

``_schedule_post_commit_index`` used to close over the ``LLCGoal`` row itself and
hand it to ``loop.create_task(...)`` whose handle was thrown away. Two defects in
one line:

* The row belongs to the request's session, which is committed and closed
  immediately after the hook fires — the task then reads a detached instance. It
  works today only because ``expire_on_commit=False`` leaves the already-loaded
  columns readable; a deferred column or a lazy relationship added later turns it
  into a ``MissingGreenlet`` in production and nowhere else. So the assertion
  that separates fixed from broken is *ownership*: the indexer must load what it
  needs through a session of its own, not read a row it was handed.
* The event loop keeps only a weak reference to a task, so a discarded handle can
  be garbage-collected mid-flight, taking its exception with it (#15522). The
  assertion for that is retention: while the coroutine is in flight the task is
  in ``pending_background_tasks()``, and it leaves that set only once the done
  callback — the thing that logs a failure — has run.
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from autobot_shared.async_compat import pending_background_tasks
from llc.models.goal import GoalLevel, LLCGoal
from llc.services import goal as goal_module
from llc.services.goal import GoalService
from llc.tests import _e2e_harness as harness
from user_management.models.base import Base

_COMPANY = "co-15612"

# Session methods that constitute "using the database through this session".
_SESSION_DB_METHODS = frozenset(
    {"add", "commit", "delete", "execute", "flush", "get", "merge", "refresh", "rollback", "scalar", "scalars"}
)


class _RequestScopedSession:
    """A real ``AsyncSession`` that refuses to be used after the request ends.

    SQLAlchemy does not enforce the lifetime the request imposes: a call on a
    closed session quietly checks a fresh connection out of the pool, so
    "close it, then await the task" passes against the bug and proves nothing.
    This proxy makes the contract explicit — every attribute reaches the real
    session until ``close()``, and any database call after that raises.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self.closed = False
        self.uses_after_close: list[str] = []

    def __getattr__(self, name):
        if self.closed and name in _SESSION_DB_METHODS:
            self.uses_after_close.append(name)
            raise AssertionError(f"request-scoped session used after teardown: {name}()")
        return getattr(self._session, name)

    async def close(self) -> None:
        """Mimic the request's dependency teardown."""
        self.closed = True
        await self._session.close()


class _JobSessionFactory:
    """Records the sessions the post-commit work opens for itself."""

    def __init__(self, sessionmaker) -> None:
        self._sessionmaker = sessionmaker
        self.opened: list = []

    def __call__(self) -> AsyncSession:
        session = self._sessionmaker()
        self.opened.append(session)
        return session


@pytest_asyncio.fixture
async def goal_env(monkeypatch) -> AsyncIterator[tuple]:
    """Only the table this test touches — the pattern ``test_step_rollup.py`` sets."""
    engine = create_async_engine(  # canonical: ignore py-adhoc-db-engine (test-local engine)
        "sqlite+aiosqlite:///:memory:"
    )
    tables = [LLCGoal.__table__]
    for table in tables:
        harness._scrub_pg_server_defaults(table)
        harness._clientside_timestamps(table)
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tables))
    maker = async_sessionmaker(  # canonical: ignore py-adhoc-db-engine (test-local factory)
        engine, expire_on_commit=False, class_=AsyncSession
    )

    request_session = _RequestScopedSession(maker())
    job_sessions = _JobSessionFactory(maker)
    monkeypatch.setattr(
        "user_management.database.get_async_session_factory",
        lambda: job_sessions,
    )
    outstanding = pending_background_tasks()
    try:
        yield GoalService(), request_session, job_sessions
    finally:
        # Anything this test scheduled and did not await would otherwise reach
        # a disposed engine, or outlive the test as a "pending task destroyed"
        # warning attributed to whatever ran next.
        for task in pending_background_tasks() - outstanding:
            task.cancel()
        await request_session._session.close()
        await engine.dispose()


def _chroma_stub() -> tuple:
    """A stand-in ``utils.async_chromadb_client`` module and its collection."""
    collection = AsyncMock()
    client = AsyncMock()
    client.get_or_create_collection = AsyncMock(return_value=collection)
    client.get_collection_or_none = AsyncMock(return_value=collection)
    module = MagicMock()
    module.get_async_chromadb_client = AsyncMock(return_value=client)
    return module, collection


async def _create_and_commit(svc: GoalService, session, title: str = "Vision 2030") -> LLCGoal:
    """Create one goal and commit, which is what fires the post-commit hooks."""
    goal = await svc.create(
        session,
        company_id=_COMPANY,
        title=title,
        level=GoalLevel.VISION,
        description="Long-term vision statement",
    )
    await session.commit()
    return goal


class TestPostCommitIndexOwnsItsSession:
    """#15612 — the indexer must reload the row, not be handed it."""

    async def test_index_reloads_the_goal_through_a_session_of_its_own(self, goal_env, monkeypatch):
        """The indexing completes with the originating session already closed.

        The coroutine ``fire_and_forget`` would schedule is captured instead, the
        request session is closed exactly as the request's teardown closes it, and
        only then is the coroutine awaited.

        Against the pre-fix code this fails on the ownership assertions: the
        coroutine read the ``LLCGoal`` it had been handed, so no session was ever
        opened for the job.
        """
        svc, request_session, job_sessions = goal_env
        captured: list = []
        monkeypatch.setattr(goal_module, "fire_and_forget", lambda coro, **_: captured.append(coro))

        goal = await _create_and_commit(svc, request_session)
        assert len(captured) == 1

        await request_session.close()
        chroma_module, collection = _chroma_stub()
        with patch.dict(sys.modules, {"utils.async_chromadb_client": chroma_module}):
            await captured[0]

        assert request_session.uses_after_close == []
        assert job_sessions.opened, "the post-commit indexer opened no session of its own"
        assert all(opened is not request_session._session for opened in job_sessions.opened)

        collection.upsert.assert_awaited_once()
        kwargs = collection.upsert.call_args.kwargs
        assert kwargs["ids"] == [str(goal.id)]
        assert "Vision 2030" in kwargs["documents"][0]
        assert kwargs["metadatas"][0]["company_id"] == _COMPANY

    async def test_no_orm_row_or_session_crosses_the_post_commit_boundary(self, goal_env, monkeypatch):
        """The scheduled work is handed plain identifiers only.

        A row is detached the moment the session that loaded it closes, so
        capturing one in a post-commit task is the same defect as capturing the
        session — even when the row is never re-read.
        """
        svc, request_session, _job_sessions = goal_env
        recorded: dict = {}

        async def _record(*args, **kwargs) -> None:
            recorded["handed_over"] = list(args) + list(kwargs.values())

        monkeypatch.setattr(svc, "_index_goal", _record)
        captured: list = []
        monkeypatch.setattr(goal_module, "fire_and_forget", lambda coro, **_: captured.append(coro))

        goal = await _create_and_commit(svc, request_session)
        await captured[0]

        handed_over = recorded["handed_over"]
        assert handed_over, "_index_goal was called with nothing"
        for value in handed_over:
            assert not isinstance(value, LLCGoal), f"ORM row crossed the boundary: {value!r}"
            assert value is not request_session
            assert value is not request_session._session
            assert not isinstance(value, AsyncSession)
        assert str(goal.id) in handed_over
        assert _COMPANY in handed_over

    async def test_a_goal_deleted_before_indexing_is_skipped(self, goal_env, monkeypatch):
        """The reload is also the existence check — a vanished row indexes nothing."""
        svc, request_session, _job_sessions = goal_env
        captured: list = []
        monkeypatch.setattr(goal_module, "fire_and_forget", lambda coro, **_: captured.append(coro))

        goal = await _create_and_commit(svc, request_session)
        await request_session.execute(LLCGoal.__table__.delete().where(LLCGoal.id == goal.id))
        await request_session.commit()
        await request_session.close()

        chroma_module, collection = _chroma_stub()
        with patch.dict(sys.modules, {"utils.async_chromadb_client": chroma_module}):
            await captured[0]

        collection.upsert.assert_not_awaited()


class TestPostCommitTasksAreRetained:
    """#15612 / #15524 — a discarded task handle can be collected mid-flight."""

    async def test_the_index_task_is_retained_until_its_callback_runs(self, goal_env, monkeypatch):
        """The scheduled index task is held by ``fire_and_forget`` while in flight.

        Against the pre-fix code the task is created by a bare
        ``loop.create_task`` whose handle is dropped, so it never appears in
        ``pending_background_tasks()`` and the loop holds only a weak reference
        to it.
        """
        svc, request_session, _job_sessions = goal_env
        started = asyncio.Event()
        release = asyncio.Event()

        async def _slow_index(*_args, **_kwargs) -> None:
            started.set()
            await release.wait()

        monkeypatch.setattr(svc, "_index_goal", _slow_index)
        before = pending_background_tasks()

        goal = await _create_and_commit(svc, request_session)
        scheduled = [t for t in pending_background_tasks() - before if t.get_name().endswith(str(goal.id))]
        assert len(scheduled) == 1, "the index task was scheduled without being retained"

        await started.wait()
        release.set()
        await scheduled[0]
        assert scheduled[0] not in pending_background_tasks(), "the done callback never ran"

    async def test_a_failing_index_task_is_reported_rather_than_collected(self, goal_env, monkeypatch):
        """A failure reaches the done callback instead of vanishing with the task."""
        svc, request_session, _job_sessions = goal_env
        release = asyncio.Event()

        async def _boom(*_args, **_kwargs) -> None:
            # Held until the assertion below has run: a task that finishes
            # inside ``commit()``'s own awaits would be released again before
            # the snapshot, and the retention check would pass vacuously.
            await release.wait()
            raise RuntimeError("indexing blew up")

        monkeypatch.setattr(svc, "_index_goal", _boom)
        before = pending_background_tasks()

        goal = await _create_and_commit(svc, request_session)
        scheduled = [t for t in pending_background_tasks() - before if t.get_name().endswith(str(goal.id))]
        assert len(scheduled) == 1

        release.set()
        await asyncio.gather(*scheduled, return_exceptions=True)
        assert isinstance(scheduled[0].exception(), RuntimeError)
        assert scheduled[0] not in pending_background_tasks()

    async def test_the_chromadb_delete_task_is_retained_too(self, goal_env, monkeypatch):
        """``_schedule_post_commit_chromadb_delete`` had defect 2 on its own."""
        svc, request_session, _job_sessions = goal_env
        recorded: dict = {}
        release = asyncio.Event()

        async def _record(company_id: str, ids: list) -> None:
            # Held for the same reason as the index case above.
            await release.wait()
            recorded["args"] = (company_id, list(ids))

        monkeypatch.setattr(svc, "_delete_from_chromadb", _record)
        # The create below schedules a real index task too; it is not what this
        # test is measuring and it must not reach the engine after teardown.
        monkeypatch.setattr(svc, "_index_goal", AsyncMock())

        goal = await _create_and_commit(svc, request_session)
        before = pending_background_tasks()
        assert await svc.delete(request_session, goal.id) is True
        await request_session.commit()

        scheduled = list(pending_background_tasks() - before)
        assert len(scheduled) == 1, "the ChromaDB delete task was scheduled without being retained"
        release.set()
        await asyncio.gather(*scheduled)
        assert recorded["args"] == (_COMPANY, [str(goal.id)])


class TestSchedulingIsRobustWithoutALoop:
    """The registration seam must not build work it cannot schedule."""

    async def test_a_non_session_argument_registers_nothing(self, goal_env):
        """A test double without ``sync_session`` is skipped, not crashed on."""
        svc, _request_session, _job_sessions = goal_env
        goal = LLCGoal(company_id=_COMPANY, title="T", level=GoalLevel.VISION.value, status="draft")
        goal.id = uuid.uuid4()
        before = pending_background_tasks()

        svc._schedule_post_commit_index(MagicMock(spec=[]), goal)

        assert pending_background_tasks() == before


async def test_the_indexer_scopes_its_reload_to_the_owning_company(goal_env, monkeypatch):
    """A goal id alone must not read another company's row (#13704 lives here too)."""
    svc, request_session, _job_sessions = goal_env
    monkeypatch.setattr(svc, "_index_goal", AsyncMock())  # the real one is not what this measures
    goal = await _create_and_commit(svc, request_session)
    await request_session.close()

    snapshot = await svc._load_goal_snapshot(str(goal.id), "some-other-company")
    assert snapshot is None
    assert (await svc._load_goal_snapshot(str(goal.id), _COMPANY))["title"] == "Vision 2030"


async def test_the_reloaded_snapshot_carries_no_orm_instance(goal_env, monkeypatch):
    """What the loader returns is plain data — nothing detached escapes with it."""
    svc, request_session, _job_sessions = goal_env
    monkeypatch.setattr(svc, "_index_goal", AsyncMock())  # the real one is not what this measures
    goal = await _create_and_commit(svc, request_session)
    await request_session.close()

    snapshot = await svc._load_goal_snapshot(str(goal.id), _COMPANY)
    assert isinstance(snapshot, dict)
    for value in snapshot.values():
        assert not isinstance(value, LLCGoal)
    assert snapshot["id"] == str(goal.id)
    assert snapshot["level"] == GoalLevel.VISION.value


def test_neither_scheduler_captures_the_row_it_was_given():
    """Read the source: the schedulers may close over ids, never the instance."""
    import ast
    import inspect
    import textwrap

    for name in ("_schedule_post_commit_index", "_schedule_post_commit_chromadb_delete"):
        source = textwrap.dedent(inspect.getsource(getattr(GoalService, name)))
        tree = ast.parse(source)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        assert "goal_ref" not in names, f"{name} still captures the ORM row"
        assert not any(
            isinstance(n, ast.Attribute) and n.attr == "create_task" for n in ast.walk(tree)
        ), f"{name} schedules with a bare create_task — use fire_and_forget (#15522)"
