# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Dynamic-inventory runs must expose the static group_vars (#11781).

Ansible resolves ``group_vars/`` relative to the inventory SOURCE directory.
The dynamic inventory is written to a uid-scoped /tmp dir, so the repo's
``inventory/group_vars/*.yml`` never loaded and playbooks referencing those
vars (e.g. ``slm_manager_node_id``) hit "undefined variable" — the
self-update pre-flight "Notify SLM of new commit" task failed exactly so.
``_link_group_vars`` symlinks the real group_vars dir beside the temp
inventory to restore parity with static-inventory runs.

Loaded via importlib to dodge the conftest's session-global stubs (#11248).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]

_STUBS = [
    "services",
    "services.ansible_secrets",
    "services.inventory_builder",
    "services.provision_progress",
]


def _load_executor():
    saved = {n: sys.modules.get(n) for n in _STUBS}
    try:
        for n in _STUBS:
            sys.modules[n] = MagicMock()
        spec = importlib.util.spec_from_file_location("_pe_11781", _BACKEND_ROOT / "services" / "playbook_executor.py")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    finally:
        for n, orig in saved.items():
            if orig is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = orig


_pe = _load_executor()


def _executor(ansible_dir: Path):
    ex = _pe.PlaybookExecutor.__new__(_pe.PlaybookExecutor)  # skip __init__ (env probing)
    ex.ansible_dir = ansible_dir
    return ex


def _fake_ansible_dir(tmp_path: Path) -> Path:
    gv = tmp_path / "ansible" / "inventory" / "group_vars"
    gv.mkdir(parents=True)
    (gv / "all.yml").write_text("slm_manager_node_id: '00-SLM-Manager'\n", encoding="utf-8")
    return tmp_path / "ansible"


def test_group_vars_symlink_created_beside_inventory(tmp_path):
    ansible_dir = _fake_ansible_dir(tmp_path)
    inv_dir = tmp_path / "inv"
    inv_dir.mkdir()
    inv = inv_dir / "autobot_inv_x.yml"
    inv.write_text("all:\n  hosts: {}\n", encoding="utf-8")

    _executor(ansible_dir)._link_group_vars(inv)

    link = inv_dir / "group_vars"
    assert link.is_symlink()
    assert link.resolve() == (ansible_dir / "inventory" / "group_vars").resolve()
    # all.yml is reachable through the link → ansible would load it.
    assert (link / "all.yml").read_text(encoding="utf-8").startswith("slm_manager_node_id")


def test_idempotent_when_link_already_correct(tmp_path):
    ansible_dir = _fake_ansible_dir(tmp_path)
    inv = tmp_path / "autobot_inv_y.yml"
    inv.write_text("all: {}\n", encoding="utf-8")
    ex = _executor(ansible_dir)
    ex._link_group_vars(inv)
    ex._link_group_vars(inv)  # second call must not raise / must keep the link
    assert (tmp_path / "group_vars").resolve() == (ansible_dir / "inventory" / "group_vars").resolve()


def test_missing_group_vars_source_is_noop(tmp_path):
    ansible_dir = tmp_path / "ansible"  # no inventory/group_vars
    ansible_dir.mkdir()
    inv = tmp_path / "autobot_inv_z.yml"
    inv.write_text("all: {}\n", encoding="utf-8")
    _executor(ansible_dir)._link_group_vars(inv)  # must not raise
    assert not (tmp_path / "group_vars").exists()
