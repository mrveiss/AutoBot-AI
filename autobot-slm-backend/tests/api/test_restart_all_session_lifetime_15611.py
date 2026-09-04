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
need the real SQLAlchemy stack that the root conftest stubs, and the harness for
that is the one ``test_replication_session_lifetime_15549.py`` carries.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import BackgroundTasks

_SLM_ROOT = Path(__file__).resolve().parents[2]
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

_SQLALCHEMY_MODULES = ("sqlalchemy", "sqlalchemy.ext", "sqlalchemy.ext.asyncio", "sqlalchemy.orm")


def _is_sqlalchemy_key(name: str) -> bool:
    return name == "sqlalchemy" or name.startswith("sqlalchemy.")


def _load_real_module(name: str, path: Path):
    """Exec *path* under canonical *name* (registered so relative imports work)."""
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = module
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    return module


def _build_real_modules() -> dict:
    """One-time real sqlalchemy + models.database/models.schemas snapshot.

    The root conftest stubs these as MagicMocks for import-time safety. The real
    packages are loaded once here and swapped in on demand, so the router is
    exercised against genuine ORM machinery rather than mock identity.
    """
    saved = {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)}
    saved.update({name: sys.modules.get(name) for name in ("models.database", "models.schemas")})
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        for name in _SQLALCHEMY_MODULES:
            importlib.import_module(name)
        importlib.import_module("sqlalchemy.dialects.sqlite")
        _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
        _load_real_module("models.schemas", _SLM_ROOT / "models" / "schemas.py")
        return {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)} | {
            "models.database": sys.modules["models.database"],
            "models.schemas": sys.modules["models.schemas"],
        }
    finally:
        for name in [n for n in sys.modules if _is_sqlalchemy_key(n)]:
            del sys.modules[name]
        sys.modules.pop("models.database", None)
        sys.modules.pop("models.schemas", None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


_REAL_MODULES = _build_real_modules()


@contextlib.contextmanager
def _real_modules_swapped():
    """Temporarily put the real sqlalchemy/models modules into sys.modules."""
    saved = {name: sys.modules.get(name) for name in _REAL_MODULES}
    sys.modules.update(_REAL_MODULES)
    try:
        yield
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


def _load_router_and_job_seam():
    """Import ``api.services`` and ``services.service_restart`` for real.

    Both must see the real ORM: the endpoint's whole contract here is which
    objects it hands across a background boundary, and an assertion about a
    ``Service`` row would pass vacuously against a MagicMock. ``sys.modules`` is
    restored afterwards, leaving the stubs in place for every other test module.
    """
    names = ("services.service_restart", "api.services")
    saved = {name: sys.modules.get(name) for name in names}
    try:
        with _real_modules_swapped():
            restart = _load_real_module("services.service_restart", _SLM_ROOT / "services" / "service_restart.py")
            sys.modules.pop("api.services", None)
            return importlib.import_module("api.services"), restart
    finally:
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


_services_api, _restart = _load_router_and_job_seam()
_db_models = _REAL_MODULES["models.database"]

Base = _db_models.Base
Node = _db_models.Node
NodeStatus = _db_models.NodeStatus
Service = _db_models.Service
ServiceStatus = _db_models.ServiceStatus

with _real_modules_swapped():
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
    close in ``finally`` — so the job runs the lifecycle it gets in production.
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
        finally:
            await session.close()


@pytest.fixture
async def restart_env(monkeypatch):
    """Real engine, a request-scoped session proxy, and a job session factory."""
    with _real_modules_swapped():
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
