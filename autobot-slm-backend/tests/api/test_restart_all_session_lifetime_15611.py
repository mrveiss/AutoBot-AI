# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The deferred SLM restart must own its DB session, and persist what it writes (#15611).

``restart_all_node_services`` used to hand ``Depends(get_db)``'s ``Node`` row and
a list of ``Service`` rows loaded through that session straight into a FastAPI
background task. Background tasks run after the response, which is after
dependency teardown has committed and closed that session, so every
``svc.status`` / ``active_state`` / ``sub_state`` / ``last_checked`` write the
task made landed on a detached row — and there was no ``commit()`` anywhere in
the deferred path to persist it. The route's own commit had already fired.

The failure was silent, which shapes these tests twice over:

* A closed ``AsyncSession`` is reusable — the next ``execute()`` quietly checks
  a fresh connection out of the pool — so "close the session, then await" passes
  against the bug and proves nothing. ``_RequestScopedSession`` makes FastAPI's
  lifetime explicit instead: any database call after ``close()`` raises.
* ``expire_on_commit=False`` leaves the loaded columns readable on the detached
  rows, so the restart ran and the WebSocket fired and nothing raised. The only
  assertion that separates fixed from broken is *durability*: the status is read
  back through a different session, after the deferred work has finished.

Own file rather than an addition to an existing api test module: the tests here
need the real SQLAlchemy stack that the root conftest stubs, and that swap now
lives in ``_real_orm_import.py`` next door, shared with the other tests/api
modules that need it (#15640).

#15657 adds the second class below. The fix above commits after *each* service
rather than once at the end, and the reason is that a single trailing commit
discards every restart that already succeeded when a later one fails — the same
silent write loss, one loop iteration wider. That reasoning was carried only by
a comment until now, so hoisting the commit out of the loop (which reads as
removing redundant work) passed every test in this file.
"""

from __future__ import annotations

import contextlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks

# The real ORM swap this file needs is shared with the other tests/api modules
# that must import a router against genuine sqlalchemy and Pydantic rather than
# the root conftest's MagicMocks (#15640). Same shape as the `_code_sync_import`
# / `_health_import` helpers next to it.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import (  # noqa: E402
    REAL_MODULES,
    SLM_ROOT,
    import_modules_with_real_orm,
    real_modules_swapped,
)

# ``api.services`` and ``services.service_restart`` must BOTH see the real ORM:
# the endpoint's whole contract here is which objects it hands across a
# background boundary, and an assertion about a ``Service`` row would pass
# vacuously against a MagicMock. ``services`` is itself a MagicMock rather than
# a package, so its child is loaded by file spec and re-bound onto that stub.
_restart, _services_api = import_modules_with_real_orm(
    import_names=("api.services",),
    path_loaded={"services.service_restart": SLM_ROOT / "services" / "service_restart.py"},
)
_db_models = REAL_MODULES["models.database"]

Base = _db_models.Base
Node = _db_models.Node
NodeStatus = _db_models.NodeStatus
Service = _db_models.Service
ServiceStatus = _db_models.ServiceStatus

with real_modules_swapped():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_PRINCIPAL = {"admin": True, "role": "admin", "sub": "tester"}
_NODE_ID = "n-restart"

# Session methods that constitute "using the database through this session".
_SESSION_DB_METHODS = frozenset(
    {"add", "commit", "delete", "execute", "flush", "get", "merge", "refresh", "rollback", "scalar", "scalars"}
)


class _RequestScopedSession:
    """A real ``AsyncSession`` that refuses to be used after request teardown.

    SQLAlchemy does not enforce the lifetime FastAPI imposes — a call on a
    closed session quietly takes a fresh connection from the pool — which is why
    #15611 lost writes instead of failing. This proxy makes the contract
    explicit: every attribute reaches the real session until ``close()``, and any
    database call after that is recorded and raises.
    """

    def __init__(self, session):
        self._session = session
        self.closed = False
        self.uses_after_close: list[str] = []

    def __getattr__(self, name):
        if self.closed and name in _SESSION_DB_METHODS:
            self.uses_after_close.append(name)
            raise AssertionError(f"request-scoped session used after teardown: {name}()")
        return getattr(self._session, name)

    async def close(self) -> None:
        """Mimic FastAPI's dependency teardown."""
        self.closed = True
        await self._session.close()


class _JobSessionFactory:
    """Stand-in for ``services.database.db_service`` recording what it opens.

    ``session()`` mirrors ``DatabaseService.session`` — commit on clean exit,
    roll back and re-raise on an exception, close in ``finally`` — so the job
    runs the lifecycle it gets in production.

    #15657: the rollback branch is what makes the mid-batch failure test mean
    anything. ``services/database.py`` really does roll back when the block
    raises, so a commit hoisted out of the per-service loop loses every write
    the batch had made; a harness that only skipped the commit would rely on
    ``close()``'s implicit rollback instead of the explicit one production has.
    """

    def __init__(self, sessionmaker):
        self._sessionmaker = sessionmaker
        self.opened: list = []

    @contextlib.asynccontextmanager
    async def session(self):
        session = self._sessionmaker()
        self.opened.append(session)
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


@pytest.fixture
async def restart_env(monkeypatch):
    """Real engine, a request-scoped session proxy, and a job session factory."""
    with real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    request_session = _RequestScopedSession(maker())
    job_sessions = _JobSessionFactory(maker)

    fake_db_module = types.ModuleType("services.database")
    fake_db_module.db_service = job_sessions
    monkeypatch.setitem(sys.modules, "services.database", fake_db_module)

    fake_ws_module = types.ModuleType("api.websocket")
    fake_ws_module.ws_manager = AsyncMock()
    monkeypatch.setitem(sys.modules, "api.websocket", fake_ws_module)

    monkeypatch.setattr(_restart, "run_ansible_service_action", AsyncMock(return_value=(True, "restarted")))
    monkeypatch.setattr(_restart, "_RESPONSE_FLUSH_DELAY_SECONDS", 0.0)

    try:
        yield request_session, job_sessions, maker
    finally:
        # #13329: close the session directly. ``AsyncSession.__aexit__`` goes
        # through ``asyncio.shield(asyncio.create_task(...))``, which any test
        # that has replaced ``create_task`` turns into an abandoned close.
        try:
            await request_session._session.close()
        finally:
            await engine.dispose()


async def _seed(db, service_names: list) -> None:
    """One online node plus a stopped service row per name."""
    db.add(Node(node_id=_NODE_ID, hostname="host-restart", ip_address="10.0.0.71", status=NodeStatus.ONLINE.value))
    for name in service_names:
        db.add(
            Service(
                node_id=_NODE_ID,
                service_name=name,
                status=ServiceStatus.STOPPED.value,
                active_state="inactive",
                sub_state="dead",
            )
        )
    await db.commit()


async def _call_restart_all(request_session) -> tuple:
    """Drive the endpoint exactly as FastAPI would, returning (response, tasks)."""
    background_tasks = BackgroundTasks()
    response = await _services_api.restart_all_node_services(
        node_id=_NODE_ID,
        db=request_session,
        _=_PRINCIPAL,
        background_tasks=background_tasks,
        request=None,
    )
    return response, background_tasks.tasks


async def _read_service(maker, service_name: str):
    """Read one service row back through a session nothing else has touched."""
    verifier = maker()
    try:
        result = await verifier.execute(
            select(Service).where(Service.node_id == _NODE_ID, Service.service_name == service_name)
        )
        return result.scalar_one()
    finally:
        await verifier.close()


class TestDeferredSlmRestartOwnsItsSession:
    """#15611 — the SLM half of restart-all must not borrow ``db`` or its rows."""

    async def test_status_written_by_the_deferred_restart_is_durable(self, restart_env):
        """The deferred restart persists its writes after the request has ended.

        The background callable is run only once the request session has been
        torn down exactly as dependency teardown tears it down, and the status is
        then read back through a *different* session.

        Against the pre-fix code this fails twice over: the job mutated rows
        detached from a closed session, and nothing in that path committed, so
        ``slm-agent`` is still STOPPED when the verifier reads it. The third
        assertion fails there independently — no session was ever opened through
        ``db_service``.
        """
        request_session, job_sessions, maker = restart_env
        await _seed(request_session, ["nginx", "slm-agent"])

        response, tasks = await _call_restart_all(request_session)
        assert response.slm_agent_restarted is True
        assert len(tasks) == 1

        await request_session.close()
        await tasks[0]()

        assert request_session.uses_after_close == []
        assert job_sessions.opened, "the deferred restart opened no session of its own"
        assert all(opened is not request_session._session for opened in job_sessions.opened)

        deferred = await _read_service(maker, "slm-agent")
        assert deferred.status == ServiceStatus.RUNNING.value
        assert deferred.active_state == "active"
        assert deferred.sub_state == "running"
        assert deferred.last_checked is not None

    async def test_synchronous_half_still_persists_through_the_request_session(self, restart_env):
        """Non-SLM services keep their in-request commit — the fix moves only the
        deferred half's lifetime, not the synchronous path's."""
        request_session, _job_sessions, maker = restart_env
        await _seed(request_session, ["nginx", "slm-agent"])

        response, _tasks = await _call_restart_all(request_session)
        assert response.successful_restarts == 1
        assert response.failed_restarts == 0

        immediate = await _read_service(maker, "nginx")
        assert immediate.status == ServiceStatus.RUNNING.value
        assert immediate.last_checked is not None

    async def test_no_orm_row_or_session_crosses_the_background_boundary(self, restart_env):
        """The task is handed plain identifiers only.

        A row loaded through the request session is detached the moment that
        session closes, so passing one across the boundary is the same defect as
        passing the session — even when the session is never touched again.
        """
        request_session, _job_sessions, _maker = restart_env
        await _seed(request_session, ["slm-agent", "slm-backend"])

        _response, tasks = await _call_restart_all(request_session)
        assert len(tasks) == 1

        handed_over = list(tasks[0].args) + list(tasks[0].kwargs.values())
        assert handed_over, "the background task was given nothing"
        for value in handed_over:
            for item in value if isinstance(value, (list, tuple)) else [value]:
                assert not isinstance(item, (Node, Service)), f"ORM row crossed the boundary: {item!r}"
                assert item is not request_session
                assert item is not request_session._session
        assert _NODE_ID in handed_over
        assert ["slm-agent", "slm-backend"] in handed_over


class TestOneFailureDoesNotDiscardTheRestartsThatSucceeded:
    """#15657 — ``restart_slm_services`` commits per service, not once at the end.

    ``services/service_restart.py`` commits inside the loop and says why: "so one
    failure cannot discard them all". With ``db_service.session()`` committing on
    clean exit and rolling back on an exception, a single trailing commit throws
    away every service that restarted before the one that raised.

    Hoisting that commit out of the loop reads like removing redundant work, and
    every other test in this file still passes when it is: the session is still
    owned, the boundary still carries scalars, the first service still restarts.
    Only a batch whose *middle* member fails, read back through a session that
    was never part of the job, separates the two.
    """

    async def test_a_mid_batch_failure_keeps_the_service_already_restarted(self, restart_env, monkeypatch):
        """Service one is durably RUNNING, service three was never attempted.

        The read-back goes through a session the job never touched, because the
        job's own session would answer from its in-memory identity map and pass
        on state that was never committed — the exact reason #15611 was silent.

        Against a commit hoisted out of the loop this fails on the first status
        assertion: the rollback that follows the middle service's exception
        discards ``slm-agent``'s write, and the verifier reads ``stopped``.
        """
        request_session, job_sessions, maker = restart_env
        ordered = ["slm-agent", "slm-backend", "slm-admin-ui"]
        await _seed(request_session, ordered)

        attempted: list = []

        async def _action(_node, service_name, _action_name):
            attempted.append(service_name)
            if service_name == "slm-backend":
                raise RuntimeError("ssh transport died mid-batch")
            return True, "restarted"

        monkeypatch.setattr(_restart, "run_ansible_service_action", _action)
        await request_session.close()

        with pytest.raises(RuntimeError, match="ssh transport died mid-batch"):
            await _restart.restart_slm_services(_NODE_ID, ordered)

        # The batch stops at the failure rather than skipping past it: the third
        # service is never asked to restart, so "untouched" below is a fact about
        # the loop, not an artefact of the transport double.
        assert attempted == ["slm-agent", "slm-backend"]
        assert len(job_sessions.opened) == 1

        first = await _read_service(maker, "slm-agent")
        assert first.status == ServiceStatus.RUNNING.value, (
            "the restart that succeeded before the failure was discarded — the commit belongs "
            "inside the per-service loop (#15657)"
        )
        assert first.active_state == "active"
        assert first.sub_state == "running"
        assert first.last_checked is not None

        failed = await _read_service(maker, "slm-backend")
        assert failed.status == ServiceStatus.STOPPED.value

        third = await _read_service(maker, "slm-admin-ui")
        assert third.status == ServiceStatus.STOPPED.value, "the batch skipped the failure instead of stopping at it"
        assert third.last_checked is None
