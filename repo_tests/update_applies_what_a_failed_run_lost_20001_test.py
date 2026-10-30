# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""A later update applies what a failed run lost (#20001, #20002).

A run that fails partway loses its notified handlers and has already advanced the deployed-commit
marker. Neither a file diff nor a commit diff can see that afterwards, so both checks ask the live
thing: the running server's setting, and whether the venv satisfies its manifest.
"""

from __future__ import annotations

import shutil
import subprocess

import pytest
import yaml
from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_PLAYBOOK = _ANSIBLE / "playbooks" / "update-all-nodes.yml"
_CONFIG = _ANSIBLE / "roles" / "postgresql" / "tasks" / "config_file.yml"


def _preflight() -> list[dict]:
    return yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))[0]["tasks"]


def _names(tasks: list[dict]) -> list[str]:
    return [str(task.get("name", "")) for task in tasks]


def test_the_python_flag_also_asks_the_installed_venv() -> None:
    tasks = _preflight()
    names = _names(tasks)
    check = next(i for i, name in enumerate(names) if "installed venvs satisfy" in name)
    flags = next(i for i, name in enumerate(names) if "Set dependency change flags" in name)
    assert check < flags, "the flag reads the check before it runs"
    assert tasks[check]["failed_when"] is False, "a failed dry run must not stop an update"
    assert "--dry-run" in tasks[check]["ansible.builtin.shell"]
    expression = str(tasks[flags]["set_fact"]["python_deps_changed"])
    assert "'Would install' in" in expression and "python_tree_check" in expression


def test_a_listen_address_the_server_is_not_running_notifies_the_restart() -> None:
    block = next(task for task in yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) if "block" in task)["block"]
    task = next(t for t in block if "running listen_addresses" in str(t.get("name")))
    assert task["notify"] == "Restart PostgreSQL"
    assert task["failed_when"] is False, "a server that cannot answer must not fail the update"
    assert "postgresql_listen_addresses" in task["changed_when"]
    assert "SHOW listen_addresses" in task["ansible.builtin.command"]["cmd"]


@pytest.mark.skipif(shutil.which("ansible-playbook") is None, reason="ansible-playbook is not installed")
@pytest.mark.parametrize(
    ("running", "rendered", "fires"), [("*", "localhost,fleet-address", True), ("a,b", "a,b", False)]
)
def test_contrast_the_condition_decides_on_the_values(tmp_path, running: str, rendered: str, fires: bool) -> None:
    """The shipped expression, evaluated by Ansible on both a difference and a match."""
    block = next(task for task in yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) if "block" in task)["block"]
    condition = next(t for t in block if "running listen_addresses" in str(t.get("name")))["changed_when"]
    play = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": {"postgresql_listen_addresses": rendered},
            "tasks": [
                {"ansible.builtin.command": {"cmd": f"echo '{running}'"}, "register": "_postgresql_running_listen"},
                {"ansible.builtin.debug": {"msg": "FIRES"}, "when": condition},
            ],
        }
    ]
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump(play), encoding="utf-8")
    done = subprocess.run(
        ["ansible-playbook", "-i", "localhost,", str(path)], capture_output=True, text=True, timeout=120, cwd=tmp_path
    )
    assert done.returncode == 0, done.stdout[-1200:]
    assert ('"msg": "FIRES"' in done.stdout) is fires, done.stdout[-1200:]
