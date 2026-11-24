# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The fleet update provisions a newly assigned vnc role after update-all-nodes.yml (#22211).

Covers the selection rule, the retry cooldown, the status transitions against a fake db session, and
that a provisioning failure is a warning on a node whose code update succeeded.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import inspect
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _real_load():
    """The real module: the suite's conftest stubs the `services` package with mocks (#14307)."""
    path = _ROOT / "services" / "pending_role_provisioning.py"
    spec = importlib.util.spec_from_file_location("_pending_role_provisioning_real", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prp = _real_load()
COOLDOWN = timedelta(hours=prp.RETRY_COOLDOWN_HOURS)


def _role(status: str, age: timedelta = timedelta(days=30), name: str = "vnc"):
    return SimpleNamespace(role_name=name, status=status, updated_at=datetime.now(timezone.utc) - age)


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    monkeypatch.setattr(prp, "no_restart_args", lambda restart: {})
    monkeypatch.setattr(prp, "select", lambda *a, **k: MagicMock())


# --------------------------------------------------------------------------
# selection rule
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("status", "creds", "needs"),
    [
        ("not_installed", {"vnc"}, True),  # assigned, never provisioned
        ("failed", {"vnc"}, True),  # a failed run is retried once the cooldown passed
        ("active", set(), True),  # row reads active, no VNC credential registered
        ("installed", {"ssh"}, True),  # other credential types do not count
        ("installing", {"vnc"}, True),  # a crash left it here and the cooldown passed
        ("active", {"vnc"}, False),  # provisioned and registered: left alone
        ("installed", {"vnc"}, False),
    ],
)
def test_the_vnc_role_is_provisioned_when_pending_or_without_a_vnc_credential(status, creds, needs) -> None:
    assert prp._needs_provisioning(_role(status), creds) is needs


def test_a_role_that_registers_no_credential_is_only_pending_by_status() -> None:
    assert prp._needs_provisioning(_role("active", name="other"), set()) is False
    assert prp._needs_provisioning(_role("not_installed", name="other"), set()) is True


@pytest.mark.parametrize("status", ["failed", "installing", "active", "installed"])
def test_a_recent_attempt_is_not_repeated_inside_the_cooldown(status) -> None:
    assert prp._needs_provisioning(_role(status, age=COOLDOWN / 2), set()) is False
    assert prp._needs_provisioning(_role(status, age=COOLDOWN + timedelta(minutes=1)), set()) is True


def test_a_fresh_assignment_is_not_held_by_the_cooldown() -> None:
    assert prp._needs_provisioning(_role("not_installed", age=timedelta(seconds=1)), set()) is True


def test_only_vnc_is_provisioned_by_the_updater_and_the_credential_must_be_active() -> None:
    assert prp.UPDATER_PROVISIONED_ROLES == ("vnc",)
    assert set(prp.PENDING_STATUSES) == {"not_installed", "failed"}
    assert "is_active.is_(True)" in inspect.getsource(prp._credential_types)
    assert "is_active = Column" in (_ROOT / "models" / "database.py").read_text(encoding="utf-8")


def test_the_cooldown_is_registered_and_env_backed() -> None:
    registry = (_ROOT.parent / "autobot_shared" / "env_registry_slm_roles.py").read_text(encoding="utf-8")
    assert "SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS" in registry
    assert "SLM_ROLE_PROVISION_RETRY_COOLDOWN_HOURS" in inspect.getsource(prp)
    assert "env_registry_slm_roles" in (_ROOT.parent / "autobot_shared" / "env_registry_slm.py").read_text(
        encoding="utf-8"
    )


# --------------------------------------------------------------------------
# status transitions against a fake session
# --------------------------------------------------------------------------
def _fake_db(roles: list, creds: list[str] | None = None, node: object = "node"):
    """A session whose three queries answer: the role rows, the credential types, the node."""
    roles_res, creds_res, node_res = MagicMock(), MagicMock(), MagicMock()
    roles_res.scalars.return_value.all.return_value = roles
    creds_res.all.return_value = [(c,) for c in (creds or [])]
    node_res.scalar_one_or_none.return_value = node
    db = MagicMock()
    db.execute = AsyncMock(side_effect=[roles_res, creds_res, node_res])
    db.commit = AsyncMock()
    return db


def _use(monkeypatch, db, helper):
    @contextlib.asynccontextmanager
    async def session():
        yield db

    monkeypatch.setattr(prp, "db_service", SimpleNamespace(session=session))
    monkeypatch.setitem(sys.modules, "api.nodes", types.SimpleNamespace(_execute_provision_playbook=helper))


def test_pending_to_installing_to_installed_on_success(monkeypatch) -> None:
    role = _role("not_installed")
    seen: list[str] = []

    async def helper(db, node_id, node, roles, names):
        seen.append(roles[0].status)  # what the row reads while provisioning runs
        roles[0].status = "installed"

    _use(monkeypatch, _fake_db([role]), helper)
    message = asyncio.run(prp.provision_pending_roles("n1"))
    assert seen == ["installing"] and role.status == "installed"
    assert "provisioned newly assigned role(s) vnc" in message


def test_failure_leaves_the_row_failed_and_is_a_warning(monkeypatch) -> None:
    role = _role("active")

    async def helper(db, node_id, node, roles, names):
        roles[0].status = "failed"
        raise RuntimeError("provisioning failed")

    _use(monkeypatch, _fake_db([role]), helper)
    message = asyncio.run(prp.provision_pending_roles("n1"))
    assert role.status == "failed" and message.startswith("WARNING") and "code update succeeded" in message


def test_a_crash_never_leaves_the_row_at_installing(monkeypatch) -> None:
    role = _role("not_installed")
    db = _fake_db([role])

    async def helper(db_, node_id, node, roles, names):
        raise asyncio.CancelledError()

    _use(monkeypatch, db, helper)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(prp.provision_pending_roles("n1"))
    assert role.status == "failed", "the finally resets it"
    assert db.commit.await_count == 2, "installing, then the reset"


def test_repeated_failure_is_retried_only_after_the_cooldown(monkeypatch) -> None:
    role = _role("active", age=timedelta(days=30))
    calls: list[int] = []

    async def helper(db, node_id, node, roles, names):
        calls.append(1)
        roles[0].status = "failed"
        roles[0].updated_at = datetime.now(timezone.utc)  # what the column's onupdate does
        raise RuntimeError("registration keeps failing")

    for _ in range(3):  # three fleet updates in a row
        _use(monkeypatch, _fake_db([role]), helper)
        asyncio.run(prp.provision_pending_roles("n1"))
    assert len(calls) == 1, "the 2nd and 3rd updates are inside the cooldown"
    role.updated_at = datetime.now(timezone.utc) - COOLDOWN - timedelta(minutes=1)
    _use(monkeypatch, _fake_db([role]), helper)
    asyncio.run(prp.provision_pending_roles("n1"))
    assert len(calls) == 2, "retried once the cooldown has passed"


def test_a_node_with_nothing_pending_runs_nothing(monkeypatch) -> None:
    async def helper(*a):
        raise AssertionError("must not provision")

    _use(monkeypatch, _fake_db([_role("active")], creds=["vnc"]), helper)
    assert asyncio.run(prp.provision_pending_roles("n1")) == ""


# --------------------------------------------------------------------------
# the update itself
# --------------------------------------------------------------------------
class _Executor:
    def __init__(self, success: bool = True):
        self.success = success
        self.calls: list[dict] = []

    async def execute_playbook(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": self.success, "output": "ran"}


def _run(executor, monkeypatch, message, **kwargs):
    async def fake(node_id):
        return message

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    return asyncio.run(prp.run_update_all_nodes(executor, "n1", ["localhost", "n1"], True, **kwargs))


def test_pending_roles_are_provisioned_after_a_successful_update(monkeypatch) -> None:
    ex = _Executor()
    result = _run(ex, monkeypatch, "provisioned newly assigned role(s) vnc", progress_callback="cb")
    assert ex.calls[0]["playbook_name"] == "update-all-nodes.yml" and ex.calls[0]["progress_callback"] == "cb"
    assert result["success"] is True and "provisioned newly assigned role(s) vnc" in result["output"]


def test_a_provisioning_failure_does_not_fail_a_successful_code_update(monkeypatch) -> None:
    result = _run(_Executor(), monkeypatch, "WARNING: provisioning of role(s) vnc failed; the code update succeeded")
    assert result["success"] is True and "WARNING" in result["output"]


def test_a_failed_update_provisions_nothing(monkeypatch) -> None:
    async def boom(node_id):
        raise AssertionError("must not provision after a failed update")

    monkeypatch.setattr(prp, "provision_pending_roles", boom)
    result = asyncio.run(prp.run_update_all_nodes(_Executor(success=False), "n1", [], False))
    assert result["success"] is False


def test_both_sync_paths_go_through_the_helper() -> None:
    src = (_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    assert src.count("run_update_all_nodes(") == 2
