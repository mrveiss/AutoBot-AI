# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310/#16322 review round 12: three gaps the first wiring test
(repo_tests/sync_deletions_ansible_wiring_16310_test.py) did not catch.

Lives in its OWN file rather than growing that one: it is frozen at its
#5060 file-size ceiling (674 lines -- see
scripts/python_file_size_known_large.py) -- "a grandfathered file may not
grow" (#14236) -- so new coverage for the same subject goes here instead of
pushing it over. Reuses that file's own YAML-parsing helpers by import
rather than re-deriving them, so the two never quietly disagree about how a
task list is flattened or a deletion include is recognized.

N1: the first test's ordering check accepted ANY later `sync_deletions.yml`
    include as a match for a sync site -- so deleting the PLAY 2 "Backend
    autobot_shared" deletion task still passed the check for that site,
    because the very next (unrelated) deletion include, PLAY 2 Backend's
    OWN, matched instead. Pinned here by the exact `sync_deletions_target_dir`
    the matching include's `vars:` must carry.
N2: two PLAY 1 sync sites (slm-backend, autobot_shared) were never pinned by
    any test at all -- only slm-frontend was.
N3: `libs` and `autobot-plugins` (#15462 workspace packages) are unarchived
    in PLAY 1 but had no deletion pass whatsoever -- both wired
    (update-all-nodes.yml) and pinned here now.
B1: every `shell:` task using bash-only syntax (`pipefail`, `[[`, `<<<`, an
    array assignment, `$'...'`) in a task file this PR added must declare
    `args: executable: /bin/bash` -- without it, ansible runs `shell:` under
    `/bin/sh` (dash on Ubuntu), which rejects `set -o pipefail` ("Illegal
    option", rc 2), so the deletion task always landed in `rescue` and
    NOTHING was ever deleted on an Ubuntu host.
N5: both temp files the shared task allocates (the controller-side
    present-files list, the target-side delete-list file) must be removed
    in `always:`, regardless of how the block exited -- a rescue-only or
    success-only cleanup would leak one of them on the other path.
"""

from __future__ import annotations

import re

import pytest
from repo_tests.sync_deletions_ansible_wiring_16310_test import (
    _ANSIBLE_ROOT,
    _UPDATE_ALL_PLAYBOOK,
    _flatten,
    _includes_sync_deletions,
    _index_of,
    _load_tasks,
    _shared_task,
)

# --------------------------------------------------------------------------
# N1/N2/N3: sync-site -> deletion-include pinned by target_dir
# --------------------------------------------------------------------------

# (file relative to _ANSIBLE_ROOT, name-substring of the sync task, the exact
# `sync_deletions_target_dir` literal the MATCHING deletion include's
# `vars:` must carry -- not just any later sync_deletions.yml include).
_SYNC_THEN_DELETE_SITES: tuple[tuple[str, str, str], ...] = (
    ("roles/backend/tasks/main.yml", "Sync autobot-backend code from code_source", "{{ backend_code_dir }}"),
    (
        "roles/frontend/tasks/main.yml",
        "Sync frontend code from code_source",
        "{{ frontend_install_dir }}/autobot-frontend",
    ),
    ("roles/slm_manager/tasks/main.yml", "Sync SLM backend code from code_source", "{{ slm_backend_dir }}"),
    (
        "roles/slm_agent/tasks/main.yml",
        "SLM Agent | Copy agent source - heartbeat_payload.py",
        "{{ slm_agent_dir }}/slm/agent",
    ),
    # update-all-nodes.yml PLAY 1 (SLM self-update) -- all FIVE unarchived
    # components, not just slm-frontend (N2/N3).
    (_UPDATE_ALL_PLAYBOOK, "SLM | Deploy autobot-slm-backend", "{{ autobot.base_dir }}/autobot-slm-backend"),
    (_UPDATE_ALL_PLAYBOOK, "SLM | Deploy autobot-slm-frontend", "{{ autobot.base_dir }}/autobot-slm-frontend"),
    (_UPDATE_ALL_PLAYBOOK, "SLM | Deploy autobot_shared", "{{ autobot.base_dir }}/autobot_shared"),
    (_UPDATE_ALL_PLAYBOOK, "SLM | Deploy libs (workspace packages)", "{{ autobot.base_dir }}/libs"),
    (
        _UPDATE_ALL_PLAYBOOK,
        "SLM | Deploy autobot-plugins (workspace packages)",
        "{{ autobot.base_dir }}/autobot-plugins",
    ),
    # update-all-nodes.yml PLAY 2 (fleet update) -- every component it syncs.
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Backend | Deploy autobot-backend", "/opt/autobot/autobot-backend"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Backend | Deploy autobot_shared", "/opt/autobot/autobot_shared"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Frontend | Deploy autobot-frontend", "/opt/autobot/autobot-frontend"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] NPU | Deploy autobot-npu-worker", "/opt/autobot/autobot-npu-worker"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Browser | Deploy autobot-browser-worker", "/opt/autobot/autobot-browser-worker"),
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] AI Stack | Deploy ai_api_server and requirements",
        "/opt/autobot/autobot-ai-stack",
    ),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Shared | Deploy autobot_shared", "/opt/autobot/autobot_shared"),
)


def _include_target_dir(task: dict) -> str | None:
    """The `sync_deletions_target_dir` literal a sync_deletions.yml include's
    own `vars:` carries -- None for anything else, including an include that
    omits the var."""
    if not _includes_sync_deletions(task):
        return None
    return (task.get("vars") or {}).get("sync_deletions_target_dir")


@pytest.mark.parametrize("rel_path,sync_task_name,target_dir", _SYNC_THEN_DELETE_SITES)
def test_deletion_task_matching_target_dir_follows_its_sync_task(
    rel_path: str, sync_task_name: str, target_dir: str
) -> None:
    tasks = _flatten(_load_tasks(rel_path))
    sync_index = _index_of(tasks, lambda t: sync_task_name in str(t.get("name", "")))
    assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"

    delete_index = _index_of(tasks[sync_index:], lambda t: _include_target_dir(t) == target_dir)
    assert (
        delete_index != -1
    ), f"{rel_path}: no sync_deletions.yml include with target_dir {target_dir!r} found after {sync_task_name!r}"
    assert delete_index > 0, f"{rel_path}: the matching include must be a task AFTER the sync, not the sync itself"


# --------------------------------------------------------------------------
# B1: bash-only shell tasks in a file THIS PR added must declare the bash
# executable, or ansible runs them under dash on Ubuntu.
# --------------------------------------------------------------------------

_NEW_TASK_FILES: tuple[str, ...] = (
    "roles/_shared/tasks/sync_deletions.yml",
    "roles/backend/tasks/npu_workers_cleanup.yml",
)
_BASH_ONLY_SUBSTRINGS: tuple[str, ...] = ("pipefail", "[[", "<<<", "$'")
_BASH_ARRAY_ASSIGNMENT = re.compile(r"\b\w+=\(")


def _uses_bash_only_syntax(script: str) -> bool:
    if any(marker in script for marker in _BASH_ONLY_SUBSTRINGS):
        return True
    return bool(_BASH_ARRAY_ASSIGNMENT.search(script))


def _shell_script(task: dict) -> str | None:
    shell = task.get("ansible.builtin.shell") or task.get("shell")
    if shell is None:
        return None
    return shell["cmd"] if isinstance(shell, dict) else str(shell)


def _bash_only_shell_tasks(rel_path: str) -> list[dict]:
    tasks = _flatten(_load_tasks(rel_path))
    scripts = ((t, _shell_script(t)) for t in tasks)
    return [t for t, script in scripts if script is not None and _uses_bash_only_syntax(script)]


@pytest.mark.parametrize("rel_path", _NEW_TASK_FILES)
def test_bash_only_shell_tasks_declare_the_bash_executable(rel_path: str) -> None:
    # A file this PR added need not contain a bash-only `shell:` task at all
    # (npu_workers_cleanup.yml has none) -- only every ONE it does have must
    # declare the executable.
    for task in _bash_only_shell_tasks(rel_path):
        executable = (task.get("args") or {}).get("executable")
        assert executable == "/bin/bash", (
            f"{rel_path}: {task.get('name')!r} uses bash-only syntax but does not declare "
            "`args: {executable: /bin/bash}` -- runs under /bin/sh (dash on Ubuntu) otherwise, which errors "
            "on `set -o pipefail` and sends every run to `rescue` (#16310 review round 12, B1)"
        )


def test_the_guard_can_see_a_bash_only_shell_task() -> None:
    """Guard the guard: sync_deletions.yml must actually contain at least one
    bash-only `shell:` task, or the check above passes vacuously."""
    assert _bash_only_shell_tasks("roles/_shared/tasks/sync_deletions.yml"), (
        "sync_deletions.yml has no bash-only shell task anymore -- "
        "test_bash_only_shell_tasks_declare_the_bash_executable would pass vacuously"
    )


# --------------------------------------------------------------------------
# N5: both temp files removed in `always:`, regardless of outcome.
# --------------------------------------------------------------------------


def _removes_path_var(task: dict, path_var: str) -> bool:
    file_args = task.get("ansible.builtin.file") or {}
    return file_args.get("state") == "absent" and path_var in str(file_args.get("path", ""))


def test_temp_files_are_removed_in_always_regardless_of_outcome() -> None:
    task = _shared_task()
    assert task.get("always"), "sync_deletions.yml's one task has no `always:` -- temp files leak on failure"

    always = task["always"]
    assert any(
        _removes_path_var(sub, "_sd_present_file") for sub in always
    ), "always: must remove the controller-side present-files list (_sd_present_file)"
    assert any(
        _removes_path_var(sub, "_sd_delete_list_file") for sub in always
    ), "always: must remove the target-side delete-list file (_sd_delete_list_file)"


def test_temp_file_cleanup_is_never_only_in_rescue() -> None:
    """A cleanup task living ONLY in `rescue:` would never run on the
    success path -- both files must be cleaned up in `always:`."""
    task = _shared_task()
    for sub in task["rescue"]:
        assert not _removes_path_var(sub, "_sd_present_file"), "present-files cleanup belongs in always:, not rescue:"
        assert not _removes_path_var(sub, "_sd_delete_list_file"), "delete-list cleanup belongs in always:, not rescue:"


def test_the_ansible_root_constant_still_resolves() -> None:
    """Guard the import: if _ANSIBLE_ROOT ever moved, every test above would
    fail with a confusing FileNotFoundError instead of this clear message."""
    assert _ANSIBLE_ROOT.is_dir(), f"{_ANSIBLE_ROOT} not found -- imported constant is stale"
