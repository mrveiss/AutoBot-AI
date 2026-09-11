# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310/#16322 review round 12/13: gaps the first wiring test
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
finding 1 (#16310 review round 13, Helper-02 second session): even the
    target_dir pin above was not enough, because PLAY 2 has TWO
    `autobot_shared` deploys sharing the SAME literal
    `sync_deletions_target_dir` ("/opt/autobot/autobot_shared") -- Backend's
    own and, much later, the non-backend-node Shared one. An unbounded
    from-the-sync-task-to-end-of-file search still finds a "match" for
    Backend's site if BACKEND'S OWN deletion include is deleted, because the
    later Shared include has the identical target_dir. A position bound (only
    search up to the NEXT sync task) does not generalize: PLAY 1 syncs all
    five of its components first and runs all five deletions only afterward,
    so nothing sits between one deploy and the next there. Fixed instead by
    pinning on `sync_deletions_label` too -- set on every site, and unique
    per site where target_dir is not.
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
finding 2 (#16310 review round 13): `always:` has no `rescue:` of its own,
    so a failing cleanup task there -- an unreachable target during cleanup,
    a permission error -- would abort the whole PLAY 2 fleet run under
    `any_errors_fatal: true`, contradicting this module's own "one node's
    failure warns, never aborts the fleet" contract. Every task in
    `always:` must be non-fatal (`failed_when: false`).
finding 3 (#16310 review round 13): the fact that picks between the diff
    plan and the bootstrap plan, `_sd_need_bootstrap`, must be filtered
    through `| bool` everywhere it is tested -- Ansible templating can hand
    a fact back as the STRING "False", which is truthy in Jinja, so an
    unfiltered `if _sd_need_bootstrap` would pick the bootstrap plan on
    every diff-mode run once that happens.
"""

from __future__ import annotations

import re

import pytest
from repo_tests.sync_deletions_ansible_wiring_16310_test import (
    _ANSIBLE_ROOT,
    _SHARED_TASK_FILE,
    _UPDATE_ALL_PLAYBOOK,
    _flatten,
    _includes_sync_deletions,
    _index_of,
    _load_tasks,
    _shared_task,
)

# --------------------------------------------------------------------------
# N1/N2/N3/finding 1: sync-site -> deletion-include pinned by target_dir AND
# by the include's own sync_deletions_label.
# --------------------------------------------------------------------------

# (file relative to _ANSIBLE_ROOT, name-substring of the sync task, the exact
# `sync_deletions_target_dir` literal, the exact `sync_deletions_label`
# literal -- the MATCHING deletion include's `vars:` must carry BOTH, not
# just any later sync_deletions.yml include with the same target_dir).
#
# target_dir alone is not unique (finding 1): PLAY 2 has TWO `autobot_shared`
# deploys -- Backend's own and, much later, the non-backend-node Shared one
# -- that share the identical target_dir literal ("/opt/autobot/autobot_shared").
# A position-bounded search (match only up to the NEXT sync task) cannot fix
# this generally: PLAY 1 syncs all five of its components first and only
# THEN runs all five deletions, so nothing sits between one deploy and the
# next -- bounding there would make every PLAY 1 site fail to match at all.
# sync_deletions_label is set on every site, and is unique per site (unlike
# target_dir), so pinning on it too closes the ambiguity without relying on
# task position.
_SYNC_THEN_DELETE_SITES: tuple[tuple[str, str, str, str], ...] = (
    (
        "roles/backend/tasks/main.yml",
        "Sync autobot-backend code from code_source",
        "{{ backend_code_dir }}",
        "Backend",
    ),
    (
        "roles/frontend/tasks/main.yml",
        "Sync frontend code from code_source",
        "{{ frontend_install_dir }}/autobot-frontend",
        "Frontend",
    ),
    (
        "roles/slm_manager/tasks/main.yml",
        "Sync SLM backend code from code_source",
        "{{ slm_backend_dir }}",
        "SLM Backend",
    ),
    (
        "roles/slm_agent/tasks/main.yml",
        "SLM Agent | Copy agent source - heartbeat_payload.py",
        "{{ slm_agent_dir }}/slm/agent",
        "SLM Agent",
    ),
    # update-all-nodes.yml PLAY 1 (SLM self-update) -- all FIVE unarchived
    # components, not just slm-frontend (N2/N3).
    (
        _UPDATE_ALL_PLAYBOOK,
        "SLM | Deploy autobot-slm-backend",
        "{{ autobot.base_dir }}/autobot-slm-backend",
        "SLM Backend (self-update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "SLM | Deploy autobot-slm-frontend",
        "{{ autobot.base_dir }}/autobot-slm-frontend",
        "SLM Frontend (self-update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "SLM | Deploy autobot_shared",
        "{{ autobot.base_dir }}/autobot_shared",
        "SLM autobot_shared (self-update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "SLM | Deploy libs (workspace packages)",
        "{{ autobot.base_dir }}/libs",
        "SLM libs (self-update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "SLM | Deploy autobot-plugins (workspace packages)",
        "{{ autobot.base_dir }}/autobot-plugins",
        "SLM autobot-plugins (self-update)",
    ),
    # update-all-nodes.yml PLAY 2 (fleet update) -- every component it syncs.
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] Backend | Deploy autobot-backend",
        "/opt/autobot/autobot-backend",
        "Backend (fleet update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] Backend | Deploy autobot_shared",
        "/opt/autobot/autobot_shared",
        "Backend autobot_shared (fleet update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] Frontend | Deploy autobot-frontend",
        "/opt/autobot/autobot-frontend",
        "Frontend (fleet update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] NPU | Deploy autobot-npu-worker",
        "/opt/autobot/autobot-npu-worker",
        "NPU worker (fleet update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] Browser | Deploy autobot-browser-worker",
        "/opt/autobot/autobot-browser-worker",
        "Browser worker (fleet update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] AI Stack | Deploy ai_api_server and requirements",
        "/opt/autobot/autobot-ai-stack",
        "AI Stack (fleet update)",
    ),
    (
        _UPDATE_ALL_PLAYBOOK,
        "[PLAY 2] Shared | Deploy autobot_shared",
        "/opt/autobot/autobot_shared",
        "Shared autobot_shared (fleet update)",
    ),
)


def _include_target_dir(task: dict) -> str | None:
    """The `sync_deletions_target_dir` literal a sync_deletions.yml include's
    own `vars:` carries -- None for anything else, including an include that
    omits the var."""
    if not _includes_sync_deletions(task):
        return None
    return (task.get("vars") or {}).get("sync_deletions_target_dir")


def _include_matches_site(task: dict, target_dir: str, label: str) -> bool:
    """True only for a sync_deletions.yml include whose `vars:` carry BOTH
    this exact target_dir AND this exact sync_deletions_label (finding 1) --
    target_dir alone is not unique across sites, but the pair is."""
    if not _includes_sync_deletions(task):
        return False
    v = task.get("vars") or {}
    return v.get("sync_deletions_target_dir") == target_dir and v.get("sync_deletions_label") == label


@pytest.mark.parametrize("rel_path,sync_task_name,target_dir,label", _SYNC_THEN_DELETE_SITES)
def test_deletion_task_matching_target_dir_follows_its_sync_task(
    rel_path: str, sync_task_name: str, target_dir: str, label: str
) -> None:
    tasks = _flatten(_load_tasks(rel_path))
    sync_index = _index_of(tasks, lambda t: sync_task_name in str(t.get("name", "")))
    assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"

    delete_index = _index_of(tasks[sync_index:], lambda t: _include_matches_site(t, target_dir, label))
    assert delete_index != -1, (
        f"{rel_path}: no sync_deletions.yml include with target_dir {target_dir!r} and label {label!r} "
        f"found after {sync_task_name!r}"
    )
    assert delete_index > 0, f"{rel_path}: the matching include must be a task AFTER the sync, not the sync itself"


_PLANTED_TARGET_DIR = "/opt/autobot/autobot_shared"
# Two sync sites share one target_dir -- Backend's own and a later Shared
# one, each with its OWN distinct label. Backend's OWN deletion include is
# the planted bug: absent here, on purpose.
_PLANTED_BACKEND_REMOVED_TASKS: list[dict] = [
    {"name": "[PLAY 2] Backend | Deploy autobot_shared"},
    {"name": "[PLAY 2] Shared | Deploy autobot_shared"},
    {
        "name": "[PLAY 2] Shared | Delete files removed from source: autobot_shared (#16310)",
        "ansible.builtin.include_tasks": "../roles/_shared/tasks/sync_deletions.yml",
        "vars": {
            "sync_deletions_target_dir": _PLANTED_TARGET_DIR,
            "sync_deletions_label": "Shared autobot_shared (fleet update)",
        },
    },
]


def test_planted_regression_a_removed_include_is_not_masked_by_a_later_shared_target() -> None:
    """finding 1's self-test: with Backend's OWN deletion include deleted,
    matching on target_dir ALONE (the old behavior) still finds a "match"
    via the later Shared include -- proving the bug is real -- while
    matching on target_dir AND label (the fix) correctly reports no match."""
    tasks = _PLANTED_BACKEND_REMOVED_TASKS
    sync_index = _index_of(tasks, lambda t: "[PLAY 2] Backend | Deploy autobot_shared" in str(t.get("name", "")))
    assert sync_index == 0

    # The bug: target_dir alone still matches, via the later, unrelated
    # Shared include.
    target_dir_only = _index_of(tasks[sync_index:], lambda t: _include_target_dir(t) == _PLANTED_TARGET_DIR)
    assert target_dir_only != -1, "self-test setup is wrong: the planted Shared include should still be reachable"

    # The fix: target_dir AND label together never reach it -- the Shared
    # include's label is never Backend's own.
    backend_label = "Backend autobot_shared (fleet update)"
    fixed = _index_of(tasks[sync_index:], lambda t: _include_matches_site(t, _PLANTED_TARGET_DIR, backend_label))
    assert fixed == -1


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


# --------------------------------------------------------------------------
# finding 2: every `always:` cleanup task is non-fatal, so a failing one
# cannot abort the whole fleet under PLAY 2's any_errors_fatal: true.
# --------------------------------------------------------------------------


def _non_fatal_cleanup_task_names(always_tasks: list[dict]) -> list[str]:
    """Names of any task in an `always:` list that is not provably non-fatal
    (`failed_when: false`) -- empty once every task there is safe."""
    return [str(t.get("name")) for t in always_tasks if t.get("failed_when") is not False]


def test_always_cleanup_tasks_are_never_fatal() -> None:
    task = _shared_task()
    offenders = _non_fatal_cleanup_task_names(task["always"])
    assert not offenders, (
        f"always: task(s) without `failed_when: false`: {offenders} -- a failure there can abort the whole "
        "fleet under PLAY 2's any_errors_fatal (#16310 review round 13, finding 2)"
    )


def test_planted_regression_a_fatal_cleanup_task_is_caught() -> None:
    """Self-test: a synthetic always: list with one task missing
    `failed_when: false` must be reported by the checker above."""
    synthetic = [
        {"name": "safe", "ansible.builtin.file": {"path": "/tmp/a", "state": "absent"}, "failed_when": False},
        {"name": "planted fatal cleanup", "ansible.builtin.file": {"path": "/tmp/b", "state": "absent"}},
    ]
    assert _non_fatal_cleanup_task_names(synthetic) == ["planted fatal cleanup"]


# --------------------------------------------------------------------------
# finding 3: every use of `_sd_need_bootstrap` (a fact that can come back as
# the truthy STRING "False") is filtered through `| bool`.
# --------------------------------------------------------------------------

_BOOTSTRAP_FACT_ASSIGNMENT = re.compile(r"^\s*_sd_need_bootstrap:\s*>-\s*$")
_BOOTSTRAP_FACT_USE = re.compile(r"_sd_need_bootstrap(?!\w)(\s*\|\s*bool)?")


def _unfiltered_bootstrap_fact_lines(text: str) -> list[str]:
    """Lines that reference `_sd_need_bootstrap` as a Jinja value -- never
    its own `set_fact:` assignment target, never a comment -- where the
    reference is NOT immediately filtered through `| bool`. Empty once the
    fix holds everywhere."""
    offenders = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or _BOOTSTRAP_FACT_ASSIGNMENT.match(line):
            continue
        if any(match.group(1) is None for match in _BOOTSTRAP_FACT_USE.finditer(line)):
            offenders.append(stripped)
    return offenders


def test_bootstrap_fact_uses_are_bool_filtered() -> None:
    text = _SHARED_TASK_FILE.read_text(encoding="utf-8")
    offenders = _unfiltered_bootstrap_fact_lines(text)
    assert not offenders, (
        f"_sd_need_bootstrap used without `| bool` on: {offenders} -- Ansible templating can hand this fact "
        'back as the STRING "False", which is truthy in Jinja, so an unfiltered `if _sd_need_bootstrap` picks '
        "the bootstrap plan on every diff-mode run once that happens (#16310 review round 13, finding 3)"
    )


def test_planted_regression_an_unfiltered_bootstrap_use_is_caught() -> None:
    """Self-test: a synthetic snippet with one filtered and one unfiltered
    use must report only the unfiltered one."""
    synthetic = "when: _sd_need_bootstrap\nwhen: _sd_need_bootstrap | bool\n"
    assert _unfiltered_bootstrap_fact_lines(synthetic) == ["when: _sd_need_bootstrap"]


def test_the_ansible_root_constant_still_resolves() -> None:
    """Guard the import: if _ANSIBLE_ROOT ever moved, every test above would
    fail with a confusing FileNotFoundError instead of this clear message."""
    assert _ANSIBLE_ROOT.is_dir(), f"{_ANSIBLE_ROOT} not found -- imported constant is stale"
