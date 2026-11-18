# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""``execute_playbook`` applies the limit proof before it decides success (#19762).

Drives the REAL ``execute_playbook`` with only its I/O collaborators replaced: a limited
``update-all-nodes.yml`` run that exits 0 but in which only localhost ran is a failure whose
reason leads the output, and the same run with the node in the recap is a success.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from unittest.mock import AsyncMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

_NODE = "b9a29e04"
_SKIPS = "PLAY [Play 2b - Update Database Nodes] ****\nskipping: no hosts matched\n"
_LOCAL = "localhost  : ok=25  changed=4  unreachable=0  failed=0\n"


def _load_real_playbook_executor():
    spec = importlib.util.spec_from_file_location(
        "playbook_executor_under_limit_proof_test", _SLM_ROOT / "services" / "playbook_executor.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["playbook_executor_under_limit_proof_test"] = module
    spec.loader.exec_module(module)
    return module


playbook_executor = _load_real_playbook_executor()


def _run(tmp_path: Path, monkeypatch, output: str) -> dict:
    (tmp_path / "update-all-nodes.yml").write_text("- hosts: all\n", encoding="utf-8")
    executor = playbook_executor.PlaybookExecutor(ansible_dir=tmp_path)
    monkeypatch.setattr(executor, "_refresh_ansible_dir", lambda: None)
    monkeypatch.setattr(executor, "_update_code_source", AsyncMock(return_value=None))
    monkeypatch.setattr(executor, "_code_source_sync_failure_result", lambda *_a: None)
    monkeypatch.setattr(executor, "_select_inventory", AsyncMock(return_value=(tmp_path / "inventory", None)))
    monkeypatch.setattr(executor, "_stage_extra_vars", lambda *_a: None)
    monkeypatch.setattr(playbook_executor, "fetch_deploy_secrets", AsyncMock(return_value={}))
    sub = AsyncMock(return_value={"output": output, "returncode": 0, "timed_out": False, "detached": False})
    monkeypatch.setattr(executor, "_run_subprocess", sub)
    return asyncio.run(executor.execute_playbook(playbook_name="update-all-nodes.yml", limit=["localhost", _NODE]))


def test_a_run_where_only_localhost_ran_fails_with_the_reason_first(tmp_path, monkeypatch) -> None:
    result = _run(tmp_path, monkeypatch, _SKIPS + "PLAY RECAP ****\n" + _LOCAL)
    assert result["success"] is False
    assert result["returncode"] == 1
    assert result["output"].splitlines()[0].startswith("ERROR! hosts named by the limit ran no task")


def test_the_same_run_with_the_node_in_the_recap_succeeds(tmp_path, monkeypatch) -> None:
    node = f"{_NODE}  : ok=100  changed=9  unreachable=0  failed=0  skipped=114\n"
    result = _run(tmp_path, monkeypatch, _SKIPS + "PLAY RECAP ****\n" + node + _LOCAL)
    assert result["success"] is True
    assert result["returncode"] == 0
