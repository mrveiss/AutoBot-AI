# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every caller-written inventory loads the real group_vars (#19202).

api/nodes.py wrote its provision and decommission inventories into the ansible root, which
has no group_vars sibling, and execute_playbook links group_vars only for inventories it
builds itself, so those plays ran without autobot.base_dir or the role_*_active facts.
Both now go through services.temp_inventory.write_linked_inventory, as the wizard does.

The provision inventory also carries the SLM manager host, exactly as the fleet update
inventory gives it, so a role's ``delegate_to: slm_manager_inventory_host`` resolves (#22262).

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
_playbook_executor, temp_inventory, provision_inventory, nodes = _orm.import_modules_with_real_orm(
    ("services.temp_inventory", "services.provision_inventory", "api.nodes"),
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
        self.limits: list = []

    async def execute_playbook(self, playbook_name, inventory_path, extra_vars=None, limit=None):
        self.seen.append((playbook_name, _base_dir_seen_from(inventory_path), inventory_path))
        self.limits.append(limit)
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
    node = SimpleNamespace(ssh_user="svc", ip_address="node.example.test", hostname="node", ssh_port=22)
    roles = [SimpleNamespace(status="pending")]
    result = asyncio.run(nodes._execute_provision_playbook(FakeAsyncSession(), "n1", node, roles, ["backend"]))
    assert result["success"], result
    [(playbook, base_dir, inventory)] = executor.seen
    assert (playbook, base_dir) == ("playbooks/provision-fleet-roles.yml", "/opt/autobot")
    assert not inventory.exists(), "the temp inventory was left behind"
    assert executor.limits == [["provision_target"]], "the SLM manager host must never be provisioned (#22262)"


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


# -- #22262: the SLM manager host roles delegate to ------------------------------------------

_MANAGER_IP = "manager.example.test"


def _fleet() -> list:
    """The SLM manager (local to the SLM) and the node being provisioned, as Node rows."""

    def _row(node_id, ip, roles):
        return SimpleNamespace(
            node_id=node_id, ip_address=ip, ssh_user="svc", ssh_port=22, roles=roles, detected_roles=[]
        )

    return [_row("mgr", _MANAGER_IP, ["slm-backend"]), _row("n1", "node.example.test", ["vnc"])]


def _provision_hosts() -> dict:
    target = SimpleNamespace(ssh_user="svc", ip_address="node.example.test", hostname="node", ssh_port=22)
    text = provision_inventory.build_provision_inventory("n1", target, ["vnc"], _fleet(), _is_manager_ip)
    return yaml.safe_load(text)["all"]


def _is_manager_ip(ip: str) -> bool:
    return ip == _MANAGER_IP


def test_the_provision_inventory_carries_the_slm_manager_with_the_update_inventorys_vars() -> None:
    """#22262: delegate_to the SLM was UNREACHABLE because the manager host was missing."""
    update = provision_inventory.build_registry_inventory(_fleet(), _is_manager_ip)["all"]
    assert list(update["children"]["slm_server"]["hosts"]) == ["mgr"]
    inv = _provision_hosts()
    assert list(inv["children"]["slm_server"]["hosts"]) == ["mgr"]
    assert inv["hosts"]["mgr"] == {**update["vars"], **update["hosts"]["mgr"]}
    assert inv["hosts"]["mgr"]["ansible_connection"] == "local"


def test_the_provision_target_keeps_its_own_vars_and_the_update_inventorys_key() -> None:
    """#22262: only the node is provisioned; its SSH key is the one the fleet update connects with."""
    target = _provision_hosts()["hosts"]["provision_target"]
    assert (target["slm_node_id"], target["node_hostname"], target["node_roles"]) == ("n1", "node", ["vnc"])
    assert target["ansible_ssh_private_key_file"] == provision_inventory.config.path.ssh_key_path
    assert "ansible_connection" not in target


def _build_for(fleet: list, ssh_port: int | None = None) -> dict:
    target = SimpleNamespace(ssh_user="svc", ip_address="node.example.test", hostname="node", ssh_port=ssh_port)
    text = provision_inventory.build_provision_inventory("n1", target, ["vnc"], fleet, _is_manager_ip)
    return yaml.safe_load(text)["all"]


def test_two_managers_keep_the_update_inventorys_sorted_order() -> None:
    """#22262: slm_server[0] is the same host in the provision and the update inventory."""
    fleet = _fleet()
    fleet.insert(0, SimpleNamespace(**{**vars(fleet[0]), "node_id": "aaa"}))
    fleet.insert(0, SimpleNamespace(**{**vars(fleet[0]), "node_id": "zzz"}))
    inv = _build_for(fleet)
    assert list(inv["children"]["slm_server"]["hosts"]) == ["aaa", "mgr", "zzz"]
    assert list(inv["hosts"])[0] == "provision_target"


def test_no_manager_row_logs_a_warning_naming_the_consequence(monkeypatch) -> None:
    warnings: list[str] = []
    monkeypatch.setattr(provision_inventory.logger, "warning", lambda msg, *a: warnings.append(msg % a))
    inv = _build_for([r for r in _fleet() if r.node_id != "mgr"])
    assert "slm_server" in inv["children"]
    assert len(warnings) == 1 and "unreachable" in warnings[0]


def test_the_target_carries_the_nodes_ssh_port() -> None:
    assert _build_for(_fleet(), 2222)["hosts"]["provision_target"]["ansible_port"] == 2222
    assert _build_for(_fleet(), None)["hosts"]["provision_target"]["ansible_port"] == 22


def test_a_manager_host_named_like_the_target_is_refused() -> None:
    """#22262: a manager named provision_target would replace the target's vars in the hosts map."""
    fleet = _fleet()
    fleet.append(SimpleNamespace(**{**vars(fleet[0]), "node_id": "provision_target"}))
    with pytest.raises(ValueError, match="provision_target"):
        _build_for(fleet)


def test_the_decommission_inventory_quotes_a_key_path_with_a_yaml_comment(monkeypatch) -> None:
    """#22262: an unquoted ``fleet #1`` key path loaded as ``fleet``; the serializer quotes it."""
    monkeypatch.setattr(provision_inventory.config.path, "ssh_key_path", "/etc/autobot/ssh/fleet #1")
    text = provision_inventory.build_decommission_inventory("10.0.0.5", "svc")
    host = yaml.safe_load(text)["all"]["hosts"]["decommission_target"]
    assert host["ansible_ssh_private_key_file"] == "/etc/autobot/ssh/fleet #1"
    assert (host["ansible_host"], host["ansible_user"]) == ("10.0.0.5", "svc")


def test_provision_inventory_for_builds_off_the_loop_from_plain_values(monkeypatch) -> None:
    """#22262: the blocking locality checks run in a worker thread on copies, not ORM rows."""
    import threading

    seen: dict = {}

    def _spy(node_id, node, roles, nodes, check):
        seen.update(thread=threading.current_thread(), node=node, nodes=nodes)
        return "inv"

    class _Result:
        def scalars(self):
            return SimpleNamespace(all=lambda: _fleet())

    class _Db:
        async def execute(self, _stmt):
            return _Result()

    monkeypatch.setattr(provision_inventory, "build_provision_inventory", _spy)
    target = SimpleNamespace(ssh_user="svc", ip_address="node.example.test", hostname="node", ssh_port=22)
    out = asyncio.run(provision_inventory.provision_inventory_for(_Db(), "n1", target, ["vnc"]))
    assert out == "inv"
    assert seen["thread"] is not threading.main_thread()
    assert all(type(n) is SimpleNamespace for n in [seen["node"], *seen["nodes"]])
    assert [n.node_id for n in seen["nodes"]] == ["mgr", "n1"] and seen["node"].hostname == "node"


_ANSIBLE_ADHOC = shutil.which("ansible")


@pytest.mark.skipif(_ANSIBLE_ADHOC is None, reason="ansible not installed")
def test_ansible_resolves_the_delegate_target_to_the_manager_host(scratch) -> None:
    """#22262: ``slm_manager_inventory_host`` (group_vars) names a host this inventory defines."""
    target = SimpleNamespace(ssh_user="svc", ip_address="node.example.test", hostname="node", ssh_port=22)
    text = provision_inventory.build_provision_inventory("n1", target, ["vnc"], _fleet(), _is_manager_ip)
    inv = temp_inventory.write_linked_inventory(text, "t_inv_", _ANSIBLE)
    host = "slm_manager_inventory_host | trim"
    expr = f"{{{{ {host} }}}}|{{{{ hostvars[{host}].ansible_connection }}}}"
    out = subprocess.run(
        [_ANSIBLE_ADHOC, "-i", str(inv), "provision_target", "-o", "-m", "debug", "-a", f"msg={expr}"],
        capture_output=True,
        text=True,
        timeout=120,
        env={"PATH": "/usr/bin:/bin", "ANSIBLE_LOG_PATH": "/dev/null", "HOME": str(scratch)},
    )
    assert out.returncode == 0, out.stdout[-500:] + out.stderr[-500:]
    assert "mgr|local" in out.stdout, out.stdout[-500:]
