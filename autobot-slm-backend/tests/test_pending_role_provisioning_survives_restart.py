# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A single-node self-update restart does not lose the node's pending-role provisioning (#22211).

The detached run cuts its waiter with the restart, so the provisioning step after it would run in the process
being replaced. The node is marked in Settings first; the restarted process takes the marker (once), waits for
the unit to finish, and provisions only when the update completed.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import signal
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _real_load(name: str):
    spec = importlib.util.spec_from_file_location(f"_real_{name}", _ROOT / "services" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


resume = _real_load("pending_role_resume")
prp = _real_load("pending_role_provisioning")


class _Setting:
    key = MagicMock()  # `Setting.key == ...` is built into the (stubbed) query

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class _Store:
    """The one Settings row, as a session sees it."""

    def __init__(self):
        self.row = None

    def session(self):
        store = self

        @contextlib.asynccontextmanager
        async def _session():
            db = MagicMock()
            result = MagicMock()
            result.scalar_one_or_none.side_effect = lambda: store.row
            db.execute = AsyncMock(return_value=result)
            db.add = lambda obj: setattr(store, "row", obj)
            db.delete = AsyncMock(side_effect=lambda obj: setattr(store, "row", None))
            db.commit = AsyncMock()
            yield db

        return _session()


@pytest.fixture
def store(monkeypatch):
    s = _Store()
    monkeypatch.setattr(resume, "db_service", SimpleNamespace(session=s.session))
    monkeypatch.setattr(resume, "select", lambda *a, **k: MagicMock())
    monkeypatch.setattr(resume, "Setting", _Setting)
    monkeypatch.setitem(sys.modules, "services.pending_role_resume", resume)
    monkeypatch.setattr(prp, "no_restart_args", lambda restart: {})
    return s


def _cut():
    return {"detached": True, "returncode": -signal.SIGTERM, "timed_out": False, "success": False, "output": ""}


def _install_resume_plan(monkeypatch):
    def cut(result, node_id):  # services' stand-in for api._resume_plan.restart_cut_the_wait
        return bool(result.get("detached")) and result.get("returncode") == -signal.SIGTERM

    monkeypatch.setitem(sys.modules, "api._resume_plan", types.SimpleNamespace(restart_cut_the_wait=cut))


class _Executor:
    def __init__(self, result):
        self.result = result

    async def execute_playbook(self, **kwargs):
        return self.result


def test_mark_and_clear_round_trip(store) -> None:
    asyncio.run(resume.mark_provision_after_restart("n1"))
    asyncio.run(resume.mark_provision_after_restart("n2"))
    assert set(resume._decode(store.row)) == {"n1", "n2"}
    asyncio.run(resume.clear_provision_marker("n1"))
    assert set(resume._decode(store.row)) == {"n2"}
    asyncio.run(resume.clear_provision_marker("n2"))
    assert store.row is None, "an empty marker set leaves no row"


def test_markers_are_taken_once(store) -> None:
    asyncio.run(resume.mark_provision_after_restart("n1"))
    assert set(asyncio.run(resume.take_markers())) == {"n1"}
    assert asyncio.run(resume.take_markers()) == {}, "gone after the first take: once only"


def _resume_env(monkeypatch, completed: bool):
    calls: list[str] = []

    async def provision(node_id, **kw):
        calls.append(node_id)
        return "provisioned newly assigned role(s) vnc"

    async def read():
        return SimpleNamespace(in_progress=False)

    monkeypatch.setitem(
        sys.modules, "services.pending_role_provisioning", types.SimpleNamespace(provision_pending_roles=provision)
    )
    monkeypatch.setitem(
        sys.modules,
        "api._resume_wait",
        types.SimpleNamespace(resolve_completion_time=lambda activity, since: "t" if completed else None),
    )
    monkeypatch.setitem(
        sys.modules,
        "api.code_sync",
        types.SimpleNamespace(_SELF_UPDATE_WATCH_POLL_SECONDS=0, _SELF_UPDATE_WATCH_TIMEOUT_SECONDS=1),
    )
    monkeypatch.setitem(sys.modules, "services.deploy_activity", types.SimpleNamespace(read_deploy_activity=read))
    return calls


def test_a_persisted_marker_is_provisioned_on_resume_exactly_once(store, monkeypatch) -> None:
    calls = _resume_env(monkeypatch, completed=True)
    asyncio.run(resume.mark_provision_after_restart("n1"))
    asyncio.run(resume.provision_marked_nodes())
    asyncio.run(resume.provision_marked_nodes())  # a second restart finds nothing
    assert calls == ["n1"]


def test_a_self_update_that_did_not_complete_provisions_nothing(store, monkeypatch) -> None:
    calls = _resume_env(monkeypatch, completed=False)
    asyncio.run(resume.mark_provision_after_restart("n1"))
    asyncio.run(resume.provision_marked_nodes())
    assert calls == [] and store.row is None, "consumed, not retried forever"


def test_a_failure_on_resume_is_a_warning_not_an_exception(store, monkeypatch) -> None:
    _resume_env(monkeypatch, completed=True)

    async def boom(node_id, **kw):
        raise RuntimeError("provisioning exploded")

    monkeypatch.setitem(
        sys.modules, "services.pending_role_provisioning", types.SimpleNamespace(provision_pending_roles=boom)
    )
    asyncio.run(resume.mark_provision_after_restart("n1"))
    asyncio.run(resume.provision_marked_nodes())  # must not raise


def test_a_run_cut_by_the_restart_leaves_the_marker_and_provisions_nothing_here(store, monkeypatch) -> None:
    _install_resume_plan(monkeypatch)
    called: list[str] = []

    async def fake(node_id, **kw):
        called.append(node_id)
        return ""

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    result = asyncio.run(prp.run_update_all_nodes(_Executor(_cut()), "n1", [], True, resume_after_restart=True))
    # #22262: the step before the play runs here; the one after it is the restarted process's
    assert called == ["n1"] and set(resume._decode(store.row)) == {"n1"}, "the restarted process owns it now"
    assert result["returncode"] == -signal.SIGTERM


def test_a_run_that_ends_in_this_process_clears_the_marker_and_provisions_here(store, monkeypatch) -> None:
    _install_resume_plan(monkeypatch)
    called: list[str] = []

    async def fake(node_id, **kw):
        called.append(node_id)
        return "provisioned"

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    ok = {"success": True, "output": "ran", "detached": True, "returncode": 0}
    asyncio.run(prp.run_update_all_nodes(_Executor(ok), "n1", [], True, resume_after_restart=True))
    assert called == ["n1", "n1"] and store.row is None  # before the play (#22262) and after it


def test_a_failed_run_clears_the_marker_and_provisions_nothing(store, monkeypatch) -> None:
    _install_resume_plan(monkeypatch)

    called: list[str] = []

    async def fake(node_id, **kw):
        called.append(node_id)
        return ""

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    bad = {"success": False, "output": "x", "detached": True, "returncode": 2}
    asyncio.run(prp.run_update_all_nodes(_Executor(bad), "n1", [], True, resume_after_restart=True))
    assert store.row is None and called == ["n1"], "only the step before the play (#22262), none after a failure"


def test_the_startup_hook_and_the_self_update_path_are_wired() -> None:
    src = (_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    assert "resume_after_restart=True" in src
    start = src.index("async def resume_update_all_orchestration")
    assert "schedule_marked_provisioning()" in src[start : start + 1500]
