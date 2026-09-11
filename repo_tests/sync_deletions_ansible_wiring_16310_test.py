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

Covers roles/backend, roles/frontend, roles/slm_manager (SLM backend),
roles/slm_agent (its own main.yml, imported in full by update-all-nodes.yml
on both plays -- #16310 review round 6), and playbooks/update-all-nodes.yml
directly for every component PLAY 1/PLAY 2 actually sync (self-update:
slm-backend/slm-frontend/autobot_shared; fleet update: backend, backend's
autobot_shared, frontend, npu-worker, browser-worker, ai-stack, the
non-backend-node autobot_shared -- unarchive-based, not
`ansible.posix.synchronize`, per #16310 review).

#16310 review round 6, BLOCKING (reachability): update-all-nodes.yml is the
ONLY updater a GUI user can reach, and it applies roles/backend and
roles/frontend via targeted `include_role ... tasks_from` includes only
(the #12959 delivery contract) or raw `unarchive:` tasks written directly in
this playbook -- it never runs either role's main.yml. A deletion task or
AC4's npu_workers cleanup that existed ONLY in main.yml was ordered
correctly on paper and reachable from nothing a GUI Update All click
actually runs. So `roles/*/tasks/main.yml` entries below are asserted
ONLY as the provisioning-path wiring (site.yml, provision-fleet-roles.yml
Phase 4a/4b run each role's main.yml in full) -- every component
update-all-nodes.yml itself updates is asserted directly against that
playbook's own tasks, never against main.yml as a proxy for it.

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
_UPDATE_ALL_PLAYBOOK = "playbooks/update-all-nodes.yml"
_SYNC_DELETIONS_INCLUDE = "sync_deletions.yml"
_MARKER = ".autobot_sync_deletions_commit"

# (file relative to _ANSIBLE_ROOT, name-substring of the sync task the
# deletion task must follow). Provisioning-only entries (main.yml, never run
# by update-all-nodes.yml) are labeled; every update-all-nodes.yml entry
# below is a component that playbook itself syncs.
_SYNC_THEN_DELETE_SITES: tuple[tuple[str, str], ...] = (
    # Provisioning path only (site.yml / provision-fleet-roles.yml Phase 4a/4b
    # run the role's main.yml in full) -- see test_provisioning_playbooks_run_the_role
    # below for the reachability half of this claim.
    ("roles/backend/tasks/main.yml", "Sync autobot-backend code from code_source"),
    ("roles/frontend/tasks/main.yml", "Sync frontend code from code_source"),
    ("roles/slm_manager/tasks/main.yml", "Sync SLM backend code from code_source"),
    # roles/slm_agent/tasks/main.yml is import_role'd in FULL by BOTH
    # update-all-nodes.yml plays (see test_slm_agent_role_is_imported_in_full
    # below) -- unlike backend/frontend, this one IS reachable from the
    # update path through its own main.yml.
    ("roles/slm_agent/tasks/main.yml", "SLM Agent | Copy agent source - heartbeat_payload.py"),
    # update-all-nodes.yml PLAY 1 (SLM self-update).
    (_UPDATE_ALL_PLAYBOOK, "SLM | Deploy autobot-slm-frontend"),
    # update-all-nodes.yml PLAY 2 (fleet update) -- every component it syncs.
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Backend | Deploy autobot-backend"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Backend | Deploy autobot_shared"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Frontend | Deploy autobot-frontend"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] NPU | Deploy autobot-npu-worker"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Browser | Deploy autobot-browser-worker"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] AI Stack | Deploy ai_api_server and requirements"),
    (_UPDATE_ALL_PLAYBOOK, "[PLAY 2] Shared | Deploy autobot_shared"),
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


def _delete_step_raw_cmd() -> str:
    task = _shared_task()
    delete_step = next((sub for sub in task["block"] if "remove" in str(sub.get("name", "")).lower()), None)
    assert delete_step is not None, "no deletion step found in the block"
    return str(delete_step["ansible.builtin.shell"]["cmd"])


def _render_delete_cmd(target_dir, delete_list: list[str]) -> str:
    """Substitute the two Jinja expressions the real task uses, by hand --
    the same two an ansible run would fill in with sync_deletions_target_dir
    and _sd_plan.delete."""
    rendered = _delete_step_raw_cmd().replace("{{ sync_deletions_target_dir }}", str(target_dir))
    return rendered.replace("{{ _sd_plan.delete | join('\\n') }}", "\n".join(delete_list))


def test_the_delete_step_shell_resists_injection_and_path_escapes(tmp_path) -> None:
    """#16310 review round 4, MEDIUM: pull the REAL `cmd:` body out of the
    shared task file (the way this file already parses it for the tests
    above), render it with a crafted delete list, and run it against a real
    tree with hostile filenames -- proving the quoting holds, not just
    asserting it by reading the source."""
    import subprocess

    root = tmp_path / "target"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    injected_marker = outside / "INJECTED"

    ordinary_hostile = [
        "safe with spaces.txt",
        "quote'name.txt",
        "back`tick.txt",
        f"dollar$(touch {injected_marker}).txt",
        "semi;colon.txt",
        "pipe|char.txt",
        "-leading-dash.txt",
    ]
    for name in ordinary_hostile:
        (root / name).write_text("x", encoding="utf-8")

    escape_link = root / "escape_link"
    escape_link.symlink_to(outside)
    escaped_payload = outside / "payload.txt"
    escaped_payload.write_text("do not delete", encoding="utf-8")

    delete_list = [*ordinary_hostile, "../outside_target.txt", "escape_link/payload.txt"]
    script = _render_delete_cmd(root, delete_list)

    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False)

    assert not injected_marker.exists(), f"injection executed a command: {result.stderr}"
    assert result.returncode == 1, "the script must fail when it refused an escaping candidate"
    for name in ordinary_hostile:
        assert not (root / name).exists(), f"{name!r} should have been deleted"
    assert escaped_payload.exists(), "a path resolving outside the root must survive"
    assert "REFUSED" in result.stderr


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


# --------------------------------------------------------------------------
# AC4 regression: the nested npu_workers.yaml duplicate cleanup
#
# Dropped entirely by the cf2a08f1e ansible-native redesign (deletion moved
# from Python-applies to Ansible-applies, and this AC's cleanup had no new
# home). Re-delivered as roles/backend/tasks/npu_workers_cleanup.yml,
# checksum-gated so a host where the nested and canonical copies have since
# diverged is left alone and reported rather than silently losing data.
#
# #16310 review round 6: split out of main.yml into its own task file so it
# can ALSO be applied via `include_role: {name: backend, tasks_from:
# npu_workers_cleanup}` from update-all-nodes.yml PLAY 2 -- the update path
# never runs main.yml (see test_provisioning_playbooks_run_the_role_in_full
# and test_npu_workers_cleanup_is_delivered_on_the_update_path below).
# --------------------------------------------------------------------------

_BACKEND_MAIN = "roles/backend/tasks/main.yml"
_NPU_CLEANUP_FILE = "roles/backend/tasks/npu_workers_cleanup.yml"
_NPU_NESTED_PATH = "{{ backend_code_dir }}/autobot-backend/config/npu_workers.yaml"
_NPU_CANONICAL_PATH = "{{ backend_code_dir }}/config/npu_workers.yaml"


def _backend_tasks() -> list[dict]:
    return _flatten(_load_tasks(_BACKEND_MAIN))


def _npu_cleanup_tasks() -> list[dict]:
    return _flatten(_load_tasks(_NPU_CLEANUP_FILE))


def _npu_task(name_substring: str) -> dict:
    tasks = _npu_cleanup_tasks()
    idx = _index_of(tasks, lambda t: name_substring in str(t.get("name", "")))
    assert idx != -1, f"{_NPU_CLEANUP_FILE}: no task with {name_substring!r} in its name"
    return tasks[idx]


def _when_text(task: dict) -> str:
    when = task.get("when", "")
    return " ".join(when) if isinstance(when, list) else str(when)


def test_npu_workers_cleanup_is_included_right_after_the_deletion_task_in_main_yml() -> None:
    """Provisioning path: main.yml includes npu_workers_cleanup.yml right
    after the #16310 deletion task -- not a separate step an operator has to
    remember to run."""
    tasks = _backend_tasks()
    delete_index = _index_of(tasks, _includes_sync_deletions)
    assert delete_index != -1, f"{_BACKEND_MAIN}: sync_deletions include not found"

    def _includes_npu_cleanup(task: dict) -> bool:
        target = task.get("ansible.builtin.include_tasks") or task.get("include_tasks")
        return target == "npu_workers_cleanup.yml"

    remove_index = _index_of(tasks[delete_index:], _includes_npu_cleanup)
    assert remove_index != -1, f"{_BACKEND_MAIN}: no npu_workers_cleanup.yml include after sync_deletions"
    assert remove_index > 0


def test_npu_workers_cleanup_is_delivered_on_the_update_path() -> None:
    """#16310 review round 6, item 2: AC4 must be reachable from PLAY 2 via
    the #12959 `include_role ... tasks_from` contract, not only from
    main.yml (provisioning)."""
    plays = yaml.safe_load((_ANSIBLE_ROOT / _UPDATE_ALL_PLAYBOOK).read_text(encoding="utf-8"))
    tasks = _flatten(plays)

    def _is_npu_cleanup_include_role(task: dict) -> bool:
        include = task.get("ansible.builtin.include_role") or task.get("include_role")
        return (
            isinstance(include, dict)
            and include.get("name") == "backend"
            and include.get("tasks_from") == "npu_workers_cleanup"
        )

    backend_sync_index = _index_of(
        tasks, lambda t: "[PLAY 2] Backend | Deploy autobot-backend" in str(t.get("name", ""))
    )
    assert backend_sync_index != -1, f"{_UPDATE_ALL_PLAYBOOK}: PLAY 2 backend sync task not found"

    cleanup_index = _index_of(tasks[backend_sync_index:], _is_npu_cleanup_include_role)
    assert cleanup_index != -1, (
        f"{_UPDATE_ALL_PLAYBOOK}: no `include_role: {{name: backend, tasks_from: npu_workers_cleanup}}` "
        "after the PLAY 2 backend sync -- AC4 is inert on every host updated through the builtin updater"
    )
    assert cleanup_index > 0


def test_npu_workers_cleanup_stats_both_files_with_a_checksum_first() -> None:
    nested_stat = _npu_task("Stat nested legacy npu_workers.yaml duplicate")
    canonical_stat = _npu_task("Stat canonical npu_workers.yaml")
    checks = (
        (nested_stat, "_npu_legacy_nested_stat", _NPU_NESTED_PATH),
        (canonical_stat, "_npu_legacy_canonical_stat", _NPU_CANONICAL_PATH),
    )
    for task, register, path in checks:
        stat_args = task.get("ansible.builtin.stat", {})
        assert stat_args.get("checksum_algorithm") == "sha256", f"{task.get('name')}: must compute a checksum"
        assert stat_args.get("path") == path
        assert task.get("register") == register


def test_npu_workers_cleanup_removal_is_gated_on_matching_checksums() -> None:
    """Removed ONLY while byte-identical to the canonical file -- a
    diverged nested copy (e.g. an operator recovered live state from it)
    must survive, never be silently deleted or overwritten."""
    remove = _npu_task("Remove nested npu_workers.yaml duplicate")
    when_text = _when_text(remove)
    assert "_npu_legacy_nested_stat.stat.exists" in when_text
    assert "_npu_legacy_canonical_stat.stat.exists" in when_text
    assert "_npu_legacy_nested_stat.stat.checksum == _npu_legacy_canonical_stat.stat.checksum" in when_text

    file_args = remove.get("ansible.builtin.file", {})
    assert file_args.get("state") == "absent"
    assert file_args.get("path") == _NPU_NESTED_PATH


def test_npu_workers_cleanup_reports_instead_of_deleting_on_a_mismatch() -> None:
    """The mismatch branch must never call ansible.builtin.file: state=absent
    -- reporting and refusing is the whole point of the checksum gate."""
    refuse = _npu_task("REFUSING to remove nested npu_workers.yaml")
    assert "ansible.builtin.file" not in refuse, "the mismatch branch must not delete anything"
    assert "ansible.builtin.debug" in refuse

    when_text = _when_text(refuse)
    assert "_npu_legacy_nested_stat.stat.exists" in when_text
    assert "checksum" in when_text.lower()


# --------------------------------------------------------------------------
# #16310 review round 6, BLOCKING (reachability): main.yml wiring for
# backend/frontend is provisioning-only. Prove the provisioning half of that
# claim rather than asserting it in a comment -- a playbook that stops
# running a role in full would silently strand this wiring exactly like the
# update path already did.
# --------------------------------------------------------------------------


def _play_applies_role_in_full(playbook_path, role_name: str) -> bool:
    plays = yaml.safe_load(playbook_path.read_text(encoding="utf-8"))
    for play in plays if isinstance(plays, list) else []:
        if not isinstance(play, dict):
            continue
        for entry in play.get("roles") or []:
            name = entry.get("role") or entry.get("name") if isinstance(entry, dict) else entry
            if name == role_name:
                return True
        for task in _flatten(play.get("tasks") or []):
            include = task.get("ansible.builtin.include_role") or task.get("include_role")
            if isinstance(include, dict) and include.get("name") == role_name and "tasks_from" not in include:
                return True
    return False


@pytest.mark.parametrize(
    "playbook,role_name",
    [
        ("provision-fleet-roles.yml", "backend"),
        ("provision-fleet-roles.yml", "frontend"),
        ("site.yml", "backend"),
        # deploy-slm-manager.yml (SLM manager provisioning) applies
        # roles/slm_manager in full via a bare `roles:` list entry
        # (`- role: slm_manager`, no tasks_from) -- the provisioning path for
        # roles/slm_manager/tasks/main.yml's own #16310 wiring. Nothing else
        # in CI would catch a future switch to `tasks_from`.
        ("deploy-slm-manager.yml", "slm_manager"),
        # site.yml's frontend play references a role named "frontend_app",
        # which does not exist under roles/ -- a pre-existing, unrelated
        # defect (not introduced by #16310) filed separately rather than
        # fixed here. provision-fleet-roles.yml's Phase 4b (checked above)
        # is frontend's real, working provisioning path.
    ],
)
def test_provisioning_playbooks_run_the_role_in_full(playbook, role_name) -> None:
    path = _ANSIBLE_ROOT / "playbooks" / playbook
    assert path.is_file(), f"{path} not found"
    assert _play_applies_role_in_full(path, role_name), (
        f"{playbook}: no play applies roles/{role_name} in full (no `tasks_from`) -- "
        f"the main.yml #16310 wiring for {role_name} would be provisioning-unreachable too"
    )


@pytest.mark.xfail(
    strict=True,
    reason="#16342: site.yml's frontend play references nonexistent role frontend_app",
)
def test_site_yml_frontend_play_applies_only_existing_roles() -> None:
    """The CORRECT end state (#16342), not "the bug exists" -- an assertion
    that the bug exists would redden this unrelated PR the moment #16342 is
    fixed. `xfail(strict=True)` instead: today this fails as expected
    (`frontend_app` does not exist), and once #16342 lands the assertion
    starts passing, which strict xfail reports as a FAILURE ("unexpected
    pass"), forcing the marker's removal -- the same pattern
    tests/test_update_all_applies_roles_12959.py's own docstring describes
    using for exactly this reason (a baseline would have quietly absorbed
    the fix and kept claiming the problem was still there, the #12894
    lesson)."""
    site_yml = yaml.safe_load((_ANSIBLE_ROOT / "site.yml").read_text(encoding="utf-8"))
    frontend_play = next((p for p in site_yml if isinstance(p, dict) and p.get("hosts") == "frontend"), None)
    assert frontend_play is not None, "site.yml: no play with hosts: frontend"
    role_names = [e.get("role") or e.get("name") if isinstance(e, dict) else e for e in frontend_play.get("roles", [])]
    missing = [name for name in role_names if not (_ANSIBLE_ROOT / "roles" / name).is_dir()]
    assert missing == [], f"site.yml Frontend play references nonexistent role(s): {missing}"


def test_slm_agent_role_is_imported_in_full_by_update_all_nodes() -> None:
    """#16310 review round 6: roles/slm_agent/tasks/main.yml's own
    sync_deletions wiring is reachable from update-all-nodes.yml ONLY if
    that playbook actually imports the role in full (no tasks_from)."""
    plays = yaml.safe_load((_ANSIBLE_ROOT / _UPDATE_ALL_PLAYBOOK).read_text(encoding="utf-8"))
    found = False
    for task in _flatten(plays):
        include = (
            task.get("ansible.builtin.import_role")
            or task.get("import_role")
            or task.get("ansible.builtin.include_role")
            or task.get("include_role")
        )
        if isinstance(include, dict) and include.get("name") == "slm_agent" and "tasks_from" not in include:
            found = True
            break
    assert found, f"{_UPDATE_ALL_PLAYBOOK}: no full (no tasks_from) import of the slm_agent role found"
