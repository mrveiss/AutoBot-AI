# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every caller-written inventory loads the real group_vars (#19202).

api/nodes.py wrote its provision and decommission inventories into the ansible root, which
has no group_vars sibling, and execute_playbook links group_vars only for inventories it
builds itself, so those plays ran without autobot.base_dir or the role_*_active facts.
Both now go through services.temp_inventory.write_linked_inventory, as the wizard does.

The callers run here for real with the executor faked. At the moment the play would start,
the inventory's group_vars must resolve and define autobot.base_dir.
"""

from __future__ import annotations

import asyncio
import importlib
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from testkit.fake_async_session import FakeAsyncSession

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "api"))
_orm = importlib.import_module("_real_orm_import")  # sibling helper in tests/api
SLM_ROOT = _orm.SLM_ROOT
# `services` is a stub package in this harness; the helper's link must be the real one.
_playbook_executor, temp_inventory, nodes = _orm.import_modules_with_real_orm(
    ("services.temp_inventory", "api.nodes"),
    path_loaded={"services.playbook_executor": SLM_ROOT / "services" / "playbook_executor.py"},
)

_ANSIBLE = SLM_ROOT / "ansible"


def _base_dir_seen_from(inventory: Path) -> str:
    """autobot.base_dir as Ansible resolves group_vars for *inventory* (its sibling dir)."""
    all_yml = inventory.parent / "group_vars" / "all.yml"
    assert all_yml.is_file(), f"{inventory} has no group_vars sibling: Ansible loads no group_vars"
    return yaml.safe_load(all_yml.read_text(encoding="utf-8"))["autobot"]["base_dir"]


@pytest.fixture
def scratch(tmp_path, monkeypatch) -> Path:
    tmp = tmp_path / "ansible_tmp"
    monkeypatch.setattr(temp_inventory, "ANSIBLE_LOCAL_TMP", str(tmp))
    return tmp


def test_the_helper_links_group_vars_outside_the_code_tree(scratch) -> None:
    inv = temp_inventory.write_linked_inventory("all:\n  hosts: {}\n", "t_inv_", _ANSIBLE)
    assert inv.parent == scratch and not inv.is_relative_to(_ANSIBLE)
    assert inv.read_text(encoding="utf-8") == "all:\n  hosts: {}\n"
    assert (inv.parent / "group_vars").resolve() == (_ANSIBLE / "inventory" / "group_vars").resolve()
    assert _base_dir_seen_from(inv) == "/opt/autobot"


def test_a_missing_group_vars_source_raises_and_leaves_no_inventory(scratch, tmp_path) -> None:
    empty = tmp_path / "ansible_without_group_vars"
    empty.mkdir()
    with pytest.raises(RuntimeError, match="group_vars"):
        temp_inventory.write_linked_inventory("all:\n  hosts: {}\n", "t_inv_", empty)
    assert list(scratch.glob("t_inv_*")) == []


def test_a_failed_link_raises_and_leaves_no_inventory(scratch, monkeypatch) -> None:
    monkeypatch.setattr(temp_inventory, "link_group_vars", lambda *_a: None)  # best-effort link that did nothing
    with pytest.raises(RuntimeError, match="group_vars"):
        temp_inventory.write_linked_inventory("all:\n  hosts: {}\n", "t_inv_", _ANSIBLE)
    assert list(scratch.glob("t_inv_*")) == []


def test_a_group_vars_dir_pointing_elsewhere_is_refused(scratch, monkeypatch, tmp_path) -> None:
    other = tmp_path / "other_group_vars"
    other.mkdir()

    def _link_wrong(inventory, _ansible_dir) -> None:
        (inventory.parent / "group_vars").symlink_to(other)

    monkeypatch.setattr(temp_inventory, "link_group_vars", _link_wrong)
    with pytest.raises(RuntimeError, match="group_vars"):
        temp_inventory.write_linked_inventory("all:\n  hosts: {}\n", "t_inv_", _ANSIBLE)


class _Executor:
    """Records what each playbook run would have seen, then succeeds."""

    def __init__(self) -> None:
        self.ansible_dir = _ANSIBLE
        self.seen: list[tuple[str, str, Path]] = []

    async def execute_playbook(self, playbook_name, inventory_path, extra_vars=None):
        self.seen.append((playbook_name, _base_dir_seen_from(inventory_path), inventory_path))
        text = await asyncio.to_thread(inventory_path.read_text, encoding="utf-8")
        target = yaml.safe_load(text)["all"]["hosts"]
        return {"success": True, "output": " ".join(target)}


@pytest.fixture
def executor(monkeypatch, scratch) -> _Executor:
    ex = _Executor()
    monkeypatch.setattr("services.playbook_executor.get_playbook_executor", lambda: ex)
    return ex


def test_the_decommission_run_sees_autobot_base_dir_from_group_vars(executor) -> None:
    result = asyncio.run(nodes._run_decommission_playbook("node.example.test", "svc", False))
    assert result["success"], result
    [(playbook, base_dir, inventory)] = executor.seen
    assert (playbook, base_dir) == ("playbooks/decommission-node.yml", "/opt/autobot")
    assert not inventory.exists(), "the temp inventory was left behind"


def test_the_provision_run_sees_autobot_base_dir_from_group_vars(executor) -> None:
    node = SimpleNamespace(ssh_user="svc", ip_address="node.example.test", hostname="node")
    roles = [SimpleNamespace(status="pending")]
    result = asyncio.run(nodes._execute_provision_playbook(FakeAsyncSession(), "n1", node, roles, ["backend"]))
    assert result["success"], result
    [(playbook, base_dir, inventory)] = executor.seen
    assert (playbook, base_dir) == ("playbooks/provision-fleet-roles.yml", "/opt/autobot")
    assert not inventory.exists(), "the temp inventory was left behind"


def test_contrast_an_inventory_in_the_ansible_root_sees_no_group_vars(tmp_path) -> None:
    """The pre-#19202 placement: no sibling, so the check above fails on it."""
    root = tmp_path / "ansible"
    shutil.copytree(_ANSIBLE / "inventory" / "group_vars", root / "inventory" / "group_vars")
    bare = root / "decommission_inv_x.yml"
    bare.write_text("all:\n  hosts: {}\n", encoding="utf-8")
    with pytest.raises(AssertionError, match="no group_vars sibling"):
        _base_dir_seen_from(bare)


# Resolved on the test's own PATH (a venv bin in CI): the run below passes a minimal PATH,
# so the bare name would not be found there even when the binary exists.
_ANSIBLE_INVENTORY = shutil.which("ansible-inventory")


@pytest.mark.skipif(_ANSIBLE_INVENTORY is None, reason="ansible not installed")
def test_ansible_itself_resolves_autobot_base_dir_for_a_linked_inventory(scratch) -> None:
    inv = temp_inventory.write_linked_inventory(
        "all:\n  hosts:\n    decommission_target:\n      ansible_host: node.example.test\n", "t_inv_", _ANSIBLE
    )
    out = subprocess.run(
        [_ANSIBLE_INVENTORY, "-i", str(inv), "--host", "decommission_target"],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "ANSIBLE_LOG_PATH": "/dev/null", "HOME": str(scratch)},
    )
    assert out.returncode == 0, out.stderr[-500:]
    assert yaml.safe_load(out.stdout)["autobot"]["base_dir"] == "/opt/autobot"
