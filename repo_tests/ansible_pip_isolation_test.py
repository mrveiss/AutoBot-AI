# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No ansible task may install a Python package outside a virtualenv (#15417).

A package installed on the system interpreter is a second copy of something a venv
already pins, and the two float independently. That is not merely untidy: the browser
role installed `fastapi` system-wide with `state: present` and no floor, while the
backend venv pins `fastapi>=0.141.1` -- a floor annotated `SECURITY UPDATE - requires
starlette >=0.52.1`. The unpinned copy could satisfy `state: present` below that floor.

The drift stays invisible because consumers guard their imports. `research_browser_manager.py`
wraps `from playwright.async_api import ...` in `try/except ImportError` and sets
`PLAYWRIGHT_AVAILABLE = False`, so a missing or mismatched package silently degrades a
capability rather than failing a deploy.

Two shapes install packages, and a guard that reads only the first would miss half the
surface: the `pip:` module (`virtualenv:` key) and raw `pip install` inside `command:`
or `shell:` (venv-scoped either by an explicit `.../venv/bin/pip` path or by a preceding
`source .../venv/bin/activate` in the same block).

Exemptions are listed here with a reason rather than inferred. There is exactly one, and
it is structural: the bootstrap that installs pip/setuptools/wheel cannot target a venv,
because a venv cannot be created before those exist.

Scope note: this guard enforces venv isolation only. Whether each site also applies
`constraints/shared.txt` is a separate and currently unmet invariant -- 19 runtime
installs do not (#15418) -- and asserting it here would redden the tree rather than
describe it.
"""

from __future__ import annotations

import pathlib

import pytest

yaml = pytest.importorskip("yaml")

_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"

# (path relative to the ansible root, task name) -> why it may install system-wide.
_EXEMPT: dict[tuple[str, str], str] = {
    (
        "roles/common/tasks/main.yml",
        "Common | Install Python packages (system-wide)",
    ): (
        "bootstrap: pip, setuptools and wheel must exist on the system interpreter "
        "before any virtualenv can be created, so this task cannot target one. It "
        "installs no runtime dependency, which is what keeps it from colliding with "
        "a venv's pins."
    ),
}

# Floors, not censuses: a walk that silently stops matching must fail loudly rather
# than pass by reaching nothing.
_MIN_PIP_MODULE_TASKS = 25
_MIN_RAW_PIP_COMMANDS = 6


def _ansible_documents():
    for path in sorted(_ANSIBLE_ROOT.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        if document is not None:
            yield path.relative_to(_ANSIBLE_ROOT).as_posix(), document


def _collect_pip_module_tasks() -> list[tuple[str, str, bool]]:
    """(file, task name, targets a venv) for every `pip:` module task."""
    found: list[tuple[str, str, bool]] = []

    def walk(node, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("pip", "ansible.builtin.pip") and isinstance(value, dict):
                    found.append((where, str(node.get("name", "<unnamed>")), "virtualenv" in value))
                walk(value, where)
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for where, document in _ansible_documents():
        walk(document, where)
    return found


def _collect_raw_pip_commands() -> list[tuple[str, str, bool]]:
    """(file, task name, venv-scoped) for every raw `pip install` in command/shell."""
    found: list[tuple[str, str, bool]] = []

    def scoped(script: str) -> bool:
        return "/venv/bin/pip" in script or "venv/bin/activate" in script

    def walk(node, where: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("command", "shell", "ansible.builtin.command", "ansible.builtin.shell"):
                    script = value.get("cmd", "") if isinstance(value, dict) else value
                    script = str(script)
                    if "pip install" in script:
                        found.append((where, str(node.get("name", "<unnamed>")), scoped(script)))
                walk(value, where)
        elif isinstance(node, list):
            for item in node:
                walk(item, where)

    for where, document in _ansible_documents():
        walk(document, where)
    return found


def test_the_ansible_tree_this_guard_reads_is_present():
    """A relocated ansible root would make every rule below vacuous."""
    assert _ANSIBLE_ROOT.is_dir(), f"{_ANSIBLE_ROOT} is missing — this guard is pinned to the wrong path"


def test_the_walk_reaches_the_known_pip_sites():
    """Both walks must keep matching, or the rules below assert nothing."""
    module_tasks = _collect_pip_module_tasks()
    raw_commands = _collect_raw_pip_commands()

    assert len(module_tasks) >= _MIN_PIP_MODULE_TASKS, (
        f"only {len(module_tasks)} `pip:` task(s) found, expected at least "
        f"{_MIN_PIP_MODULE_TASKS} — this walk has stopped reaching the tree it guards"
    )
    assert len(raw_commands) >= _MIN_RAW_PIP_COMMANDS, (
        f"only {len(raw_commands)} raw `pip install` command(s) found, expected at least "
        f"{_MIN_RAW_PIP_COMMANDS} — this walk has stopped reaching the tree it guards"
    )


def test_every_pip_module_task_targets_a_virtualenv():
    """Reported as a set: one abort would hide the rest behind a re-run."""
    offenders = [
        (where, name)
        for where, name, has_venv in _collect_pip_module_tasks()
        if not has_venv and (where, name) not in _EXEMPT
    ]

    assert not offenders, "pip tasks install system-wide without a documented exemption (#15417):\n" + "\n".join(
        f"  {where}\n     task: {name}\n     add `virtualenv:`, or add an entry to _EXEMPT stating why it cannot"
        for where, name in offenders
    )


def test_every_raw_pip_command_runs_inside_a_virtualenv():
    """A bare `pip install` in a shell block reaches the system interpreter."""
    offenders = [
        (where, name)
        for where, name, is_scoped in _collect_raw_pip_commands()
        if not is_scoped
    ]

    assert not offenders, "raw pip commands are not venv-scoped (#15417):\n" + "\n".join(
        f"  {where}\n     task: {name}\n     use `.../venv/bin/pip`, or `source .../venv/bin/activate` first"
        for where, name in offenders
    )


def test_every_exemption_states_a_reason():
    """An exemption without a reason is an unexamined outlier with better paperwork."""
    unexplained = [key for key, reason in _EXEMPT.items() if len(reason.strip()) < 40]

    assert not unexplained, f"exemptions carry no substantive reason: {unexplained}"


def test_exemptions_still_correspond_to_real_tasks():
    """A stale exemption would silently forgive a task that no longer exists."""
    actual = {(where, name) for where, name, _ in _collect_pip_module_tasks()}
    stale = [key for key in _EXEMPT if key not in actual]

    assert not stale, f"_EXEMPT names tasks that no longer exist — remove them: {stale}"
