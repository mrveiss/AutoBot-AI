# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The fleet-address check gathers the network facts it reads (#19944).

The updater's plays run with gather_facts: false and gather only the "min" subset, so the check
reported "no default route" on a host that had one, and every builtin update stopped in Play 1.
This runs the shipped task file with ansible-playbook, from the same starting state.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
import yaml
from repo_tests._paths import repo_root

_ROLE = repo_root() / "autobot-slm-backend" / "ansible" / "roles" / "postgresql"
_PLAYBOOK = shutil.which("ansible-playbook")
_needs_ansible = pytest.mark.skipif(_PLAYBOOK is None, reason="ansible-playbook is not installed")


def _run(tmp_path, extra_vars: dict | None = None) -> subprocess.CompletedProcess:
    """fleet_address.yml on localhost, after gathering only the subset the updater gathers."""
    playbook = [
        {
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars_files": [str(_ROLE / "defaults" / "main.yml")],
            "tasks": [
                {"ansible.builtin.setup": {"gather_subset": ["min"]}},
                {"ansible.builtin.assert": {"that": ["ansible_facts['default_ipv4'] is not defined"]}},
                {"ansible.builtin.include_tasks": str(_ROLE / "tasks" / "fleet_address.yml")},
                {"ansible.builtin.debug": {"msg": "FLEET_ADDRESS={{ postgresql_fleet_address }}"}},
            ],
        }
    ]
    path = tmp_path / "play.yml"
    path.write_text(yaml.safe_dump(playbook), encoding="utf-8")
    args = [_PLAYBOOK, "-i", "localhost,", str(path), "-e", json.dumps(extra_vars or {})]
    return subprocess.run(args, capture_output=True, text=True, timeout=120, cwd=tmp_path, check=False)


@_needs_ansible
def test_missing_network_facts_are_gathered_before_the_check(tmp_path) -> None:
    routes = subprocess.run(["ip", "-4", "route", "show", "default"], capture_output=True, text=True, check=False)
    if not routes.stdout.strip():
        pytest.skip("this machine has no default route, so no address can resolve")
    result = _run(tmp_path)
    assert result.returncode == 0, result.stdout[-1500:]
    assert "FLEET_ADDRESS=" in result.stdout and 'FLEET_ADDRESS="' not in result.stdout


@_needs_ansible
def test_a_host_with_no_address_still_fails_and_reports_what_it_evaluated(tmp_path) -> None:
    result = _run(tmp_path, {"postgresql_fleet_address": ""})
    assert result.returncode != 0, "the check passed with no address"
    for evaluated in ("slm_host=", "ansible_host=", "own addresses=", "default route address="):
        assert evaluated in result.stdout, result.stdout[-1500:]
    assert "there is no default route" not in result.stdout


def test_contrast_the_starting_state_has_no_network_facts_gathered() -> None:
    """The task must not be gated on a fact the min subset could have set."""
    tasks = yaml.safe_load((_ROLE / "tasks" / "fleet_address.yml").read_text(encoding="utf-8"))
    gather, check = tasks[0], tasks[1]
    assert gather["ansible.builtin.setup"]["gather_subset"] == ["network"]
    assert "all_ipv4_addresses" in gather["when"] and "default_ipv4" in gather["when"]
    assert "ansible.builtin.assert" in check
