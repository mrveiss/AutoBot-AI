# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`code_source` is the controller's git checkout; no task syncs it to a node.

#17242: `roles/backend/tasks/main.yml` ran a script out of `code_source` on the
target. It passed for as long as the manager was the only backend host -- there
the controller and the target are the same machine -- and failed `rc=127` the
first time a second host joined the group. #17243 found five more of the same
shape, three of them in the builtin updater.

So a task whose module executes **on the target** may not read `code_source`
unless it is delegated to the controller. `_shared/tasks/sync_deletions.yml` has
always done this correctly and is the pattern.

A play pinned to the controller or the manager is exempt: there the path really
does exist, and `playbooks/sync-code-source.yml` exists precisely to push
`code_source` to the SLM. Those are allowed by play scope, not by name, so a
task that moves into a fleet-wide play stops being exempt automatically.

CI does not execute Ansible, so this is unobservable before a fleet node hits
it -- which is exactly why it survived green runs for so long.

Mutation check: drop `delegate_to: localhost` from the generate task in
`roles/backend/tasks/main.yml` and this goes red naming that file and task.
"""

from __future__ import annotations

import pathlib

import yaml

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_ANSIBLE = _REPO_ROOT / "autobot-slm-backend" / "ansible"

# Modules whose payload runs on the TARGET unless the task is delegated.
_EXEC_MODULES = {
    "shell", "ansible.builtin.shell",
    "command", "ansible.builtin.command",
    "script", "ansible.builtin.script",
    "raw", "ansible.builtin.raw",
}

# Play scopes where the controller's checkout is genuinely present.
_CONTROLLER_SCOPES = {"localhost", "127.0.0.1", "slm_server", "slm"}

# A floor, not a census: if the walk stops finding `code_source` tasks at all,
# this guard would pass by matching nothing. See MEASUREMENT_DISCIPLINE.md.
_MIN_TASKS_SEEN = 8


def _tasks(node):
    """Yield every mapping that looks like a task, depth-first."""
    if isinstance(node, list):
        for item in node:
            yield from _tasks(item)
    elif isinstance(node, dict):
        if any(k in _EXEC_MODULES for k in node):
            yield node
        for value in node.values():
            yield from _tasks(value)


def _payload_text(task) -> str:
    module = next(k for k in task if k in _EXEC_MODULES)
    payload = task[module]
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return " ".join(f"{k}={v}" for k, v in payload.items())
    return str(payload)


def _play_scope(doc, task) -> str | None:
    """`hosts:` of the play containing *task*, or None for a role task file."""
    if not isinstance(doc, list):
        return None
    for play in doc:
        if not isinstance(play, dict) or "hosts" not in play:
            continue
        if any(t is task for t in _tasks(play)):
            return str(play.get("hosts", ""))
    return None


def _offenders() -> tuple[list[str], int]:
    offenders: list[str] = []
    seen = 0
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        if "/tests/" in path.as_posix():
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        for task in _tasks(doc):
            if "code_source" not in _payload_text(task):
                continue
            seen += 1
            if task.get("delegate_to"):
                continue
            scope = _play_scope(doc, task)
            if scope is not None and any(s in scope for s in _CONTROLLER_SCOPES):
                continue
            offenders.append(
                f"{path.relative_to(_REPO_ROOT).as_posix()} :: "
                f"{str(task.get('name', '<unnamed>'))[:70]}"
                f"{'' if scope is None else f'  (play hosts: {scope})'}"
            )
    return offenders, seen


def test_the_scan_reaches_the_tasks_it_guards():
    """A walk that matches nothing would make the assertion below vacuous."""
    _, seen = _offenders()

    assert seen >= _MIN_TASKS_SEEN, (
        f"only {seen} task(s) referencing code_source were found, expected at least "
        f"{_MIN_TASKS_SEEN} -- this guard has stopped reaching the tasks it checks"
    )


def test_no_target_side_task_reads_code_source_undelegated():
    """#17242/#17243: reading the controller's checkout on a node is rc=127."""
    offenders, _ = _offenders()

    assert not offenders, (
        "these tasks execute on the target and read code_source, which exists only on "
        "the controller -- add `delegate_to: localhost` (see "
        "_shared/tasks/sync_deletions.yml) or stage the file onto the node:\n  "
        + "\n  ".join(offenders)
    )
