# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Tests for the group_vars shadowing guard (#18514), including real Ansible resolution."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

import tools.lint.check_group_vars_no_shadow as guard

GROUP_VARS = guard.ANSIBLE / "inventory" / "group_vars"
HOST = "h1"
HOSTS = f"all:\n  hosts:\n    {HOST}:\n      ansible_connection: local\n"


def _layout(tmp_path: Path, shadow: bool) -> Path:
    inv = tmp_path / "inv"
    shutil.copytree(GROUP_VARS, inv / "group_vars")
    (inv / "hosts.yml").write_text(HOSTS, encoding="utf-8")
    if shadow:
        (inv / "group_vars" / "all").mkdir()
        (inv / "group_vars" / "all" / "extra.yml").write_text("extra_var: 1\n", encoding="utf-8")
    return inv


def _hostvars(inv: Path) -> dict:
    env = {**os.environ, "ANSIBLE_LOG_PATH": str(inv.parent / "a.log")}
    out = subprocess.run(
        ["ansible-inventory", "-i", str(inv / "hosts.yml"), "--host", HOST],
        capture_output=True,
        text=True,
        check=True,
        env=env,
    ).stdout
    return json.loads(out[out.index("{") :])


def test_tracked_tree_has_no_shadowing() -> None:
    assert guard.vars_roots(guard.ANSIBLE), "guard found no group_vars directory -- it looked at nothing"
    assert guard.violations() == []


def test_shadowing_pair_is_reported(tmp_path: Path) -> None:
    gv = tmp_path / "inventory" / "group_vars"
    (gv / "all").mkdir(parents=True)
    (gv / "all.yml").write_text("a: 1\n", encoding="utf-8")
    (gv / "backend.yml").write_text("b: 1\n", encoding="utf-8")
    found = guard.violations(tmp_path)
    assert len(found) == 1 and "all/" in found[0], found


def test_host_vars_shadowing_is_reported(tmp_path: Path) -> None:
    hv = tmp_path / "host_vars"
    (hv / "h1").mkdir(parents=True)
    (hv / "h1.yml").write_text("a: 1\n", encoding="utf-8")
    assert len(guard.violations(tmp_path)) == 1


@pytest.mark.skipif(shutil.which("ansible-inventory") is None, reason="ansible-inventory not installed")
def test_real_layout_resolves_base_dir_and_role_facts(tmp_path: Path) -> None:
    hv = _hostvars(_layout(tmp_path, shadow=False))
    assert hv["autobot"]["base_dir"], "autobot.base_dir must resolve from group_vars/all.yml"
    assert "role_backend_active" in hv, "role_*_active facts must resolve from the same layout"


@pytest.mark.skipif(shutil.which("ansible-inventory") is None, reason="ansible-inventory not installed")
def test_broken_layout_loses_all_yml_and_the_guard_flags_it(tmp_path: Path) -> None:
    inv = _layout(tmp_path, shadow=True)
    hv = _hostvars(inv)
    assert "autobot" not in hv, "control: Ansible loaded the directory and ignored all.yml"
    assert hv.get("extra_var") == 1
    assert guard.violations(inv.parent) != []
