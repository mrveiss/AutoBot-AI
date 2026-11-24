# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The fleet update provisions a newly assigned vnc role after update-all-nodes.yml (#22211)."""

from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _real_load():
    """The real module: the suite's conftest stubs the `services` package with mocks (#14307)."""
    spec = importlib.util.spec_from_file_location(
        "_pending_role_provisioning_real", _ROOT / "services" / "pending_role_provisioning.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


prp = _real_load()


@pytest.fixture(autouse=True)
def _no_restart_kwargs(monkeypatch):
    monkeypatch.setattr(prp, "no_restart_args", lambda restart: {})


class _Executor:
    def __init__(self, success: bool = True):
        self.success = success
        self.calls: list[dict] = []

    async def execute_playbook(self, **kwargs):
        self.calls.append(kwargs)
        return {"success": self.success, "output": "ran"}


def _run(executor, monkeypatch, outcome):
    async def fake(node_id):
        return outcome

    monkeypatch.setattr(prp, "provision_pending_roles", fake)
    return asyncio.run(prp.run_update_all_nodes(executor, "n1", ["localhost", "n1"], True))


def test_pending_roles_are_provisioned_after_a_successful_update(monkeypatch) -> None:
    ex = _Executor()
    result = _run(ex, monkeypatch, (True, "provisioned newly assigned role(s) vnc"))
    assert ex.calls[0]["playbook_name"] == "update-all-nodes.yml" and ex.calls[0]["limit"] == ["localhost", "n1"]
    assert result["success"] is True and "provisioned newly assigned role(s) vnc" in result["output"]


def test_a_failed_provisioning_fails_the_node_update(monkeypatch) -> None:
    result = _run(_Executor(), monkeypatch, (False, "provisioning of newly assigned role(s) vnc failed"))
    assert result["success"] is False and "failed" in result["output"]


def test_a_failed_update_provisions_nothing(monkeypatch) -> None:
    async def boom(node_id):
        raise AssertionError("must not provision after a failed update")

    monkeypatch.setattr(prp, "provision_pending_roles", boom)
    result = asyncio.run(prp.run_update_all_nodes(_Executor(success=False), "n1", [], False))
    assert result["success"] is False


def test_only_vnc_is_provisioned_by_the_updater_and_failures_are_retried() -> None:
    assert prp.UPDATER_PROVISIONED_ROLES == ("vnc",)
    assert set(prp.PENDING_STATUSES) == {"not_installed", "failed"}


def test_the_fleet_sync_path_goes_through_it() -> None:
    src = (_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    assert "run_update_all_nodes(executor, node_state.node_id, limit, restart)" in src


class _Role:
    def __init__(self, role_name: str, status: str):
        self.role_name, self.status = role_name, status


@pytest.mark.parametrize(
    ("status", "creds", "needs"),
    [
        ("not_installed", {"vnc"}, True),  # assigned, never provisioned
        ("failed", {"vnc"}, True),  # a failed run is retried
        ("active", set(), True),  # row reads active, no VNC credential registered
        ("installed", {"ssh"}, True),  # other credential types do not count
        ("active", {"vnc"}, False),  # provisioned and registered: left alone
        ("installing", {"vnc"}, False),
    ],
)
def test_the_vnc_role_is_provisioned_when_pending_or_without_a_vnc_credential(status, creds, needs) -> None:
    assert prp._needs_provisioning(_Role("vnc", status), creds) is needs


def test_a_role_that_registers_no_credential_is_only_pending_by_status() -> None:
    assert prp._needs_provisioning(_Role("other", "active"), set()) is False
    assert prp._needs_provisioning(_Role("other", "not_installed"), set()) is True


def test_both_sync_paths_go_through_the_helper() -> None:
    src = (_ROOT / "api" / "code_sync.py").read_text(encoding="utf-8")
    assert src.count("run_update_all_nodes(") == 2
