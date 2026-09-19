# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310 host evidence, 2026-09-19: `code_source` is still a shallow git
clone on a live host, and every deletion marker on disk today was written
BEFORE `services/sync_deletions.py`'s shallow-clone guard existed, so each
component is stuck in diff-only mode from an empty bootstrap baseline
forever. Two fixes, both asserted here against the ansible wiring (the
Python-side halves -- ``services.git_subprocess.ensure_full_history`` and
``compute_bootstrap_plan``'s shallow guard -- have their own colocated
tests: ``tests/services/git_subprocess_test.py`` and
``tests/services/sync_deletions_shallow_bootstrap_test.py``):

1. Every ``code_source`` fetch (``update-all-nodes.yml``,
   ``pre-flight-code-sync.yml``, ``provision-fleet-roles.yml``) runs an
   "ensure full history" step, through the same CLI the diff/bootstrap
   plans use, immediately after its own "Sync ... from GitHub" task.
2. The deletion marker gains a version line
   (``services/deploy_artifacts.py``'s ``SYNC_DELETIONS_MARKER_VERSION``,
   mirrored as a literal in ``sync_deletions.yml``'s ``_sd_marker_version``
   -- the SAME lockstep pattern
   ``sync_deletions_ansible_wiring_16310_test.py``'s own
   ``test_bootstrap_find_prunes_the_same_artifact_vocabulary_as_deploy_artifacts``
   already uses for ``ARTIFACT_DIRS``). A marker in the old, unversioned,
   bare-SHA format reads as legacy and forces exactly one bootstrap
   re-run before it is upgraded.

Lives in its own file rather than growing
``sync_deletions_ansible_wiring_16310_test.py``, which is frozen at its own
#14236 file-size ceiling (see ``scripts/python_file_size_known_large.py``).
Reuses that file's own YAML-parsing helpers by import, so this file and it
never quietly disagree about how a task list is flattened or read.
"""

from __future__ import annotations

import ast
import re

import pytest
from repo_tests._paths import repo_root
from repo_tests.sync_deletions_ansible_wiring_16310_test import (
    _SHARED_TASK_FILE,
    _UPDATE_ALL_PLAYBOOK,
    _flatten,
    _index_of,
    _load_tasks,
    _shared_task,
)

_REPO_ROOT = repo_root()
_DEPLOY_ARTIFACTS = _REPO_ROOT / "autobot-slm-backend" / "services" / "deploy_artifacts.py"
_ENSURE_FULL_HISTORY_MARKER = "ensure-full-history"

# (playbook path relative to _ANSIBLE_ROOT, the sync task's own name).
_CODE_SOURCE_FETCH_SITES: tuple[tuple[str, str], ...] = (
    (_UPDATE_ALL_PLAYBOOK, "[PRE-FLIGHT] Sync code from GitHub"),
    ("playbooks/pre-flight-code-sync.yml", "[PRE-FLIGHT] Sync latest code from GitHub (if reachable)"),
    ("playbooks/provision-fleet-roles.yml", "[PRE-FLIGHT] Sync latest code from GitHub (if reachable)"),
)


def _task_command_cmd(task: dict) -> str:
    """The shell text of a `command:`/`ansible.builtin.command:` task,
    whichever shape it uses -- the free-form string shorthand
    (``command: git ...``) or the dict form (``command: {cmd: git ...}``).
    A predicate that assumes only the dict form crashes (AttributeError) the
    moment it is asked about a shorthand task, which several sibling
    pre-flight tasks in these playbooks use (#16310)."""
    value = task.get("ansible.builtin.command", task.get("command", ""))
    if isinstance(value, dict):
        return str(value.get("cmd", ""))
    return str(value)


def _read_literal_string(source: str, var_name: str) -> str:
    """The string value of *var_name*'s top-level literal assignment, read
    with ``ast`` -- repo_tests cannot import autobot-slm-backend packages
    (a separate source root), and a by-path load would pull in
    deploy_artifacts.py's own imports too (see
    ``sync_deletions_ansible_wiring_16310_test.py``'s
    ``_read_literal_string_collection``, the same rationale)."""
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            target_names = [node.target.id]
        elif isinstance(node, ast.Assign):
            target_names = [t.id for t in node.targets if isinstance(t, ast.Name)]
        else:
            continue
        if var_name not in target_names:
            continue
        assert isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, str
        ), f"{var_name}: expected a literal string constant, found {type(node.value).__name__} instead"
        return node.value.value
    raise AssertionError(f"{var_name}: no assignment found in {len(source.splitlines())}-line source")


# --------------------------------------------------------------------------
# Fix 1: an "ensure full history" step after every code_source fetch.
# --------------------------------------------------------------------------


def _is_ensure_full_history(task: dict) -> bool:
    return _ENSURE_FULL_HISTORY_MARKER in _task_command_cmd(task)


def _ensure_full_history_task_after(tasks: list[dict], sync_index: int, rel_path: str) -> dict:
    ensure_index = _index_of(tasks[sync_index:], _is_ensure_full_history)
    assert ensure_index != -1, f"{rel_path}: no {_ENSURE_FULL_HISTORY_MARKER!r} task found after the code_source sync"
    assert ensure_index > 0, f"{rel_path}: the {_ENSURE_FULL_HISTORY_MARKER!r} task must follow the sync, not be it"
    return tasks[sync_index:][ensure_index]


@pytest.mark.parametrize("rel_path,sync_task_name", _CODE_SOURCE_FETCH_SITES)
def test_ensure_full_history_runs_immediately_after_the_code_source_fetch(rel_path: str, sync_task_name: str) -> None:
    tasks = _flatten(_load_tasks(rel_path))
    sync_index = _index_of(tasks, lambda t: sync_task_name in str(t.get("name", "")))
    assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"

    _ensure_full_history_task_after(tasks, sync_index, rel_path)


@pytest.mark.parametrize("rel_path,sync_task_name", _CODE_SOURCE_FETCH_SITES)
def test_ensure_full_history_uses_the_same_cli_the_deletion_plans_use(rel_path: str, sync_task_name: str) -> None:
    """Never an ad-hoc `git fetch --unshallow` in the playbook itself --
    routed through scripts/sync_deletion_planner.py, the same CLI
    roles/_shared/tasks/sync_deletions.yml calls for diff/bootstrap plans,
    so there is exactly one place `run_git` is invoked from (#16310)."""
    tasks = _flatten(_load_tasks(rel_path))
    sync_index = _index_of(tasks, lambda t: sync_task_name in str(t.get("name", "")))
    assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"

    task = _ensure_full_history_task_after(tasks, sync_index, rel_path)
    cmd = _task_command_cmd(task)
    assert "sync_deletion_planner.py" in cmd
    assert "--repo-root" in cmd


@pytest.mark.parametrize("rel_path,sync_task_name", _CODE_SOURCE_FETCH_SITES)
def test_ensure_full_history_task_does_not_ignore_errors(rel_path: str, sync_task_name: str) -> None:
    """#16310: "surface failure as an explicit error, never swallow it" --
    none of the three sites may set `ignore_errors: true` on this task (the
    offline-tolerance `when: github_sync is not failed` gate is the only
    permitted way to skip it)."""
    tasks = _flatten(_load_tasks(rel_path))
    sync_index = _index_of(tasks, lambda t: sync_task_name in str(t.get("name", "")))
    assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"

    task = _ensure_full_history_task_after(tasks, sync_index, rel_path)
    assert (
        task.get("ignore_errors") is not True
    ), f"{rel_path}: the ensure-full-history task ignores errors -- a failed unshallow must fail the play"


# --------------------------------------------------------------------------
# Fix 2: a versioned marker forces exactly one bootstrap re-run for a
# legacy (pre-versioning) marker.
# --------------------------------------------------------------------------


def test_marker_version_literal_matches_deploy_artifacts_constant() -> None:
    deploy_artifacts_source = _DEPLOY_ARTIFACTS.read_text(encoding="utf-8")
    expected = _read_literal_string(deploy_artifacts_source, "SYNC_DELETIONS_MARKER_VERSION")

    text = _SHARED_TASK_FILE.read_text(encoding="utf-8")
    match = re.search(r"_sd_marker_version:\s*[\"']([^\"']+)[\"']", text)
    assert match, 'no `_sd_marker_version: "..."` set_fact found in sync_deletions.yml'
    assert match.group(1) == expected, (
        f"sync_deletions.yml's _sd_marker_version ({match.group(1)!r}) does not match "
        f"deploy_artifacts.SYNC_DELETIONS_MARKER_VERSION ({expected!r})"
    )


def test_marker_write_includes_the_version_line() -> None:
    task = _shared_task()
    marker_write = next(
        (
            sub
            for sub in task["block"]
            if ".autobot_sync_deletions_commit" in str(sub.get("ansible.builtin.copy", {}).get("dest", ""))
        ),
        None,
    )
    assert marker_write is not None, "no marker-write task found"
    content = str(marker_write["ansible.builtin.copy"].get("content", ""))
    assert "_sd_marker_version" in content, "the marker write must include the version line (#16310)"


def test_a_legacy_marker_is_distinguished_from_the_current_format() -> None:
    """The settle-on-previous-commit logic must actually branch on
    _sd_own_marker_is_legacy -- a marker existing is not, by itself, enough
    to pick diff mode any more."""
    text = _SHARED_TASK_FILE.read_text(encoding="utf-8")
    assert "_sd_own_marker_is_legacy" in text
    # The fact must be computed from the marker's OWN content, not derived
    # from something else entirely (e.g. always False).
    legacy_fact = re.search(r"_sd_own_marker_is_legacy:\s*>-\s*(.*?)\n\n", text, re.DOTALL)
    assert legacy_fact, "no _sd_own_marker_is_legacy set_fact body found"
    assert "_sd_marker_version" in legacy_fact.group(1)
    assert "_sd_own_marker_lines" in legacy_fact.group(1)


def test_previous_commit_is_empty_for_a_legacy_marker() -> None:
    """The settle-on-previous-commit fact must read '' (forcing bootstrap,
    the same as no marker at all) when the marker is legacy -- never fall
    through to treating the legacy content as a trustworthy commit."""
    text = _SHARED_TASK_FILE.read_text(encoding="utf-8")
    settle = re.search(r"_sd_previous_commit:\s*>-\s*(.*?)\n\n", text, re.DOTALL)
    assert settle, "no _sd_previous_commit set_fact body found"
    body = settle.group(1)
    assert "_sd_own_marker_is_legacy" in body
    # The legacy branch's own result must be the empty string.
    assert re.search(
        r"''\s*\n\s*if \(_sd_own_marker is succeeded and _sd_own_marker_is_legacy", body
    ), "the legacy-marker branch of _sd_previous_commit does not resolve to '' (forcing bootstrap)"
