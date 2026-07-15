# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Secret extra_vars must never appear in the ansible argv (#11735).

PlaybookExecutor auto-merges stored SLM secrets into extra_vars (#3519);
passing them as ``-e key=value`` exposed the values in /proc/<pid>/cmdline
to every local user for the whole playbook run.  They now travel via a
0600 temp JSON file passed as ``-e @<file>``.

Loads the modules under test directly from their file paths via importlib
(same approach as tests/api/test_apply_secrets.py): the shared conftest
stubs the ``services`` package with MagicMocks, so normal package imports
resolve to stubs when this file runs standalone (#11248).
"""

from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_from_file(module_name: str, rel_path: str, extra_stubs: dict | None = None):
    """Load a module from its file path with sys.modules snapshot/restore."""
    snapshot = sys.modules.copy()
    for name, stub in (extra_stubs or {}).items():
        sys.modules[name] = stub
    try:
        spec = importlib.util.spec_from_file_location(module_name, _BACKEND_ROOT / rel_path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.modules.clear()
        sys.modules.update(snapshot)


def _load_inventory_builder():
    return _load_from_file("_ib_11735", "services/inventory_builder.py")


def _load_playbook_executor():
    services_pkg = MagicMock()
    stubs = {
        "services": services_pkg,
        "services.ansible_secrets": MagicMock(),
        "services.inventory_builder": MagicMock(),
        "services.provision_progress": MagicMock(),
    }
    return _load_from_file("_pe_11735", "services/playbook_executor.py", extra_stubs=stubs)


# ============================================================
# write_temp_extra_vars
# ============================================================


def test_written_file_is_0600_and_round_trips(tmp_path):
    ib = _load_inventory_builder()
    vars_in = {"tts_hf_token": "hf_dummy_value", "plain": "x"}  # nosec B106 - test fixture, not a credential
    path = ib.write_temp_extra_vars(vars_in, uid_tmp_dir=str(tmp_path))
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        assert mode == 0o600, f"expected 0600, got {oct(mode)}"
        assert json.loads(path.read_text(encoding="utf-8")) == vars_in
        assert path.parent == tmp_path
    finally:
        path.unlink(missing_ok=True)


def test_unique_file_per_call(tmp_path):
    ib = _load_inventory_builder()
    a = ib.write_temp_extra_vars({"k": "1"}, uid_tmp_dir=str(tmp_path))
    b = ib.write_temp_extra_vars({"k": "2"}, uid_tmp_dir=str(tmp_path))
    try:
        assert a != b
    finally:
        a.unlink(missing_ok=True)
        b.unlink(missing_ok=True)


# ============================================================
# _build_ansible_command
# ============================================================


def _build_command(extra_vars_file):
    pe = _load_playbook_executor()
    executor = pe.PlaybookExecutor.__new__(pe.PlaybookExecutor)  # skip __init__ (env probing)
    executor.inventory_path = Path("/tmp/inv.yml")  # nosec B108 - test fixture path
    executor._find_ansible_playbook = lambda: "ansible-playbook"
    return executor._build_ansible_command(
        Path("/tmp/play.yml"),  # nosec B108 - test fixture path
        limit=["node-1"],
        tags=None,
        extra_vars_file=extra_vars_file,
        check_mode=False,
    )


def test_command_uses_at_file_reference():
    cmd = _build_command(Path("/tmp/evars.json"))  # nosec B108 - test fixture path
    assert "-e" in cmd
    assert "@/tmp/evars.json" in cmd


def test_no_key_value_pairs_in_argv():
    cmd = _build_command(Path("/tmp/evars.json"))  # nosec B108 - test fixture path
    joined = " ".join(cmd)
    assert "=" not in joined.replace("@/tmp/evars.json", ""), f"argv leaks key=value: {cmd}"


def test_no_extra_vars_flag_when_no_file():
    cmd = _build_command(None)
    assert "-e" not in cmd
