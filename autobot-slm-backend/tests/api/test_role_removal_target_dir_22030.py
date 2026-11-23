# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The removal passes the playbook a safe install-root-relative directory, and the playbook checks it again (#22030)."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _real_orm_import import SLM_ROOT, import_modules_with_real_orm  # noqa: E402

_codestatus, _nodes = import_modules_with_real_orm(
    import_names=("api.nodes",),
    path_loaded={"services.code_status": SLM_ROOT / "services" / "code_status.py"},
)

_PLAYBOOK = SLM_ROOT / "ansible" / "playbooks" / "remove-role.yml"


def _extra_vars_sent(target_dir):
    ran = AsyncMock(return_value={"success": True, "output": "ok"})
    executor = type("Ex", (), {"execute_playbook": staticmethod(ran)})()
    with patch("services.playbook_executor.get_playbook_executor", return_value=executor):
        asyncio.run(_nodes._run_role_removal("n1", "slm-agent", "slm-agent", False, target_dir))
    return ran.await_args.kwargs["extra_vars"]


def test_the_agent_case_passes_the_whole_relative_path_not_its_basename():
    sent = _extra_vars_sent("autobot-slm-agent/slm/agent")
    assert sent["role_target_dir"] == "autobot-slm-agent/slm/agent"


@pytest.mark.parametrize(
    "value", [None, "", ".", "..", "/", "/opt/autobot", "/opt/x/y", "../x", "a/../b", "a/./b", "a b"]
)
def test_an_unsafe_directory_is_not_sent_at_all(value):
    assert "role_target_dir" not in _extra_vars_sent(value)


def _tasks():
    return yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8"))[0]["tasks"]


def test_the_playbook_validates_the_directory_before_any_other_task():
    tasks = _tasks()
    names = [t["name"] for t in tasks[:3]]
    assert all("#22030" in n for n in names), names
    checks = " ".join(str(t) for t in tasks[:3])
    for needed in ("startswith('/')", "'..'", "realpath", "length > 0"):
        assert needed in checks, needed


def test_every_validation_task_is_conditional_on_the_variable_and_nothing_precedes_them():
    first, resolve, check = _tasks()[:3]
    for task in (first, resolve, check):
        assert task["when"] == "role_target_dir is defined"
    assert "ansible.builtin.assert" in first and "ansible.builtin.command" in resolve
