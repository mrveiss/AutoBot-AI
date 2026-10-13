# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Node-level post-sync: one ordered plan, recorded, one execution path (#17455).

Drives the real ``api.node_post_sync`` and ``services.post_sync_plan_runner`` with the three
seams that touch the outside world replaced: the ssh command runner, the restart runner and the
recorder. The orchestrator and the database are fakes.
"""

from __future__ import annotations

import ast
import importlib
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent))
_orm = importlib.import_module("_real_orm_import")  # a sibling helper, not on the package path
SLM_ROOT = _orm.SLM_ROOT

_loaded = _orm.import_modules_with_real_orm(
    ("services.post_sync_recorder", "services.post_sync_plan_runner", "api.node_post_sync"),
    path_loaded={
        "services.service_restart": SLM_ROOT / "services" / "service_restart.py",
    },
)
_service_restart, recorder, plan_runner, node_post_sync = _loaded

_NOW = datetime(2026, 10, 11, tzinfo=timezone.utc)
_CTX = SimpleNamespace(node_ip="node.example.test", node_user="svc", node_port=22)


def _role(name, units=None, cmd=None):
    return SimpleNamespace(
        name=name, display_name=name, post_sync_cmd=cmd, systemd_service=units, auto_restart=bool(units)
    )


_ROLES = [
    _role("autobot-slm-backend", ["autobot-slm-backend"], "alembic upgrade head"),
    _role("autobot-llm-cpu", ["ollama"]),
    _role("autobot-llm-gpu", ["ollama"]),
    _role("autobot-ai-stack", ["autobot-ai-stack"], "pip install -r requirements-ai.txt"),
    _role("autobot-database", ["autobot-chromadb"]),
]


def _outcome(success=True, row=None):
    return recorder.ActionOutcome(success, 0 if success else 1, "", None if success else "exit 1", _NOW, _NOW, row)


class _World:
    """Everything the plan touches, with an ordered event log."""

    def __init__(self, monkeypatch, fail=()):
        self.events: list[tuple] = []
        self.orch = SimpleNamespace(
            sync_role_files=AsyncMock(side_effect=self._files),
            record_role_synced=AsyncMock(side_effect=self._versioned),
        )
        self.fail = set(fail)
        monkeypatch.setattr(node_post_sync, "get_sync_orchestrator", lambda: self.orch)
        monkeypatch.setattr(node_post_sync, "_load_roles", AsyncMock(side_effect=lambda names: _by_name(names)))
        monkeypatch.setattr(plan_runner, "run_post_sync_command", self._command)
        monkeypatch.setattr(plan_runner, "restart_units", self._restart)
        monkeypatch.setattr(plan_runner, "record_action_run", self._record)

    async def _files(self, node_id, role_name, commit):
        self.events.append(("files", node_id))
        return True, "OK", SimpleNamespace(node_ip=f"{node_id}.example.test", node_user="svc", node_port=22)

    async def _versioned(self, node_id, role_name, commit):
        self.events.append(("versioned", node_id, role_name))

    def _row(self, label, ok):
        return {"label": label, "category": "x", "success": ok, "error": None if ok else "exit 1"}

    async def _command(self, ssh_base, command, timeout, rec, label, category):
        self.events.append(("command", category, rec.role_name))
        ok = category not in self.fail
        return _outcome(ok, {**self._row(label, ok), "category": category})

    async def _restart(self, ssh_base, units, rec=None):
        self.events.append(("restart", " ".join(units), ssh_base[-1]))
        ok = " ".join(units) not in self.fail
        return _outcome(ok, {**self._row("Restart " + " ".join(units), ok), "category": "restart"})

    async def _record(self, rec, category, label, command, units, outcome):
        self.events.append(("record", category, units, outcome.success))
        return {"label": label, "category": category, "success": outcome.success, "error": outcome.error}


def _by_name(names):
    return [r for r in _ROLES if r.name in names]


def _restarts(events):
    return [e[1] for e in events if e[0] == "restart"]


async def _sync(world, restart=True, names=None, host_id=None):
    names = names or [r.name for r in _ROLES]
    return await node_post_sync.sync_node_roles("n1", names, "c1", restart, "run1", host_id)


async def test_node_plan_is_node_major_with_ollama_once_chromadb_first_and_slm_backend_last(monkeypatch):
    world = _World(monkeypatch)
    outcome = await _sync(world)
    kinds = [e[0] if e[0] == "restart" else e[1] for e in world.events if e[0] in ("restart", "command")]
    assert kinds[:2] == ["install", "schema"] and set(kinds[2:]) == {"restart"}
    assert _restarts(world.events) == ["ollama", "autobot-chromadb", "autobot-ai-stack", "autobot-slm-backend"]
    assert not outcome.plan.aborted
    assert world.orch.record_role_synced.await_count == len(_ROLES)


async def test_records_and_versions_are_committed_before_the_slm_backend_restart_is_issued(monkeypatch):
    world = _World(monkeypatch)
    monkeypatch.setattr(node_post_sync, "wait_for_response_flush", AsyncMock())
    outcome = await _sync(world, host_id="n1")
    assert "autobot-slm-backend" not in _restarts(world.events)  # held back: not sent during the sync
    assert [e[0] for e in world.events[-2:]] == ["versioned", "record"]
    assert world.events[-1][1:] == ("restart", "autobot-slm-backend", None)  # issued: success unknown
    assert any(r["success"] is None for r in outcome.plan.rows)  # the issued row is in the response
    await node_post_sync._issue_after_flush(outcome.plan.deferred)
    assert world.events[-1][:2] == ("restart", "autobot-slm-backend")
    assert [e[0] for e in world.events].index("versioned") < len(world.events) - 1


async def test_role_sync_puts_the_slm_host_last_and_defers_its_restart_until_every_node_is_done(monkeypatch):
    world = _World(monkeypatch)
    sent = []
    monkeypatch.setattr(node_post_sync, "_slm_host_node_id", AsyncMock(return_value="host"))
    monkeypatch.setattr(node_post_sync, "fire_and_forget", lambda coro, name: sent.append(coro))
    monkeypatch.setattr(node_post_sync, "wait_for_response_flush", AsyncMock())
    node_roles = [SimpleNamespace(node_id=n) for n in ("host", "n2", "n3")]  # the host is FIRST in the input
    results, ok_count, run_id, actions = await node_post_sync.sync_role_on_nodes(
        node_roles, "autobot-slm-backend", "c1", True
    )
    assert [r["node_id"] for r in results] == ["n2", "n3", "host"] and ok_count == 3
    synced = [e[1] for e in world.events if e[0] == "versioned"]
    assert synced == ["n2", "n3", "host"]
    assert [e[2] for e in world.events if e[0] == "restart"] == ["svc@n2.example.test", "svc@n3.example.test"]
    assert len(sent) == 1  # one deferred task, scheduled only after the loop
    await sent[0]
    assert world.events[-1] == ("restart", "autobot-slm-backend", "svc@host.example.test")


async def test_a_failed_install_aborts_the_node_with_no_restart_and_no_version_recorded(monkeypatch):
    world = _World(monkeypatch, fail={"install"})
    outcome = await _sync(world)
    assert outcome.plan.aborted and _restarts(world.events) == []
    assert any(label.startswith("Restart") for label in outcome.plan.skipped)
    world.orch.record_role_synced.assert_not_awaited()


async def test_a_failed_restart_is_recorded_and_reported_but_does_not_fail_the_sync(monkeypatch):
    world = _World(monkeypatch, fail={"ollama"})
    outcome = await _sync(world)
    assert not outcome.plan.aborted
    assert [r["success"] for r in outcome.plan.rows if r["label"] == "Restart ollama"] == [False]
    assert node_post_sync._outcome_ok(outcome)
    assert _restarts(world.events)[-1] == "autobot-slm-backend"  # later restarts still run


async def test_restart_false_plans_no_restart(monkeypatch):
    world = _World(monkeypatch)
    await _sync(world, restart=False)
    assert _restarts(world.events) == []


async def test_a_role_whose_files_fail_is_reported_and_left_out_of_the_plan(monkeypatch):
    world = _World(monkeypatch)
    world.orch.sync_role_files = AsyncMock(
        side_effect=lambda n, r, c: (False, "Commit not cached", None) if r == "autobot-llm-cpu" else (True, "OK", _CTX)
    )
    outcome = await _sync(world)
    assert [r["success"] for r in outcome.roles].count(False) == 1
    assert not node_post_sync._outcome_ok(outcome)
    assert world.orch.record_role_synced.await_count == len(_ROLES) - 1


async def test_role_sync_goes_through_the_same_plan_with_one_run_id_across_nodes(monkeypatch):
    world = _World(monkeypatch)
    monkeypatch.setattr(node_post_sync, "_slm_host_node_id", AsyncMock(return_value=None))
    node_roles = [SimpleNamespace(node_id="n1"), SimpleNamespace(node_id="n2")]
    results, ok_count, run_id, actions = await node_post_sync.sync_role_on_nodes(
        node_roles, "autobot-ai-stack", "c1", True
    )
    assert re.fullmatch(r"[0-9a-f]{32}", run_id)
    assert ok_count == 2 and [r["node_id"] for r in results] == ["n1", "n2"]
    assert all(set(r) == {"node_id", "success", "message"} for r in results)
    assert len(actions) == 4  # install + restart on each node
    assert _restarts(world.events) == ["autobot-ai-stack", "autobot-ai-stack"]


# ---- routes ---------------------------------------------------------------------------------

_BEARER = HTTPBearer()
_SIGNED_IN = {"Authorization": "Bearer test-token"}


async def _requires_bearer(credentials: HTTPAuthorizationCredentials = Depends(_BEARER)) -> dict:
    return {"sub": "tester"}


class _Db:
    def __init__(self, scalars):
        self._queue = list(scalars)

    async def execute(self, _statement):
        value = self._queue.pop(0)
        return SimpleNamespace(
            scalar_one_or_none=lambda: value,
            scalars=lambda: SimpleNamespace(all=lambda: value),
        )


def _client(db) -> TestClient:
    app = FastAPI()
    app.include_router(node_post_sync.router, prefix="/api/nodes")
    app.include_router(node_post_sync.runs_router, prefix="/api/code-sync")

    async def _get_db():
        yield db

    app.dependency_overrides[node_post_sync.get_db] = _get_db
    app.dependency_overrides[node_post_sync.get_current_user] = _requires_bearer
    return TestClient(app)


_ROW = SimpleNamespace(
    run_id="run1",
    node_id="n1",
    role_name="r",
    category="restart",
    label="Restart a",
    command="c",
    units="a",
    started_at=_NOW,
    finished_at=_NOW,
    exit_code=0,
    success=True,
    output_tail="",
    error=None,
)


def test_get_returns_the_recorded_rows():
    body = _client(_Db([[_ROW, _ROW]])).get("/api/code-sync/post-sync-runs/run1", headers=_SIGNED_IN).json()
    assert body["run_id"] == "run1" and [a["label"] for a in body["actions"]] == ["Restart a", "Restart a"]


def test_get_gives_404_for_an_unknown_run():
    assert _client(_Db([[]])).get("/api/code-sync/post-sync-runs/nope", headers=_SIGNED_IN).status_code == 404


def test_node_sync_gives_404_for_an_unknown_node():
    assert _client(_Db([None])).post("/api/nodes/ghost/sync", headers=_SIGNED_IN).status_code == 404


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api/nodes/n1/sync"), ("get", "/api/code-sync/post-sync-runs/run1")],
)
def test_an_anonymous_request_is_refused(method, path):
    response = getattr(_client(_Db([])), method)(path)
    assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)


# ---- auth parity with POST /roles/{role_name}/sync -----------------------------------------


def _depends_get_current_user(path: Path, function: str) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    func = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == function)
    return "Depends(get_current_user)" in ast.unparse(func.args)


def test_all_three_routes_carry_the_same_user_dependency():
    api = SLM_ROOT / "api"
    assert _depends_get_current_user(api / "code_sync.py", "sync_role")
    assert _depends_get_current_user(api / "node_post_sync.py", "sync_node_post_sync_plan")
    assert _depends_get_current_user(api / "node_post_sync.py", "get_post_sync_run")


def test_both_new_routers_are_mounted_on_routers_main_gates_with_the_role_sync_dependency():
    init = (SLM_ROOT / "api" / "__init__.py").read_text(encoding="utf-8")
    assert "nodes_router.include_router(node_post_sync_router)" in init
    assert "code_sync_router.include_router(post_sync_runs_router)" in init
    main = (SLM_ROOT / "main.py").read_text(encoding="utf-8")
    for router in ("nodes_router", "code_sync_router"):
        assert f'app.include_router({router}, prefix="/api", dependencies=_SM_OR_AGENT)' in main
