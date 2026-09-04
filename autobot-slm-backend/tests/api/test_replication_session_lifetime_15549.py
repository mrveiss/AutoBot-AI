# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The replication background job must own its DB session (#15549).

``start_replication`` used to hand ``Depends(get_db)``'s ``AsyncSession`` — and
two ``Node`` rows loaded through it — straight into a ``fire_and_forget``
coroutine. FastAPI closes that session in dependency teardown as soon as the
response is sent, so the job ran against a session whose lifetime had ended.

The failure is not the obvious one, which is why the tests below are shaped the
way they are. A closed ``AsyncSession`` is *reusable*: the next ``execute()``
silently checks a fresh connection out of the pool and succeeds. What does not
survive is the identity map — ``close()`` expunges every instance, so the rows
come back detached and re-attaching one raises ``InvalidRequestError``. So
closing the session and awaiting the coroutine proves nothing; it passes against
the buggy code. The property that separates fixed from broken is *ownership*:
the job's session must not be the request's. Both tests assert that directly.

Own file rather than an addition to ``test_slm_endpoints_12515.py``: that module
sits exactly on the 600-line limit the Python file-size ratchet enforces
(#14236), so it cannot grow. It carries a near-identical real-module harness;
the duplication is the ratchet's price, and ``test_nodes_list_timeout_10913.py``
already carries a third copy.
"""

from __future__ import annotations

import contextlib
import importlib
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

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

    The root conftest stubs these as MagicMocks for import-time safety. The
    real packages are loaded once here and swapped in on demand, so the router
    is exercised against genuine ORM machinery rather than mock identity.
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
    """Real-load ``services.replication`` → ``replication_jobs`` → ``api.stateful``.

    Order is load-bearing: ``services/replication_jobs.py`` binds
    ``replication_service`` from ``services.replication`` at import, and
    ``api/stateful.py`` binds ``setup_replication`` from
    ``services.replication_jobs``. Real-loading each in turn is what makes those
    bindings the real coroutines instead of the root conftest's MagicMocks — a
    MagicMock accepts any call signature, so every assertion below about *which*
    session the job uses would pass vacuously against one.

    ``sys.modules`` is restored afterwards, leaving the stubs in place for every
    other test module. ``ReplicationService.__init__`` calls
    ``Path(settings.ansible_dir)``, which a MagicMock attribute cannot satisfy;
    a throwaway path stands in for the exec and is restored immediately. Nothing
    writes there — every Ansible/SSH entry point is replaced per test.
    """
    names = ("services.replication", "services.replication_jobs", "api.stateful")
    saved = {name: sys.modules.get(name) for name in names}
    settings = sys.modules["config"].settings
    saved_ansible_dir = settings.ansible_dir
    settings.ansible_dir = str(Path(tempfile.gettempdir()) / "autobot-slm-test-ansible")
    try:
        with _real_modules_swapped():
            _load_real_module("services.replication", _SLM_ROOT / "services" / "replication.py")
            jobs = _load_real_module("services.replication_jobs", _SLM_ROOT / "services" / "replication_jobs.py")
            sys.modules.pop("api.stateful", None)
            return importlib.import_module("api.stateful"), jobs
    finally:
        settings.ansible_dir = saved_ansible_dir
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod
            else:
                sys.modules.pop(name, None)


_stateful, _jobs = _load_router_and_job_seam()
_db_models = _REAL_MODULES["models.database"]
_schemas = _REAL_MODULES["models.schemas"]

Base = _db_models.Base
Node = _db_models.Node
NodeStatus = _db_models.NodeStatus
Replication = _db_models.Replication
ReplicationStatus = _db_models.ReplicationStatus
ReplicationCreate = _schemas.ReplicationCreate

with _real_modules_swapped():
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

_PRINCIPAL = {"admin": True, "role": "admin", "sub": "tester"}

# Session methods that constitute "using the database through this session".
_SESSION_DB_METHODS = frozenset(
    {"add", "commit", "delete", "execute", "flush", "get", "merge", "refresh", "rollback", "scalar", "scalars"}
)


class _RequestScopedSession:
    """A real ``AsyncSession`` that refuses to be used after request teardown.

    SQLAlchemy does not enforce the lifetime FastAPI imposes — a call on a
    closed session quietly takes a fresh connection from the pool — which is
    precisely why #15549 corrupted state nondeterministically instead of
    failing. This proxy makes the contract explicit: every attribute reaches
    the real session until ``close()``, and any database call after that is
    recorded and raises.
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
async def replication_env():
    """Real engine + a request-scoped session proxy + a job session factory."""
    with _real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    request_session = _RequestScopedSession(maker())
    try:
        yield request_session, _JobSessionFactory(maker), maker
    finally:
        # #13329: close the session directly. ``AsyncSession.__aexit__`` goes
        # through ``asyncio.shield(asyncio.create_task(...))``, which any test
        # that has replaced ``create_task`` turns into an abandoned close.
        try:
            await request_session._session.close()
        finally:
            await engine.dispose()


async def _insert_node(db, node_id: str, ip: str) -> None:
    """Persist a minimal online Node row."""
    db.add(Node(node_id=node_id, hostname=f"host-{node_id}", ip_address=ip, status=NodeStatus.ONLINE.value))
    await db.commit()


def _install_job_stubs(monkeypatch, job_sessions):
    """Give the job seam a recording session factory and inert Ansible/SSH legs.

    ``setup_replication`` resolves ``db_service`` through a deferred
    ``from services.database import db_service``, so the injection point is
    ``sys.modules`` — the same lookup the running backend performs.
    """
    fake_db_module = types.ModuleType("services.database")
    fake_db_module.db_service = job_sessions
    monkeypatch.setitem(sys.modules, "services.database", fake_db_module)

    service = _jobs.replication_service
    monkeypatch.setattr(service, "_get_redis_password", AsyncMock(return_value=""))
    monkeypatch.setattr(service, "_run_ansible_replication", AsyncMock(return_value=True))
    monkeypatch.setattr(service, "_wait_for_sync", AsyncMock(return_value=True))
    monkeypatch.setattr(
        service,
        "_get_replication_info",
        AsyncMock(return_value={"master_repl_offset": "42", "lag_bytes": 0}),
    )
    # Would otherwise schedule a real 30-second polling task outliving the test.
    monkeypatch.setattr(service, "_start_lag_monitor", lambda replication_id: None)
    return service


class TestReplicationJobOwnsItsSession:
    """#15549 — ``start_replication``'s background job must not borrow ``db``."""

    async def test_job_runs_on_its_own_session_after_request_teardown(self, replication_env, monkeypatch):
        """The job completes with the request session already torn down.

        The coroutine handed to ``fire_and_forget`` is captured rather than
        scheduled, the request session is then closed exactly as dependency
        teardown closes it, and only afterwards is the coroutine awaited.

        Against the pre-fix code the endpoint passed ``db`` and two ``Node``
        rows bound to it into ``setup_replication``, so the job's first
        ``db.execute`` lands on the torn-down session and the proxy raises.
        Two further assertions fail independently there: nothing was opened
        through ``db_service``, and the row never reaches ACTIVE.
        """
        request_session, job_sessions, maker = replication_env
        _install_job_stubs(monkeypatch, job_sessions)

        captured: list = []
        monkeypatch.setattr(_stateful, "fire_and_forget", lambda coro, **_: captured.append(coro))

        await _insert_node(request_session, "n-src", "10.0.0.61")
        await _insert_node(request_session, "n-tgt", "10.0.0.62")

        created = await _stateful.start_replication(
            request=ReplicationCreate(source_node_id="n-src", target_node_id="n-tgt", service_type="redis"),
            db=request_session,
            _=_PRINCIPAL,
        )
        assert created.status == ReplicationStatus.PENDING.value
        assert len(captured) == 1

        await request_session.close()
        success, message = await captured[0]

        assert success is True, message
        assert request_session.uses_after_close == []
        assert job_sessions.opened, "the background job opened no session of its own"
        assert all(opened is not request_session for opened in job_sessions.opened)
        assert all(opened is not request_session._session for opened in job_sessions.opened)

        verifier = maker()
        try:
            row = (
                await verifier.execute(select(Replication).where(Replication.replication_id == created.replication_id))
            ).scalar_one()
            assert row.status == ReplicationStatus.ACTIVE.value
            assert row.sync_position == "42"
        finally:
            await verifier.close()

    async def test_no_orm_row_or_session_crosses_the_background_boundary(self, replication_env, monkeypatch):
        """``start_replication`` hands the job plain data only.

        A row loaded through the request session is detached the moment that
        session closes, so passing one across the boundary is the same defect
        as passing the session — even when the session is never touched again.
        """
        request_session, job_sessions, _maker = replication_env
        _install_job_stubs(monkeypatch, job_sessions)

        recorded: dict = {}

        async def _record(*args, **kwargs):
            recorded["handed_over"] = list(args) + list(kwargs.values())
            return True, "recorded"

        monkeypatch.setattr(_stateful, "setup_replication", _record)
        captured: list = []
        monkeypatch.setattr(_stateful, "fire_and_forget", lambda coro, **_: captured.append(coro))

        await _insert_node(request_session, "n-src2", "10.0.0.63")
        await _insert_node(request_session, "n-tgt2", "10.0.0.64")

        await _stateful.start_replication(
            request=ReplicationCreate(source_node_id="n-src2", target_node_id="n-tgt2", service_type="redis"),
            db=request_session,
            _=_PRINCIPAL,
        )
        await captured[0]

        handed_over = recorded["handed_over"]
        assert handed_over, "setup_replication was called with nothing"
        for value in handed_over:
            assert not isinstance(value, (Node, Replication)), f"ORM row crossed the boundary: {value!r}"
            assert value is not request_session
            assert value is not request_session._session
        assert {"n-src2", "n-tgt2"} <= {v for v in handed_over if isinstance(v, str)}
