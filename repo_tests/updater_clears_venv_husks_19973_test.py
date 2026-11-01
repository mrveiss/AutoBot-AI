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


def _husk_and_pip(tasks: list[dict], venv: str) -> tuple[dict, dict]:
    husk = next(
        task
        for task in tasks
        if "clear_venv_husks.yml" in str(task.get("ansible.builtin.include_tasks", ""))
        and f"/{venv}/venv" in str(task.get("vars", ""))
    )
    pip = next(task for task in tasks if f"/{venv}/venv/bin/pip install" in str(task.get("command") or {}))
    return husk, pip


def _mismatches(husk: dict, pip: dict) -> list[str]:
    """What lets a run reach pip without the repair: a pip tag or a condition the include lacks (#19986)."""
    wanted = set(pip.get("tags") or [])
    found = []
    if not wanted <= set(husk.get("tags") or []):
        found.append("tags")
    if not wanted <= set(husk["ansible.builtin.include_tasks"]["apply"].get("tags") or []):
        found.append("apply tags")
    if husk.get("when") != pip.get("when"):
        found.append("when")
    return found


def test_a_tagged_run_cannot_reach_pip_without_the_repair() -> None:
    tasks = _tasks()
    for venv in _MARKER_CAPABLE:
        assert _mismatches(*_husk_and_pip(tasks, venv)) == [], venv


def test_contrast_each_mismatch_is_caught() -> None:
    pip = {"tags": ["slm", "slm-backend", "deps"], "when": "x"}
    include = {"apply": {"tags": ["slm", "slm-backend", "deps"]}}
    good = {"tags": pip["tags"], "when": "x", "ansible.builtin.include_tasks": include}
    assert _mismatches(good, pip) == []
    assert _mismatches({**good, "tags": ["slm", "deps"]}, pip) == ["tags"]  # the shape #19986 found
    short = {"apply": {"tags": ["slm", "deps"]}}
    assert _mismatches({**good, "ansible.builtin.include_tasks": short}, pip) == ["apply tags"]
    assert _mismatches({**good, "when": "y"}, pip) == ["when"]
