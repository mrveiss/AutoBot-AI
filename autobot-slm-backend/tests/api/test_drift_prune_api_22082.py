# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour of the drift-prune endpoints (#22082) through a real FastAPI app.

``api/drift_prune.py`` is loaded by path with its collaborators stubbed (the package
conftest replaces ``services``/``models`` with spec-less mocks), mirroring
``test_chat_approval_settings_audit_20465.py``. FastAPI, pydantic and the route bodies are
real. Every stub is withdrawn by ``monkeypatch``.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi import APIRouter, FastAPI, HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from testkit.fake_async_session import FakeAsyncSession  # noqa: E402

_BACKEND = Path(__file__).resolve().parents[2]
_PATHS = ["a.py", "b.py"]


def _module(monkeypatch, name: str, **attrs) -> types.ModuleType:
    mod = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(mod, key, value)
    monkeypatch.setitem(sys.modules, name, mod)
    return mod


class _Db(FakeAsyncSession):
    def __init__(self, events: list) -> None:
        super().__init__()
        self.events = events

    async def commit(self) -> None:
        self.events.append("commit")


@pytest.fixture
def env(monkeypatch):
    state = SimpleNamespace(
        admin=True,
        in_progress=False,
        probe_raises=False,
        audit_raises=False,
        apply_raises=False,
        events=[],
        rows=[],
        apply_calls=[],
    )

    async def _gate() -> dict:
        if not state.admin:
            raise HTTPException(status_code=403, detail="Admin privileges required")
        return {"sub": "alice"}

    async def _get_db():
        yield _Db(state.events)

    async def _probe():
        if state.probe_raises:
            raise OSError("systemctl unavailable")
        return SimpleNamespace(in_progress=state.in_progress, reason="probe")

    async def _audit(db, **kwargs):
        if state.audit_raises:
            raise RuntimeError("audit store down")
        row = SimpleNamespace(**kwargs)
        state.rows.append(row)
        state.events.append("audit")
        return row

    class _Result:
        def __init__(self, component, removed, refused, failed):
            self.component, self.removed, self.refused, self.failed = component, removed, refused, failed

    async def _apply(component, paths, repo_root=None, before_delete=None):
        state.events.append("apply")
        state.apply_calls.append(paths)
        if before_delete is not None:
            await before_delete()
        if state.apply_raises:
            raise RuntimeError("boom")
        return _Result(component, ["a.py"], {"b.py": "not removed_from_source"}, {})

    async def _plan(component, repo_root=None):
        return SimpleNamespace(error=None, files=[("a.py", "abc123")])

    _module(monkeypatch, "sqlalchemy")
    _module(monkeypatch, "sqlalchemy.ext")
    _module(monkeypatch, "sqlalchemy.ext.asyncio", AsyncSession=type("AsyncSession", (), {}))
    _module(monkeypatch, "api")
    _module(monkeypatch, "api.code_sync", router=APIRouter(prefix="/code-sync"))
    _module(monkeypatch, "api.security", create_audit_log=_audit)
    _module(monkeypatch, "autobot_shared")
    _module(monkeypatch, "autobot_shared.auth")
    _module(monkeypatch, "autobot_shared.auth.permissions", Permission=SimpleNamespace(ADMIN_SYSTEM="admin"))
    _module(monkeypatch, "services")
    _module(monkeypatch, "services.auth", require_permission=lambda _p: _gate)
    _module(monkeypatch, "services.database", get_db=_get_db)
    _module(monkeypatch, "services.deploy_activity", read_deploy_activity=_probe)
    _module(monkeypatch, "services.drift_checker", VISIBILITY_COMPONENTS=frozenset({"plugins", "autobot-backend"}))
    _module(
        monkeypatch,
        "services.drift_prune",
        PruneResult=_Result,
        apply_prune=_apply,
        plan_prune=_plan,
        is_prunable_component=lambda c: c in {"plugins", "autobot-backend"},
    )
    spec = importlib.util.spec_from_file_location("_drift_prune_api_under_test_22082", _BACKEND / "api/drift_prune.py")
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    monkeypatch.setitem(sys.modules, "_drift_prune_api_under_test_22082", mod)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]

    app = FastAPI()
    app.include_router(sys.modules["api.code_sync"].router)
    state.client = TestClient(app, raise_server_exceptions=False)
    return state


def _confirm(env, component: str = "plugins"):
    return env.client.post("/code-sync/drift/prune", json={"component": component, "paths": _PATHS})


def test_a_non_admin_gets_403_on_both_routes_and_nothing_runs(env) -> None:
    env.admin = False

    preview = env.client.post("/code-sync/drift/prune/preview", json={"component": "plugins"})
    confirm = _confirm(env)

    assert (preview.status_code, confirm.status_code) == (403, 403)
    assert env.apply_calls == [] and env.rows == []


def test_the_preview_lists_the_files_and_the_plugins_component_is_accepted(env) -> None:
    resp = env.client.post("/code-sync/drift/prune/preview", json={"component": "plugins"})

    assert resp.status_code == 200
    assert resp.json() == {"component": "plugins", "files": [{"path": "a.py", "detail": "abc123"}]}


def test_an_unknown_component_is_400(env) -> None:
    assert _confirm(env, "not-a-component").status_code == 400
    assert env.apply_calls == []


def test_a_running_deploy_is_409_and_nothing_is_audited_or_removed(env) -> None:
    env.in_progress = True

    assert _confirm(env).status_code == 409
    assert env.apply_calls == [] and env.rows == []


def test_an_unknown_deploy_state_refuses(env) -> None:
    env.in_progress = None

    assert _confirm(env).status_code == 409
    assert env.apply_calls == []


def test_a_raising_probe_refuses_and_apply_is_not_called(env) -> None:
    env.probe_raises = True

    resp = _confirm(env)

    assert resp.status_code == 409
    assert env.apply_calls == [] and env.rows == []


def test_the_pending_row_is_committed_before_apply_then_updated_with_the_outcome(env) -> None:
    resp = _confirm(env)

    assert resp.status_code == 200
    assert resp.json()["removed"] == ["a.py"]
    assert env.events[:3] == ["audit", "commit", "apply"], "intent is durable before anything is removed"
    row = env.rows[0]
    assert (row.category, row.action, row.resource_type, row.resource_id) == (
        "deploy",
        "drift_prune",
        "component",
        "plugins",
    )
    assert (row.user_id, row.username) == ("alice", "alice")
    assert row.extra_data["status"] == "completed"
    assert row.extra_data["requested"] == _PATHS
    assert row.extra_data["removed"] == ["a.py"]
    assert row.extra_data["refused"] == {"b.py": "not removed_from_source"}
    assert env.events[-1] == "commit", "the outcome is committed too"


def test_when_the_audit_fails_nothing_is_removed(env) -> None:
    env.audit_raises = True

    resp = _confirm(env)

    assert resp.status_code == 500
    assert env.apply_calls == [], "no deletion without a committed audit row"


def test_a_deploy_that_starts_before_the_delete_aborts_and_the_row_says_so(env) -> None:
    calls = {"n": 0}
    original = sys.modules["services.deploy_activity"].read_deploy_activity

    async def _flip():
        calls["n"] += 1
        env.in_progress = calls["n"] > 1  # idle at the first check, running at the last-moment one
        return await original()

    sys.modules["_drift_prune_api_under_test_22082"].read_deploy_activity = _flip

    resp = _confirm(env)

    assert resp.status_code == 409
    assert env.rows[0].extra_data["status"] == "aborted"
    assert env.rows[0].success is False


def test_a_failing_apply_marks_the_row_aborted(env) -> None:
    env.apply_raises = True

    assert _confirm(env).status_code == 500
    assert env.rows[0].extra_data["status"] == "aborted"


def test_the_module_is_registered_from_full_tree_drift() -> None:
    registrar = (_BACKEND / "api" / "full_tree_drift.py").read_text(encoding="utf-8")
    assert "from api import drift_prune" in registrar
