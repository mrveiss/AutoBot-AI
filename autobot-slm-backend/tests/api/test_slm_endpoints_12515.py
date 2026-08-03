# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Endpoint coverage for the rewritten SLM nodes-CRUD and stateful routers (#12515).

Follow-up to #12455, which deleted three dead ``autobot-backend`` tests
(``nodes_api_test.py``, ``stateful_api_test.py``, ``websockets_test.py``)
because they imported symbols removed in the layer-separation refactor
(``get_db_service``, ``StatefulServiceManager``, ``SLMWebSocketManager``, …).
The rewritten ``autobot-slm-backend`` routers use ``Depends(get_db)``
(``AsyncSession``) + ``get_current_user`` and had only narrow regression
coverage.  This module exercises the CURRENT code paths.

Strategy (mirrors ``tests/api/test_nodes_list_timeout_10913.py``): the root
conftest stubs ``sqlalchemy``/``models.database``/``models.schemas`` as
MagicMocks for import-time safety, so we snapshot the REAL modules once,
swap them in to import ``api.nodes``/``api.stateful`` with real FastAPI/
pydantic/ORM machinery, and drive the endpoints against a genuine
in-memory SQLite ``AsyncSession`` (aiosqlite).  This tests real query
logic, real 404s, and real ``model_validate`` contracts — not mock
identity.  The route functions are called directly (no TestClient), so
``get_current_user`` is satisfied by passing ``_={"admin": True}`` for the
already-authenticated principal.

Gaps (documented, not force-tested):
- ``verify_replication_sync`` happy path and ``verify_data`` redis path
  reach ``replication_service``/SSH subprocess infra that cannot be
  unit-tested without a live Redis + SSH target; only their 404 / non-redis
  branches are covered here.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

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
    """One-time real sqlalchemy + models.database/models.schemas/
    services.code_status snapshot.

    Copied from tests/api/test_nodes_list_timeout_10913.py: the root conftest
    stubs these as MagicMocks for import-time safety, so the real packages are
    loaded once here and swapped in on demand.

    services.code_status (#12571) must be real-loaded too: api.nodes'
    _get_latest_code_version/_reported_code_status now delegate there
    (#12428/#12570), and its own module-level ``select``/``Setting`` bindings
    need the real sqlalchemy/models.database swapped in first or its queries
    fail against a genuine aiosqlite AsyncSession.
    """
    saved = {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)}
    saved.update(
        {name: sys.modules.get(name) for name in ("models.database", "models.schemas", "services.code_status")}
    )
    for name in list(saved):
        sys.modules.pop(name, None)
    try:
        for name in _SQLALCHEMY_MODULES:
            importlib.import_module(name)
        importlib.import_module("sqlalchemy.dialects.sqlite")
        _load_real_module("models.database", _SLM_ROOT / "models" / "database.py")
        _load_real_module("models.schemas", _SLM_ROOT / "models" / "schemas.py")
        _load_real_module("services.code_status", _SLM_ROOT / "services" / "code_status.py")
        return {name: mod for name, mod in sys.modules.items() if _is_sqlalchemy_key(name)} | {
            "models.database": sys.modules["models.database"],
            "models.schemas": sys.modules["models.schemas"],
            "services.code_status": sys.modules["services.code_status"],
        }
    finally:
        for name in [n for n in sys.modules if _is_sqlalchemy_key(n)]:
            del sys.modules[name]
        sys.modules.pop("models.database", None)
        sys.modules.pop("models.schemas", None)
        sys.modules.pop("services.code_status", None)
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


def _load_api_module(dotted: str):
    """Import a real ``api.*`` router module under the real-module swap."""
    with _real_modules_swapped():
        sys.modules.pop(dotted, None)
        return importlib.import_module(dotted)


# Import the routers + real ORM/schemas once under the swap; the bound
# references (real Node/select/etc.) survive after stubs are restored.
_nodes = _load_api_module("api.nodes")
_stateful = _load_api_module("api.stateful")
_db_models = _REAL_MODULES["models.database"]
_schemas = _REAL_MODULES["models.schemas"]

Base = _db_models.Base
Node = _db_models.Node
NodeStatus = _db_models.NodeStatus
Backup = _db_models.Backup
BackupStatus = _db_models.BackupStatus
Replication = _db_models.Replication
ReplicationStatus = _db_models.ReplicationStatus

NodeCreate = _schemas.NodeCreate
NodeUpdate = _schemas.NodeUpdate
BackupCreate = _schemas.BackupCreate
ReplicationCreate = _schemas.ReplicationCreate
DataVerifyRequest = _schemas.DataVerifyRequest

with _real_modules_swapped():
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# Any already-authenticated principal — the route functions only receive the
# decoded payload (the auth dependency itself is not exercised here).
_PRINCIPAL = {"admin": True, "role": "admin", "sub": "tester"}


async def _close_session_and_engine(session, engine) -> None:
    """Close *session*, then dispose *engine*, without using ``__aexit__``.

    ``AsyncSession.__aexit__`` closes through
    ``await asyncio.shield(asyncio.create_task(self.close()))``.  Any test in
    this package that has replaced ``asyncio.create_task`` and whose
    ``monkeypatch`` undo is ordered *after* this teardown therefore hands
    ``shield`` a non-awaitable: the close is abandoned mid-flight and the
    aiosqlite connection stays checked out until the garbage collector
    terminates it (the ``SAWarning`` behind the xdist controller crash).
    Registering any fixture finalizer in this package is enough to produce that
    ordering, which made the old spelling a tripwire rather than a bug (#13329).

    ``AsyncSession.close()`` is a plain coroutine, so awaiting it directly is
    equivalent and depends on nothing global.  ``engine.dispose()`` runs from a
    ``finally`` so a failed close can never leave a half-open transport behind.
    """
    try:
        await session.close()
    finally:
        await engine.dispose()


@pytest.fixture
async def db():
    """A fresh real in-memory SQLite AsyncSession per test."""
    with _real_modules_swapped():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)()
    try:
        yield session
    finally:
        await _close_session_and_engine(session, engine)


# ---------------------------------------------------------------------------
# #13329 — the finalizer-ordering pin
# ---------------------------------------------------------------------------

_REAL_CREATE_TASK = asyncio.create_task


@pytest.fixture(autouse=True)
def finalizer_ordering_guard(request, monkeypatch):
    """Hold this module to the fixture ordering that used to break its teardown.

    ``db`` previously closed its session through
    ``AsyncSession.__aexit__`` → ``await asyncio.shield(asyncio.create_task(...))``
    while ``no_bg_tasks`` had ``asyncio.create_task`` replaced on the *shared*
    ``asyncio`` module.  Requesting ``monkeypatch`` as a parameter here — plus
    the ``addfinalizer`` below — puts ``monkeypatch``'s undo *underneath* ``db``
    on the finalizer stack, so the undo runs after ``db`` tears down.  That
    ordering is what turned the fixture into a tripwire: any fixture finalizer
    anywhere in ``tests/api`` produced it, and it cost 9 teardown errors plus a
    leaked aiosqlite connection (#13329).

    Autouse and unconditional on purpose: every test in this module now runs
    under the ordering, so a regression cannot hide behind a single test case.
    """
    request.addfinalizer(lambda: None)


async def test_db_teardown_survives_a_replaced_global_create_task(db, monkeypatch):
    """``db`` must tear down even with a non-awaitable ``asyncio.create_task``.

    ``monkeypatch``'s undo is ordered after ``db``'s teardown (see
    ``finalizer_ordering_guard``), so the replacement below is still live while
    the session closes — the exact interpreter state that raised
    ``TypeError: An asyncio.Future, a coroutine or an awaitable is required``.
    """
    monkeypatch.setattr(asyncio, "create_task", lambda *a, **kw: MagicMock())
    assert db.is_active


def test_no_bg_tasks_leaves_the_shared_asyncio_module_untouched(no_bg_tasks):
    """The background-task patch stays inside ``api.stateful``."""
    assert asyncio.create_task is _REAL_CREATE_TASK
    assert _stateful.asyncio is not asyncio
    assert _stateful.asyncio.create_task is not _REAL_CREATE_TASK
    assert _stateful.asyncio.wait_for is asyncio.wait_for


async def _insert_node(db, node_id: str, ip: str = "10.0.0.10", **overrides) -> Node:
    """Persist a minimal online Node row and return it."""
    node = Node(
        node_id=node_id,
        hostname=overrides.get("hostname", f"host-{node_id}"),
        ip_address=ip,
        status=overrides.get("status", NodeStatus.ONLINE.value),
    )
    db.add(node)
    await db.commit()
    await db.refresh(node)
    return node


# ---------------------------------------------------------------------------
# Nodes CRUD (api/nodes.py) — list / create / get / update / delete
# ---------------------------------------------------------------------------


class TestNodesCrud:
    """The rewritten get_db/auth-based nodes router (#12515)."""

    async def test_list_empty(self, db):
        result = await _nodes.list_nodes(db=db, _=_PRINCIPAL, status_filter=None, page=1, per_page=20)
        assert result.total == 0
        assert result.nodes == []
        assert result.page == 1

    async def test_create_returns_201_shape_and_persists(self, db):
        node_data = NodeCreate(
            hostname="web-1",
            ansible_name="web-1",
            ip_address="10.0.0.21",
            import_existing=True,  # -> ONLINE, and skips enrollment path
            auth_method="key",  # avoid the password-encryption (mocked) branch
        )
        created = await _nodes.create_node(node_data=node_data, db=db, _=_PRINCIPAL)

        assert created.hostname == "web-1"
        assert created.ip_address == "10.0.0.21"
        assert created.status == NodeStatus.ONLINE.value

        # Persisted and visible through the list endpoint.
        listed = await _nodes.list_nodes(db=db, _=_PRINCIPAL, status_filter=None, page=1, per_page=20)
        assert listed.total == 1
        assert listed.nodes[0].node_id == created.node_id

    async def test_create_pending_when_not_imported(self, db):
        node_data = NodeCreate(hostname="p-1", ansible_name="p-1", ip_address="10.0.0.22", auth_method="key")
        created = await _nodes.create_node(node_data=node_data, db=db, _=_PRINCIPAL)
        assert created.status == NodeStatus.PENDING.value

    async def test_create_duplicate_ip_rejected_400(self, db):
        await _insert_node(db, "n-dup", ip="10.0.0.30")
        node_data = NodeCreate(hostname="dup", ansible_name="dup", ip_address="10.0.0.30", auth_method="key")
        with pytest.raises(HTTPException) as exc:
            await _nodes.create_node(node_data=node_data, db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 400

    async def test_get_returns_node(self, db):
        await _insert_node(db, "n-get", ip="10.0.0.40")
        got = await _nodes.get_node(node_id="n-get", db=db, _=_PRINCIPAL)
        assert got.node_id == "n-get"
        assert got.ip_address == "10.0.0.40"

    async def test_get_not_found_404(self, db):
        with pytest.raises(HTTPException) as exc:
            await _nodes.get_node(node_id="ghost", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404

    async def test_update_mutates_fields(self, db):
        await _insert_node(db, "n-upd", ip="10.0.0.50")
        updated = await _nodes.update_node(
            node_id="n-upd",
            node_data=NodeUpdate(hostname="renamed"),
            db=db,
            _=_PRINCIPAL,
        )
        assert updated.hostname == "renamed"
        # Round-trips through a fresh read.
        reread = await _nodes.get_node(node_id="n-upd", db=db, _=_PRINCIPAL)
        assert reread.hostname == "renamed"

    async def test_update_not_found_404(self, db):
        with pytest.raises(HTTPException) as exc:
            await _nodes.update_node(node_id="ghost", node_data=NodeUpdate(hostname="x"), db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404

    async def test_delete_removes_node(self, db):
        await _insert_node(db, "n-del", ip="10.0.0.60")
        result = await _nodes.delete_node(node_id="n-del", db=db, _=_PRINCIPAL)
        assert result is None  # 204 No Content
        with pytest.raises(HTTPException) as exc:
            await _nodes.get_node(node_id="n-del", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404

    async def test_delete_not_found_404(self, db):
        with pytest.raises(HTTPException) as exc:
            await _nodes.delete_node(node_id="ghost", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404

    async def test_list_status_filter_narrows(self, db):
        await _insert_node(db, "n-online", ip="10.0.0.71", status=NodeStatus.ONLINE.value)
        await _insert_node(db, "n-offline", ip="10.0.0.72", status=NodeStatus.OFFLINE.value)
        online = await _nodes.list_nodes(
            db=db, _=_PRINCIPAL, status_filter=NodeStatus.ONLINE.value, page=1, per_page=20
        )
        assert online.total == 1
        assert online.nodes[0].node_id == "n-online"


# ---------------------------------------------------------------------------
# Stateful REST (api/stateful.py) — backups + replications
# ---------------------------------------------------------------------------


def _make_no_op_task_asyncio() -> types.ModuleType:
    """Return an ``asyncio`` stand-in whose ``create_task`` schedules nothing.

    A module object carrying a copy of the real ``asyncio`` namespace, so every
    other attribute ``api/stateful.py`` reaches for
    (``create_subprocess_exec``, ``subprocess.PIPE``, ``wait_for``,
    ``TimeoutError``) keeps its real behaviour.
    """

    def _fake_create_task(coro=None, *args, **kwargs):
        if asyncio.iscoroutine(coro):
            coro.close()
        return MagicMock()

    shim = types.ModuleType("asyncio")
    shim.__dict__.update(vars(asyncio))
    shim.create_task = _fake_create_task  # type: ignore[attr-defined]
    return shim


@pytest.fixture
def no_bg_tasks(monkeypatch):
    """Neutralise the fire-and-forget ``asyncio.create_task`` background jobs.

    ``create_backup``/``start_replication``/``restore_backup`` kick off async
    jobs that reach real backup/replication services (stubbed MagicMocks here).
    Scheduling those would either raise (MagicMock isn't a coroutine) or leak
    'never retrieved' task warnings, so replace scheduling with a coroutine-safe
    no-op for the duration of the test.

    #13329: the replacement goes on the *router module's* ``asyncio`` binding,
    never on the shared ``asyncio`` module itself.  ``monkeypatch.setattr(
    _stateful.asyncio, "create_task", ...)`` mutated the one ``asyncio`` object
    the whole process shares — including the copy SQLAlchemy's
    ``AsyncSession.__aexit__`` calls — so for as long as the undo had not run,
    every unrelated async teardown in this package got a ``MagicMock`` back from
    ``create_task``.  Rebinding the name inside ``api.stateful`` keeps the blast
    radius at exactly the module under test.
    """
    monkeypatch.setattr(_stateful, "asyncio", _make_no_op_task_asyncio())


class TestStatefulBackups:
    """Backup endpoints on the SQLAlchemy-backed stateful router (#12515)."""

    async def test_list_backups_empty(self, db):
        result = await _stateful.list_backups(
            db=db, _=_PRINCIPAL, node_id=None, service_type=None, status_filter=None, page=1, per_page=20
        )
        assert result.total == 0
        assert result.backups == []

    async def test_create_backup_201_for_existing_node(self, db, no_bg_tasks):
        await _insert_node(db, "n-bk", ip="10.0.0.80")
        created = await _stateful.create_backup(
            request=BackupCreate(node_id="n-bk", service_type="redis"),
            db=db,
            _=_PRINCIPAL,
        )
        assert created.node_id == "n-bk"
        assert created.status == BackupStatus.PENDING.value
        assert created.backup_id

        listed = await _stateful.list_backups(
            db=db, _=_PRINCIPAL, node_id=None, service_type=None, status_filter=None, page=1, per_page=20
        )
        assert listed.total == 1

    async def test_create_backup_unknown_node_404(self, db, no_bg_tasks):
        with pytest.raises(HTTPException) as exc:
            await _stateful.create_backup(
                request=BackupCreate(node_id="ghost", service_type="redis"), db=db, _=_PRINCIPAL
            )
        assert exc.value.status_code == 404

    async def test_get_backup_roundtrip_and_404(self, db, no_bg_tasks):
        await _insert_node(db, "n-bk2", ip="10.0.0.81")
        created = await _stateful.create_backup(
            request=BackupCreate(node_id="n-bk2", service_type="redis"), db=db, _=_PRINCIPAL
        )
        got = await _stateful.get_backup(backup_id=created.backup_id, db=db, _=_PRINCIPAL)
        assert got.backup_id == created.backup_id

        with pytest.raises(HTTPException) as exc:
            await _stateful.get_backup(backup_id="nope", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404

    async def test_restore_rejects_non_completed_backup_400(self, db, no_bg_tasks):
        await _insert_node(db, "n-bk3", ip="10.0.0.82")
        created = await _stateful.create_backup(
            request=BackupCreate(node_id="n-bk3", service_type="redis"), db=db, _=_PRINCIPAL
        )
        # Fresh backup is PENDING, not COMPLETED -> cannot restore.
        with pytest.raises(HTTPException) as exc:
            await _stateful.restore_backup(backup_id=created.backup_id, db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 400

    async def test_restore_completed_backup_starts_job(self, db, no_bg_tasks):
        backup = Backup(
            backup_id="bk-done",
            node_id="n-any",
            service_type="redis",
            status=BackupStatus.COMPLETED.value,
        )
        db.add(backup)
        await db.commit()
        result = await _stateful.restore_backup(backup_id="bk-done", db=db, _=_PRINCIPAL)
        assert result.success is True
        assert result.job_id

    async def test_restore_missing_backup_404(self, db, no_bg_tasks):
        with pytest.raises(HTTPException) as exc:
            await _stateful.restore_backup(backup_id="ghost", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404


class TestStatefulReplications:
    """Replication endpoints on the stateful router (#12515)."""

    async def test_list_replications_empty(self, db):
        result = await _stateful.list_replications(
            db=db, _=_PRINCIPAL, source_node_id=None, target_node_id=None, status_filter=None, page=1, per_page=20
        )
        assert result.total == 0
        assert result.replications == []

    async def test_start_replication_201(self, db, no_bg_tasks):
        await _insert_node(db, "src", ip="10.0.0.90")
        await _insert_node(db, "dst", ip="10.0.0.91")
        created = await _stateful.start_replication(
            request=ReplicationCreate(source_node_id="src", target_node_id="dst", service_type="redis"),
            db=db,
            _=_PRINCIPAL,
        )
        assert created.source_node_id == "src"
        assert created.target_node_id == "dst"
        assert created.status == ReplicationStatus.PENDING.value

        listed = await _stateful.list_replications(
            db=db, _=_PRINCIPAL, source_node_id=None, target_node_id=None, status_filter=None, page=1, per_page=20
        )
        assert listed.total == 1

    async def test_start_replication_missing_source_404(self, db, no_bg_tasks):
        await _insert_node(db, "dst2", ip="10.0.0.92")
        with pytest.raises(HTTPException) as exc:
            await _stateful.start_replication(
                request=ReplicationCreate(source_node_id="ghost", target_node_id="dst2"),
                db=db,
                _=_PRINCIPAL,
            )
        assert exc.value.status_code == 404

    async def test_start_replication_conflict_when_active_exists(self, db, no_bg_tasks):
        await _insert_node(db, "s3", ip="10.0.0.93")
        await _insert_node(db, "t3", ip="10.0.0.94")
        db.add(
            Replication(
                replication_id="rep-active",
                source_node_id="s3",
                target_node_id="t3",
                service_type="redis",
                status=ReplicationStatus.ACTIVE.value,
            )
        )
        await db.commit()
        with pytest.raises(HTTPException) as exc:
            await _stateful.start_replication(
                request=ReplicationCreate(source_node_id="s3", target_node_id="t3"),
                db=db,
                _=_PRINCIPAL,
            )
        assert exc.value.status_code == 400

    async def test_get_replication_roundtrip_and_404(self, db):
        db.add(
            Replication(
                replication_id="rep-1",
                source_node_id="a",
                target_node_id="b",
                service_type="redis",
                status=ReplicationStatus.PENDING.value,
            )
        )
        await db.commit()
        got = await _stateful.get_replication(replication_id="rep-1", db=db, _=_PRINCIPAL)
        assert got.replication_id == "rep-1"

        with pytest.raises(HTTPException) as exc:
            await _stateful.get_replication(replication_id="nope", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404

    async def test_promote_translates_service_success(self, db, monkeypatch):
        """promote_replica maps a service (True, msg) into an ActionResponse."""
        monkeypatch.setattr(
            _stateful.replication_service,
            "promote_replica",
            AsyncMock(return_value=(True, "promoted")),
        )
        result = await _stateful.promote_replica(replication_id="rep-x", db=db, _=_PRINCIPAL)
        assert result.action == "promote"
        assert result.success is True
        assert result.message == "promoted"
        assert result.resource_id == "rep-x"

    async def test_promote_service_failure_400(self, db, monkeypatch):
        monkeypatch.setattr(
            _stateful.replication_service,
            "promote_replica",
            AsyncMock(return_value=(False, "not a replica")),
        )
        with pytest.raises(HTTPException) as exc:
            await _stateful.promote_replica(replication_id="rep-x", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 400
        assert exc.value.detail == "not a replica"

    async def test_stop_translates_service_success(self, db, monkeypatch):
        monkeypatch.setattr(
            _stateful.replication_service,
            "stop_replication",
            AsyncMock(return_value=(True, "stopped")),
        )
        result = await _stateful.stop_replication(replication_id="rep-y", db=db, _=_PRINCIPAL)
        assert result.action == "stop"
        assert result.success is True
        assert result.resource_id == "rep-y"

    async def test_verify_replication_sync_missing_404(self, db):
        with pytest.raises(HTTPException) as exc:
            await _stateful.verify_replication_sync(replication_id="ghost", db=db, _=_PRINCIPAL)
        assert exc.value.status_code == 404


class TestStatefulVerify:
    """Data-verification endpoint (api/stateful.py verify_data) — #12515."""

    async def test_verify_unknown_node_404(self, db):
        with pytest.raises(HTTPException) as exc:
            await _stateful.verify_data(
                request=DataVerifyRequest(node_id="ghost", service_type="redis"), db=db, _=_PRINCIPAL
            )
        assert exc.value.status_code == 404

    async def test_verify_non_redis_service_is_skipped(self, db):
        """Non-redis services short-circuit to a 'skipped' check (no infra call)."""
        await _insert_node(db, "n-vf", ip="10.0.0.99")
        result = await _stateful.verify_data(
            request=DataVerifyRequest(node_id="n-vf", service_type="postgres"), db=db, _=_PRINCIPAL
        )
        assert result.service_type == "postgres"
        assert result.is_healthy is True
        assert any(check["status"] == "skipped" for check in result.checks)
