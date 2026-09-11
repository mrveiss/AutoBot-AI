# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310 owner decision: every role that syncs code runs the deletion tasks
right after its own sync task, and writes this module's marker only after
deletion. Asserted on task ORDER, not text -- a deletion task present
anywhere in the file would pass a substring check while still running before
the sync it is supposed to follow, or never running at all under a `when`
that can't be true.

Covers roles/backend, roles/frontend (co-located AND remote: the same task
file runs against whichever host these roles target, so there is no separate
"remote-node role" to wire), roles/slm_manager (SLM backend), and
playbooks/update-all-nodes.yml (the SLM's actual self-update path for
slm-backend/slm-frontend/autobot_shared -- unarchive-based, not
`ansible.posix.synchronize`, per #16310 review).

Lives in repo_tests/ because CI's shard command passes an explicit path list
and autobot-slm-backend/ansible is not on it (mirrors
repo_tests/ansible_backend_path_defects_15560_test.py).
"""

from __future__ import annotations

import pytest
import yaml
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"
_SYNC_DELETIONS_INCLUDE = "sync_deletions.yml"

# (file relative to _ANSIBLE_ROOT, name-substring of the sync task the
# deletion task must follow).
_SYNC_THEN_DELETE_SITES: tuple[tuple[str, str], ...] = (
    ("roles/backend/tasks/main.yml", "Sync autobot-backend code from code_source"),
    ("roles/frontend/tasks/main.yml", "Sync frontend code from code_source"),
    ("roles/slm_manager/tasks/main.yml", "Sync SLM backend code from code_source"),
    ("playbooks/update-all-nodes.yml", "SLM | Deploy autobot-slm-frontend"),
)


def _load_tasks(rel_path: str) -> list[dict]:
    path = _ANSIBLE_ROOT / rel_path
    assert path.is_file(), f"{path} not found -- #16310 wiring test target moved or was deleted"
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return loaded if isinstance(loaded, list) else loaded.get("tasks", [])


def _flatten(entries: list[dict]) -> list[dict]:
    """A playbook is a list of PLAYS (hosts + tasks); a role's tasks/main.yml
    is a flat task list that may still wrap a run of tasks in `block:` (e.g.
    roles/backend/tasks/main.yml's restart-guard block, which is where the
    sync task actually lives). Recurse into play.tasks for anything that
    looks like a play (a "hosts" key) -- a play commonly ALSO has "name", so
    that alone cannot tell a play from a task -- and into `block:` bodies."""
    flat: list[dict] = []
    for entry in entries:
        if "hosts" in entry and "tasks" in entry:
            flat.extend(_flatten(entry["tasks"]))
        elif "block" in entry:
            flat.append(entry)
            flat.extend(_flatten(entry["block"]))
        else:
            flat.append(entry)
    return flat


def _index_of(tasks: list[dict], predicate) -> int:
    for i, task in enumerate(tasks):
        if predicate(task):
            return i
    return -1


def _includes_sync_deletions(task: dict) -> bool:
    target = task.get("ansible.builtin.include_tasks") or task.get("include_tasks")
    return bool(target) and _SYNC_DELETIONS_INCLUDE in str(target)


@pytest.mark.parametrize("rel_path,sync_task_name", _SYNC_THEN_DELETE_SITES)
def test_deletion_task_runs_immediately_after_its_sync_task(rel_path: str, sync_task_name: str) -> None:
    tasks = _flatten(_load_tasks(rel_path))
    sync_index = _index_of(tasks, lambda t: sync_task_name in str(t.get("name", "")))
    assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"

    delete_index = _index_of(tasks[sync_index:], _includes_sync_deletions)
    assert delete_index != -1, f"{rel_path}: no sync_deletions.yml include after {sync_task_name!r}"
    # index 0 within the slice would mean the include IS the sync task itself
    assert delete_index > 0, f"{rel_path}: sync_deletions.yml include must be a task AFTER the sync, not the sync"


def test_shared_task_file_writes_the_marker_last() -> None:
    """The marker write must be the LAST task -- it must never run before, or
    concurrently with, the deletion loop it is supposed to follow."""
    tasks = _load_tasks("roles/_shared/tasks/sync_deletions.yml")
    assert tasks, "roles/_shared/tasks/sync_deletions.yml has no tasks"

    delete_loop_index = _index_of(tasks, lambda t: "ansible.builtin.file" in t and t.get("loop") is not None)
    marker_write_index = _index_of(
        tasks, lambda t: ".autobot_sync_deletions_commit" in str(t.get("ansible.builtin.copy", {}).get("dest", ""))
    )

    assert delete_loop_index != -1, "no file:state=absent loop found in sync_deletions.yml"
    assert marker_write_index != -1, "no marker-write task found in sync_deletions.yml"
    assert marker_write_index == len(tasks) - 1, "the marker write must be the LAST task (#16310 review, BLOCKING 1)"
    assert marker_write_index > delete_loop_index, "the marker must be written AFTER the deletion loop, not before"


def test_shared_task_file_never_touches_deployed_commit() -> None:
    """#16310 review, BLOCKING 1: this module must never WRITE .deployed_commit
    -- only a read-only slurp bootstrap of it is allowed."""
    path = _ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "sync_deletions.yml"
    tasks = yaml.safe_load(path.read_text(encoding="utf-8"))

    for task in tasks:
        copy_args = task.get("ansible.builtin.copy")
        if copy_args:
            assert ".deployed_commit" not in str(
                copy_args.get("dest", "")
            ), f"{task.get('name')}: writes .deployed_commit -- the SLM self-update's C4 skip-gate marker"


def test_shared_task_file_has_no_hardcoded_opt_autobot() -> None:
    """#16310 review Standards: {{ autobot.base_dir }}, never a literal."""
    path = _ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "sync_deletions.yml"
    text = path.read_text(encoding="utf-8")
    assert "/opt/autobot" not in text, "sync_deletions.yml hardcodes /opt/autobot -- use {{ autobot.base_dir }}"
