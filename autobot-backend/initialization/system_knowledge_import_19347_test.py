# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The backend imports the system-knowledge templates once per startup (#19347).

``get_knowledge_manager`` had no production caller, so the templates reached the KB only through
the operator CLI. These tests pin the one startup wiring point, the failure isolation, the zero-write
unchanged restart through the real manager and librarian, and the one-worker lease.
"""

import ast
import asyncio
import shutil
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

import agents.knowledge_manager as km
from agents.kb_librarian import KBLibrarian
from agents.kb_librarian.stable_ids import IMPORT_HASH_FIELD, LINK_FIELD, SystemFactIds, system_fact_id, text_digest
from agents.system_knowledge_manager import SystemKnowledgeManager
from autobot_shared.async_compat import pending_background_tasks
from autobot_shared.leader_lease import LeaderLease
from autobot_shared.system_knowledge_paths import system_knowledge_templates_dir
from initialization import system_knowledge_import as ski

_BACKEND = Path(__file__).resolve().parents[1]


class _FakeKB:
    """In-memory KB counting every store/update the import makes."""

    def __init__(self) -> None:
        self.facts: dict[str, str] = {}
        self.meta: dict[str, dict] = {}
        self.writes = 0

    def get_fact(self, fact_id):
        return {"id": fact_id, "metadata": self.meta.get(fact_id, {})} if fact_id in self.facts else None

    async def store_fact(self, content, metadata=None, fact_id=None):
        self.writes += 1
        fid = fact_id or f"random-{self.writes}"
        self.facts[fid], self.meta[fid] = content, dict(metadata or {})
        return {"status": "success"}

    async def update_fact(self, fact_id, content=None, metadata=None):
        if fact_id not in self.meta:
            return {"status": "error", "message": "Fact not found"}
        self.writes += 1
        self.facts[fact_id] = content if content is not None else self.facts[fact_id]
        self.meta[fact_id] = {**self.meta[fact_id], **(metadata or {})}
        return {"status": "success"}


class _FakeSyncRedis:
    """The file-state cache store (``get`` / ``setex``)."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    def get(self, key):
        return self.data.get(key)

    def setex(self, key, _ttl, value):
        self.data[key] = value


class _FakeAsyncRedis:
    """Just enough of Redis for ``LeaderLease``: SET NX and the compare-and-extend script."""

    def __init__(self) -> None:
        self.data: dict[str, str] = {}
        self.ttl_ms: dict[str, int] = {}

    async def set(self, key, value, nx=False, px=None):
        if nx and key in self.data:
            return None
        self.data[key], self.ttl_ms[key] = value, px
        return True

    async def eval(self, _script, _nkeys, key, worker_id, ttl):
        if self.data.get(key) != worker_id:
            return 0
        self.ttl_ms[key] = int(ttl)
        return 1

    async def delete(self, key):
        self.data.pop(key, None)
        self.ttl_ms.pop(key, None)


def _batches_of(kb: _FakeKB):
    async def _gen():
        yield [{"fact_id": f, "content": c, "metadata": kb.meta[f]} for f, c in kb.facts.items()]

    return _gen


def _system_manager(kb: _FakeKB, tmp_path, templates: Path | None = None) -> SystemKnowledgeManager:
    """The real manager over the real template tree (or a copy), with the runtime dir under tmp_path."""
    manager = object.__new__(SystemKnowledgeManager)
    manager.knowledge_base = kb
    manager.librarian = KBLibrarian.__new__(KBLibrarian)
    manager.librarian.knowledge_base = kb
    manager.system_knowledge_dir = templates or system_knowledge_templates_dir()
    manager.fact_ids = SystemFactIds(_batches_of(kb))
    manager.runtime_knowledge_dir = tmp_path / "runtime"
    manager.backup_dir = tmp_path / "backup"
    manager._import_failures, manager._import_unresolved = [], []
    return manager


def _won_lease() -> MagicMock:
    lease = MagicMock(refresh_s=3600)
    lease.update_leadership = AsyncMock(return_value=True)
    return lease


@pytest.fixture(autouse=True)
def _fresh_singleton(monkeypatch):
    """Each test is a fresh process: no KnowledgeManager built yet."""
    monkeypatch.setattr(km, "_knowledge_manager_instance", None)


# --- one wiring point -------------------------------------------------------------------------


def _calls_by_function(name: str) -> dict[str, list[int]]:
    """Function name -> line numbers of every ``name(...)`` call inside it, across lifespan.py."""
    tree = ast.parse((_BACKEND / "initialization" / "lifespan.py").read_text(encoding="utf-8"))
    found: dict[str, list[int]] = {}
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(fn):
                if isinstance(node, ast.Call) and getattr(node.func, "id", None) == name:
                    found.setdefault(fn.name, []).append(node.lineno)
    return found


def test_startup_starts_the_import_once_right_after_the_kb_is_ready() -> None:
    starts = _calls_by_function("start_system_knowledge_import")
    assert starts.keys() == {"_init_knowledge_base"} and len(starts["_init_knowledge_base"]) == 1
    [kb_ready] = _calls_by_function("get_or_create_knowledge_base")["_init_knowledge_base"]
    assert starts["_init_knowledge_base"][0] > kb_ready
    assert len(_calls_by_function("_init_knowledge_base")["initialize_background_services"]) == 1


def _production_callers(symbol: str) -> list[str]:
    out = subprocess.run(  # nosec B603 B607  # fixed argv
        ["git", "grep", "--untracked", "-lw", symbol, "--", "*.py"],
        cwd=_BACKEND,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return sorted(p for p in out if not p.endswith("_test.py") and "/tests/" not in p and not p.startswith("tests/"))


def test_there_is_one_production_entry_point() -> None:
    # Each list is the defining module plus its ONE caller.
    assert _production_callers("start_system_knowledge_import") == [
        "initialization/lifespan.py",
        "initialization/system_knowledge_import.py",
    ]
    assert _production_callers("get_knowledge_manager") == [
        "agents/knowledge_manager.py",
        "initialization/system_knowledge_import.py",
    ]


@pytest.mark.asyncio
async def test_start_schedules_one_retained_task() -> None:
    app = SimpleNamespace(state=SimpleNamespace(knowledge_base=object()))
    with patch.object(ski, "run_system_knowledge_import", new=AsyncMock(return_value=True)) as run:
        task = ski.start_system_knowledge_import(app)
        assert task in pending_background_tasks()
        await task
    run.assert_awaited_once_with(app.state.knowledge_base)


def test_start_without_a_kb_schedules_nothing() -> None:
    assert ski.start_system_knowledge_import(SimpleNamespace(state=SimpleNamespace())) is None


# --- failure isolation ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_failed_import_is_logged_and_does_not_raise() -> None:
    with (
        patch.object(km, "get_knowledge_manager", side_effect=RuntimeError("kb exploded")),
        patch.object(ski.logger, "error") as logged,
    ):
        assert await ski.run_system_knowledge_import(_FakeKB(), lease=_won_lease()) is False
    assert "kb exploded" in str(logged.call_args)


@pytest.mark.asyncio
async def test_a_failed_import_task_ends_without_an_exception() -> None:
    app = SimpleNamespace(state=SimpleNamespace(knowledge_base=_FakeKB()))
    with (
        patch.object(ski, "import_lease", return_value=_won_lease()),
        patch.object(km, "get_knowledge_manager", side_effect=RuntimeError("boom")),
    ):
        task = ski.start_system_knowledge_import(app)
        assert await task is False
    assert task.exception() is None


# --- idempotent restart -----------------------------------------------------------------------


async def _startup(kb: _FakeKB, tmp_path, templates: Path | None = None) -> bool:
    km._knowledge_manager_instance = None  # a restart is a new process
    build = lambda base: _system_manager(base, tmp_path, templates)  # noqa: E731
    with patch.object(km, "SystemKnowledgeManager", side_effect=build):
        return await ski.run_system_knowledge_import(kb, lease=_won_lease())


@pytest.mark.asyncio
async def test_an_unchanged_restart_makes_zero_kb_writes(tmp_path) -> None:
    kb, cache = _FakeKB(), _FakeSyncRedis()
    with (
        patch("autobot_shared.redis_client.get_redis_client", return_value=cache),
        patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()),
    ):
        assert await _startup(kb, tmp_path) is True
        first = kb.writes
        assert first > 0, "the first startup imported nothing"
        assert cache.data, "the first startup recorded no template file state"
        assert await _startup(kb, tmp_path) is True
    assert kb.writes == first, "an unchanged restart wrote to the KB"
    assert (tmp_path / "runtime" / ".template_hashes.json").exists()


# --- one worker -------------------------------------------------------------------------------


def _lease(worker: str) -> LeaderLease:
    return LeaderLease(key=ski.IMPORT_LEASE_KEY, database="knowledge", worker_id=worker, label="test")


@pytest.mark.asyncio
async def test_a_second_worker_does_not_import_concurrently() -> None:
    gate, imports = asyncio.Event(), []

    async def _slow_import(_kb):
        imports.append(1)
        await gate.wait()

    redis = _FakeAsyncRedis()
    with (
        patch("autobot_shared.leader_lease.get_async_redis_client", new=AsyncMock(return_value=redis)),
        patch.object(ski, "_import", new=_slow_import),
    ):
        first = asyncio.create_task(ski.run_system_knowledge_import(_FakeKB(), lease=_lease("worker-a")))
        await asyncio.sleep(0)
        assert await ski.run_system_knowledge_import(_FakeKB(), lease=_lease("worker-b")) is False
        gate.set()
        assert await first is True
    assert imports == [1]


@pytest.mark.asyncio
async def test_failed_items_make_the_run_unsuccessful_and_are_warned() -> None:
    manager = MagicMock(initialize=AsyncMock(), import_failures=["tool:gh"])
    with (
        patch.object(km, "get_knowledge_manager", return_value=manager),
        patch.object(ski.logger, "warning") as warned,
    ):
        assert await ski.run_system_knowledge_import(_FakeKB(), lease=_won_lease()) is False
    assert "tool:gh" in str(warned.call_args)


def test_the_facade_reports_the_system_managers_failed_items(tmp_path) -> None:
    system = _system_manager(_FakeKB(), tmp_path)
    system._import_failures.append("tool:gh")
    facade = km.KnowledgeManager(_FakeKB(), enable_temporal=False, enable_machine_aware=False, system_manager=system)
    assert facade.import_failures == ["tool:gh"]


# --- never overwrite a user edit on a startup import ------------------------------------------


def _edit_template(templates: Path) -> list[str]:
    """Change the purpose of every tool in one template file; return the changed tool names."""
    path = templates / "tools" / "github_tools.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    for tool in data["tools"]:
        tool["purpose"] += " (revised template)"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return [tool["name"] for tool in data["tools"]]


@pytest.mark.asyncio
async def test_a_changed_template_keeps_a_user_edit_and_refreshes_an_unedited_fact(tmp_path) -> None:
    templates = tmp_path / "templates"
    shutil.copytree(system_knowledge_templates_dir(), templates)
    kb, cache = _FakeKB(), _FakeSyncRedis()
    with (
        patch("autobot_shared.redis_client.get_redis_client", return_value=cache),
        patch("agents.kb_librarian.librarian.publish_event", new=AsyncMock()),
    ):
        assert await _startup(kb, tmp_path, templates) is True
        edited, unedited = (system_fact_id("tool", name) for name in _edit_template(templates))
        kb.facts[edited] = "USER EDIT"  # the recorded import hash no longer matches the body
        edited_meta, unedited_body = dict(kb.meta[edited]), kb.facts[unedited]
        assert await _startup(kb, tmp_path, templates) is True
    assert kb.facts[edited] == "USER EDIT", "a startup import overwrote a user edit"
    changed = {k for k in kb.meta[edited].keys() | edited_meta.keys() if kb.meta[edited].get(k) != edited_meta.get(k)}
    assert changed <= {LINK_FIELD} and kb.meta[edited][LINK_FIELD] == edited
    # Positive control: the unedited owned fact IS rewritten from the changed template.
    assert kb.facts[unedited] != unedited_body and "(revised template)" in kb.facts[unedited]
    assert kb.meta[unedited][IMPORT_HASH_FIELD] == text_digest(kb.facts[unedited])


# --- a cancelled import leaves the lease to expire --------------------------------------------


@pytest.mark.asyncio
async def test_a_cancelled_import_leaves_the_lease_to_expire_not_deleted() -> None:
    started = asyncio.Event()

    async def _hanging_import(_kb):
        started.set()
        await asyncio.Event().wait()

    redis, lease = _FakeAsyncRedis(), _lease("worker-a")
    with (
        patch("autobot_shared.leader_lease.get_async_redis_client", new=AsyncMock(return_value=redis)),
        patch.object(ski, "_import", new=_hanging_import),
    ):
        run = asyncio.create_task(ski.run_system_knowledge_import(_FakeKB(), lease=lease))
        await started.wait()
        run.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run
        await asyncio.sleep(0)
    assert redis.data[ski.IMPORT_LEASE_KEY] == "worker-a", "the lease key was deleted"
    assert redis.ttl_ms[ski.IMPORT_LEASE_KEY] == lease.ttl_ms, "the lease lost its TTL"
    assert not [t for t in asyncio.all_tasks() if t.get_name() == f"{ski.IMPORT_TASK_NAME}-lease"]


@pytest.mark.asyncio
async def test_losing_the_lease_mid_run_is_warned() -> None:
    lease = MagicMock(refresh_s=0)
    lease.update_leadership = AsyncMock(return_value=False)
    with patch.object(ski.logger, "warning") as warned:
        await ski._keep_lease(lease)
    assert "lost its lease" in str(warned.call_args)


@pytest.mark.asyncio
async def test_losing_the_lease_mid_run_cancels_the_import() -> None:
    started, outcome = asyncio.Event(), []

    async def _hanging_import(_kb):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            outcome.append("cancelled")
            raise
        outcome.append("finished")

    lease = MagicMock(refresh_s=0)
    lease.update_leadership = AsyncMock(side_effect=[True, False])
    with (
        patch.object(ski, "_import", new=_hanging_import),
        patch.object(ski.logger, "error") as logged,
    ):
        # Bounded: an import that ignores the lost lease hangs here instead of returning.
        run = ski.run_system_knowledge_import(_FakeKB(), lease=lease)
        assert await asyncio.wait_for(run, timeout=5) is False
    assert started.is_set() and outcome == ["cancelled"], "the import kept running after the lease was lost"
    assert "lost the import lease" in str(logged.call_args)
    assert lease.update_leadership.await_count == 2
