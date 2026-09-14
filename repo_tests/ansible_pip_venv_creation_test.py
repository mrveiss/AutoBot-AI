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

This is a ratchet, not an absolute (#16641's own acceptance criteria: "a
guard test fails on any NEW pip task" -- not on the tree as found). Thirteen
sites predate this guard, in roles this change does not otherwise touch
(``roles/backend``, ``roles/dependency_patching``,
``roles/redis/tasks/chromadb.yml`` -- fenced off a concurrent edit at filing
time -- and ``roles/slm_manager``); ``KNOWN_MISSING`` names them so a new
site cannot hide behind the same silence, and shrinks as each is fixed.
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

#: Sites this guard already knew about at filing time, with a reason each is
#: not fixed HERE rather than a promise it never will be. Shrink-only, the
#: same contract as `ansible_manifest_resolution.MULTI_SOURCE_VENVS`: an
#: entry that stops matching a real offender fails just as loudly as a new,
#: unrecorded one.
KNOWN_MISSING: dict[tuple[str, str], str] = {
    ("roles/backend/tasks/main.yml", "Upgrade pip"): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/backend/tasks/main.yml",
        "Install autobot_shared as editable package",
    ): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/backend/tasks/main.yml",
        "Install filtered backend requirements",
    ): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/backend/tasks/main.yml",
        "Backend | Install CUDA torch requirements (requirements-gpu-torch.txt) (#15162)",
    ): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/backend/tasks/main.yml",
        "Backend | Remove CPU-only faiss before installing the GPU build (#15163)",
    ): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/backend/tasks/main.yml",
        "Backend | Install GPU faiss requirements (requirements-gpu-faiss.txt) (#15163)",
    ): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/backend/tasks/main.yml",
        "Backend | Install GPU/vLLM requirements (requirements-gpu.txt) (#10288)",
    ): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/backend/tasks/main.yml",
        "Reinstall autobot_shared to pick up ssot_config fixes",
    ): "roles/backend, untouched here -- filed as #16718",
    (
        "roles/dependency_patching/tasks/update-venv.yml",
        "Upgrade pip first (if needed)",
    ): "roles/dependency_patching, untouched here -- filed as #16718",
    (
        "roles/dependency_patching/tasks/update-venv.yml",
        "Install security updates",
    ): "roles/dependency_patching, untouched here -- filed as #16718",
    (
        "roles/redis/tasks/chromadb.yml",
        "ChromaDB | Upgrade pip in venv",
    ): "roles/redis/** was fenced off a concurrent edit at filing time",
    (
        "roles/redis/tasks/chromadb.yml",
        "ChromaDB | Install chromadb package",
    ): "roles/redis/** was fenced off a concurrent edit at filing time",
    (
        "roles/slm_manager/tasks/main.yml",
        "SLM | Install Python requirements",
    ): "roles/slm_manager, untouched here -- filed as #16718",
}


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


def test_no_new_pip_task_creates_a_venv_via_the_virtualenv_executable() -> None:
    """A pip task with `virtualenv:` must also say how to create it (#16641)."""
    offenders = {(where, name) for where, name, has_command in _pip_venv_tasks() if not has_command}
    unrecorded = sorted(offenders - set(KNOWN_MISSING))
    assert not unrecorded, (
        "these pip tasks set virtualenv: with no virtualenv_command:, so pip falls back to the "
        "standalone `virtualenv` executable -- absent from this fleet, only `python3 -m venv` is "
        'installed (#16641). Set virtualenv_command: "{{ python_interpreter_binary }} -m venv" '
        "(or the role's equivalent literal), or add the (file, task name) pair to KNOWN_MISSING "
        "with a reason:\n  " + "\n  ".join(f"{where}: {name}" for where, name in unrecorded)
    )

    stale = sorted(set(KNOWN_MISSING) - offenders)
    assert not stale, (
        "KNOWN_MISSING names a (file, task name) pair that is no longer missing "
        "virtualenv_command: — the fix landed and the record did not. Delete it:\n  "
        + "\n  ".join(f"{where}: {name}" for where, name in stale)
    )
