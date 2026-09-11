# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#16310 owner decision: every role that syncs code runs the deletion tasks
right after its own sync task, and writes this module's marker only after
deletion succeeds -- inside a block/rescue so one node's planning failure
never aborts the fleet (#16310 review, BLOCKING 2), and only after resolving
each candidate's real path on the target so a symlinked parent cannot escape
the deployed dir (#16310 review, HIGH). Asserted on task ORDER and structure,
not text -- a deletion task present anywhere in the file would pass a
substring check while still running before the sync it is supposed to
follow, inside no failure boundary, or with no containment check at all.

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

import re

import pytest
import yaml
from repo_tests._paths import repo_root

_REPO_ROOT = repo_root()
_ANSIBLE_ROOT = _REPO_ROOT / "autobot-slm-backend" / "ansible"
_SHARED_TASK_FILE = _ANSIBLE_ROOT / "roles" / "_shared" / "tasks" / "sync_deletions.yml"
_SYNC_DELETIONS_INCLUDE = "sync_deletions.yml"
_MARKER = ".autobot_sync_deletions_commit"

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


def _shared_task() -> dict:
    """The single top-level `name` + `block` + `rescue` task in the shared file."""
    tasks = _load_tasks("roles/_shared/tasks/sync_deletions.yml")
    assert len(tasks) == 1, f"expected exactly one top-level task (block/rescue), found {len(tasks)}"
    task = tasks[0]
    assert "block" in task and "rescue" in task, "sync_deletions.yml's one task must be a block/rescue (#16310)"
    return task


def _writes_marker(task: dict) -> bool:
    return _MARKER in str(task.get("ansible.builtin.copy", {}).get("dest", ""))


@pytest.mark.parametrize("rel_path,sync_task_name", _SYNC_THEN_DELETE_SITES)
def test_deletion_task_runs_immediately_after_its_sync_task(rel_path: str, sync_task_name: str) -> None:
    tasks = _flatten(_load_tasks(rel_path))
    sync_index = _index_of(tasks, lambda t: sync_task_name in str(t.get("name", "")))
    assert sync_index != -1, f"{rel_path}: sync task {sync_task_name!r} not found"

    delete_index = _index_of(tasks[sync_index:], _includes_sync_deletions)
    assert delete_index != -1, f"{rel_path}: no sync_deletions.yml include after {sync_task_name!r}"
    # index 0 within the slice would mean the include IS the sync task itself
    assert delete_index > 0, f"{rel_path}: sync_deletions.yml include must be a task AFTER the sync, not the sync"


# --------------------------------------------------------------------------
# BLOCKING 1: bootstrap enumeration cost
# --------------------------------------------------------------------------


def test_bootstrap_find_prunes_the_same_artifact_vocabulary_as_deploy_artifacts() -> None:
    """The `find ... -prune` name list must match ARTIFACT_DIRS/
    ARTIFACT_DIR_SUFFIXES exactly -- a hand-mirrored copy that drifts is the
    #14231 failure mode arriving in a new place."""
    from services.deploy_artifacts import ARTIFACT_DIR_SUFFIXES, ARTIFACT_DIRS

    text = _SHARED_TASK_FILE.read_text(encoding="utf-8")
    find_block = re.search(r"find .*?-prune", text, re.DOTALL)
    assert find_block, "no `find ... -prune` command found in sync_deletions.yml"

    names = set(re.findall(r"-name\s+'?\*?([\w.\-]+)'?", find_block.group(0)))
    # ARTIFACT_DIR_SUFFIXES entries (".egg-info") are matched via `*.egg-info`;
    # stripping only the leading `*` (not the dot) leaves ".egg-info", matching
    # the literal suffix value -- no dot-stripping on either side.
    expected = set(ARTIFACT_DIRS) | set(ARTIFACT_DIR_SUFFIXES)
    missing = expected - names
    assert missing == set(), f"find -prune is missing artifact names: {missing}"


def test_no_ansible_find_module_walks_the_full_target_tree() -> None:
    """ansible.builtin.find's `excludes:` only trims the RESULT list, not the
    walk -- it must not be used for the present-files enumeration, or a
    venv/node_modules tree gets walked file-by-file regardless."""
    task = _shared_task()
    for sub in task["block"]:
        assert "ansible.builtin.find" not in sub, (
            f"{sub.get('name')}: ansible.builtin.find walks the whole tree even with excludes -- "
            "use `find ... -prune` (ansible.builtin.command) instead"
        )


# --------------------------------------------------------------------------
# BLOCKING 2: blast radius -- block/rescue, marker never written on failure
# --------------------------------------------------------------------------


def test_deletion_tasks_are_wrapped_in_a_block_with_a_rescue() -> None:
    task = _shared_task()
    assert task["block"], "block is empty"
    assert task["rescue"], "rescue is empty"


def test_rescue_never_writes_the_marker() -> None:
    task = _shared_task()
    for sub in task["rescue"]:
        assert not _writes_marker(sub), "rescue must never write the marker -- the next run must retry"


def test_rescue_reports_the_component_target_and_error() -> None:
    task = _shared_task()
    messages = " ".join(str(sub.get("ansible.builtin.debug", {}).get("msg", "")) for sub in task["rescue"])
    assert "sync_deletions_label" in messages or "{{ sync_deletions_label" in messages
    assert "sync_deletions_target_dir" in messages or "{{ sync_deletions_target_dir" in messages
    assert "ansible_failed_result" in messages, "rescue must surface the actual error, not just a static message"


def test_marker_write_is_the_last_task_in_the_block() -> None:
    """The marker write must be the LAST task in the block -- it must never
    run before, or concurrently with, the deletion step it is supposed to
    follow (#16310 review, BLOCKING 1's ordering rule)."""
    task = _shared_task()
    block = task["block"]
    marker_index = _index_of(block, _writes_marker)
    assert marker_index != -1, "no marker-write task found in the block"
    assert marker_index == len(block) - 1, "the marker write must be the LAST task in the block"


def test_shared_task_file_never_touches_deployed_commit() -> None:
    """#16310 review, BLOCKING 1: this module must never WRITE .deployed_commit
    -- only a read-only slurp bootstrap of it is allowed."""
    task = _shared_task()
    for sub in task["block"] + task["rescue"]:
        copy_args = sub.get("ansible.builtin.copy")
        if copy_args:
            assert ".deployed_commit" not in str(
                copy_args.get("dest", "")
            ), f"{sub.get('name')}: writes .deployed_commit -- the SLM self-update's C4 skip-gate marker"


# --------------------------------------------------------------------------
# HIGH: symlinked parent on the target
# --------------------------------------------------------------------------


def test_the_delete_step_resolves_containment_before_removing_anything() -> None:
    """The deletion step must consume only the contained list -- resolved on
    the TARGET (the controller cannot see a remote target's real filesystem),
    never trusting the (lexically-checked-only) planner output alone."""
    task = _shared_task()
    delete_step = next((sub for sub in task["block"] if "remove" in str(sub.get("name", "")).lower()), None)
    assert delete_step is not None, "no deletion step found in the block"

    body = str(delete_step.get("ansible.builtin.shell", {}).get("cmd", ""))
    assert "realpath" in body, "the deletion step must resolve real paths before removing anything"
    assert "root_real" in body and "cand_real" in body, "the deletion step must compare candidate to root real paths"
    # No blind `ansible.builtin.file: state=absent` loop over the raw plan.
    assert "ansible.builtin.file" not in delete_step or delete_step.get("ansible.builtin.file", {}).get("state") != (
        "absent"
    )


# --------------------------------------------------------------------------
# Standards
# --------------------------------------------------------------------------


def test_shared_task_file_has_no_hardcoded_opt_autobot() -> None:
    """#16310 review Standards: {{ autobot.base_dir }}, never a literal."""
    text = _SHARED_TASK_FILE.read_text(encoding="utf-8")
    assert "/opt/autobot" not in text, "sync_deletions.yml hardcodes /opt/autobot -- use {{ autobot.base_dir }}"


# --------------------------------------------------------------------------
# BLOCKING 3: the marker must never be wiped by a delete-style sync
# --------------------------------------------------------------------------


def _delete_style_syncs() -> list[tuple[str, str, dict]]:
    found = []
    for path in sorted(_ANSIBLE_ROOT.rglob("*.yml")):
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:  # pragma: no cover - malformed files fail elsewhere
            continue

        def walk(node):
            if isinstance(node, list):
                for item in node:
                    walk(item)
            elif isinstance(node, dict):
                sync = node.get("ansible.posix.synchronize") or node.get("synchronize")
                if isinstance(sync, dict) and sync.get("delete"):
                    found.append((path.relative_to(_ANSIBLE_ROOT).as_posix(), node.get("name"), sync))
                for value in node.values():
                    walk(value)

        walk(document)
    return found


def test_every_delete_style_sync_excludes_the_deletion_marker() -> None:
    """#16310 review, BLOCKING 3: roles/slm_manager's `delete: true` sync
    deleted the marker before the next run's slurp, every time. Direct
    companion to tests/api/test_host_state_excludes_14231.py's generic
    HOST_STATE_EXCLUDES check -- asserted here by name too since this IS the
    exact bug that check now also catches once SYNC_DELETIONS_MARKER is in
    HOST_STATE_EXCLUDES."""
    syncs = _delete_style_syncs()
    assert len(syncs) >= 6, f"only {len(syncs)} delete-style syncs found -- the scan did not reach the ansible tree"

    gaps = [
        f"{source}: {name}" for source, name, sync in syncs if f"--exclude=/{_MARKER}" not in sync.get("rsync_opts", [])
    ]
    assert gaps == [], f"delete-style sync(s) do not exclude the deletion marker: {gaps}"
