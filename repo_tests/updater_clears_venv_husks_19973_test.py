# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The builtin updater clears venv husks before pip meets them (#19973).

pip aborts on a dist-info husk with uninstall-no-record-file, so a husked SLM venv stopped every
update in Play 1, before the update that could repair it. The roles include the repair; the
playbook's inline pip tasks did not. ai-stack is not covered because this playbook has no pip task for it.
"""

from __future__ import annotations

import yaml
from repo_tests._paths import repo_root

_PLAYBOOK = repo_root() / "autobot-slm-backend" / "ansible" / "playbooks" / "update-all-nodes.yml"
#: The marker-capable venvs this playbook pip-installs into.
_MARKER_CAPABLE = ("autobot-slm-backend", "autobot-backend")


def _tasks() -> list[dict]:
    return [task for play in yaml.safe_load(_PLAYBOOK.read_text(encoding="utf-8")) for task in play.get("tasks") or []]


def _repairs_before_pip(tasks: list[dict], venv: str) -> bool:
    """A husk include for *venv* comes before the first pip install into it."""
    for task in tasks:
        include = str(task.get("ansible.builtin.include_tasks", ""))
        if "clear_venv_husks.yml" in include and "apply" in include and f"/{venv}/venv" in str(task.get("vars", {})):
            return True
        if f"/{venv}/venv/bin/pip install" in str((task.get("command") or {})):
            return False
    raise AssertionError(f"no pip install into {venv} found; this test reads nothing")


def test_every_marker_capable_pip_install_is_preceded_by_the_repair() -> None:
    tasks = _tasks()
    for venv in _MARKER_CAPABLE:
        assert _repairs_before_pip(tasks, venv), f"{venv}: pip can meet a husk before the repair runs"


def test_contrast_a_pip_task_without_the_repair_is_caught() -> None:
    bare = [{"command": {"cmd": "/x/autobot-backend/venv/bin/pip install -r r.txt"}}]
    assert not _repairs_before_pip(bare, "autobot-backend")
