# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A pip task that sets ``virtualenv:`` must say how to create it (#16641).

The ``ansible.builtin.pip`` module creates the venv named by ``virtualenv:``
when it does not already exist, by shelling out to ``virtualenv_command:`` --
which defaults to the *standalone* ``virtualenv`` executable, not the
standard library's ``venv`` module. Nothing in this fleet installs that
executable; only ``python3 -m venv`` is available. The failure surfaces the
first time a role actually has to create the venv, so a host whose venv
already exists (recreated, migrated, hand-provisioned) passes and hides it --
exactly what happened on 2026-09-13/14, when a builtin ``update-all`` deploy
failed the browser-service venv with:

    Failed to find required executable "virtualenv" in paths: ...

``virtualenv_python:`` does not fix this -- the pip module only appends
``-p <python>`` when ``virtualenv_command:`` itself names the ``virtualenv``
tool, so an unrelated ``virtualenv_command:`` (or none at all) makes
``virtualenv_python:`` dead configuration.

Absolute, not a ratchet: every pip task under ``autobot-slm-backend/ansible/``
that sets ``virtualenv:`` was swept and given a ``virtualenv_command:`` in
the same change that added this guard, including the ones a task-role sweep
would have left out of scope (``roles/backend``, ``roles/dependency_patching``,
``roles/redis/tasks/chromadb.yml``, ``roles/slm_manager``). There is no
baseline of exceptions to widen -- a new offender is always a new defect.
"""

from __future__ import annotations

import pytest
from repo_tests._paths import repo_root

yaml = pytest.importorskip("yaml")

_REPO_ROOT = repo_root()
_ANSIBLE = _REPO_ROOT / "autobot-slm-backend" / "ansible"

_PIP_MODULE_KEYS = ("pip", "ansible.builtin.pip")

#: Floor on the sweep's REACH -- pip tasks with `virtualenv:` discovered,
#: never findings. 29 measured 2026-09-14; well above the population any one
#: role could hide behind if the walk broke.
_MIN_VENV_PIP_TASKS = 20


def _pip_venv_tasks() -> list[tuple[str, str, bool]]:
    """(file, task name, has virtualenv_command) for every pip task with `virtualenv:`."""
    tasks: list[tuple[str, str, bool]] = []

    def walk(node, where: str, name: str = "") -> None:
        if isinstance(node, dict):
            name = str(node.get("name", name))
            for key in _PIP_MODULE_KEYS:
                value = node.get(key)
                if isinstance(value, dict) and "virtualenv" in value:
                    tasks.append((where, name, "virtualenv_command" in value))
            for value in node.values():
                walk(value, where, name)
        elif isinstance(node, list):
            for item in node:
                walk(item, where, name)

    for path in sorted(_ANSIBLE.rglob("*.yml")):
        try:
            documents = list(yaml.safe_load_all(path.read_text(encoding="utf-8")))
        except Exception:  # noqa: BLE001 - a jinja-templated file ansible renders before parsing
            continue
        walk(documents, path.relative_to(_ANSIBLE).as_posix())
    return tasks


def test_the_sweep_reaches_the_venv_pip_tasks_it_claims_to() -> None:
    """Reach before findings -- an empty walk must fail, not pass silently."""
    tasks = _pip_venv_tasks()
    assert len(tasks) >= _MIN_VENV_PIP_TASKS, (
        f"found only {len(tasks)} pip tasks with virtualenv: (floor {_MIN_VENV_PIP_TASKS}) — "
        "the walk has stopped reading"
    )


def test_no_pip_task_creates_a_venv_via_the_virtualenv_executable() -> None:
    """A pip task with `virtualenv:` must also say how to create it (#16641)."""
    offenders = sorted((where, name) for where, name, has_command in _pip_venv_tasks() if not has_command)
    assert not offenders, (
        "these pip tasks set virtualenv: with no virtualenv_command:, so pip falls back to the "
        "standalone `virtualenv` executable -- absent from this fleet, only `python3 -m venv` is "
        'installed (#16641). Set virtualenv_command: "{{ python_interpreter_binary }} -m venv" '
        "(or the role's equivalent literal):\n  " + "\n  ".join(f"{where}: {name}" for where, name in offenders)
    )
