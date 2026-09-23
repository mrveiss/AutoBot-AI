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

from repo_tests._paths import repo_root

# #15925: the repository root is derived in one place. Re-deriving it from
# __file__ binds this guard to its own depth in the tree.
_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"

# Modules whose payload runs on the TARGET unless the task is delegated.
_EXEC_MODULES = {
    "shell", "ansible.builtin.shell",
    "command", "ansible.builtin.command",
    "script", "ansible.builtin.script",
    "raw", "ansible.builtin.raw",
}

# Modules that READ A FILE on the target. Delegation is not an exemption here:
# delegating `pip` moves the install to the controller, which is a worse bug
# than the one being fixed. The only correct fix is to stage the file, so these
# are exempt by controller-only play scope and by nothing else.
#
# The first sweep for #17243 scanned only _EXEC_MODULES and therefore missed
# three `pip:` tasks reading root-level manifests out of code_source. Being
# blind to a module class is how that shape survives a guard.
_TARGET_FILE_MODULES = {"pip", "ansible.builtin.pip"}

_SCANNED_MODULES = _EXEC_MODULES | _TARGET_FILE_MODULES

# Play scopes where the controller's checkout is genuinely present.
_CONTROLLER_SCOPES = {"localhost", "127.0.0.1", "slm_server", "slm"}

# Only these delegate_to destinations actually move execution to the controller.
# `delegate_to` alone is not enough: `delegate_to: "{{ inventory_hostname }}"`
# is truthy and still runs on the fleet host, so accepting any value would let
# the exact defect this guard exists for slip through wearing an exemption.
_CONTROLLER_DELEGATES = {"localhost", "127.0.0.1"}

# A floor, not a census: if the walk stops finding `code_source` tasks at all,
# this guard would pass by matching nothing. See MEASUREMENT_DISCIPLINE.md.
_MIN_TASKS_SEEN = 8

# Pre-existing offenders, recorded so this guard blocks NEW instances today
# instead of waiting until every old one is fixed.
#
# This list may only SHRINK. `test_the_baseline_has_no_stale_entries` fails when
# an entry stops being an offender, so a fix cannot silently leave its record
# behind, and nothing can be added here to make a new violation pass.
#
# #17246 fixed six of the original seven: each now reads
# `{{ autobot.base_dir }}/constraints/shared.txt`, staged onto the node by
# `roles/_shared/tasks/stage_shared_manifests.yml`.
#
# The seventh is NOT a pip-path problem and is deliberately not forced into the
# same shape. `roles/npu-worker` reads its whole MANIFEST out of the checkout,
# and that manifest opens with `-e ../autobot_shared` (#15733) -- an editable
# install of a sibling package tree. The other sites could be repointed because
# only their `-c` named the checkout; here the editable does too, and the
# obvious move (route it through build-filtered-requirements.sh, which strips
# that line) would silently drop autobot_shared from the NPU venv. Nothing else
# installs it there: `roles/autobot_shared` syncs to a PYTHONPATH directory and
# only runs under `deploy_role == 'autobot_shared'`. Dropping it would be the
# #11135 class of regression -- the exact failure this guard's own history is
# made of -- so it waits on a decision about where autobot_shared lives on a
# worker node, tracked by #17334.
_KNOWN_UNSTAGED = frozenset({
    "roles/npu-worker/tasks/main.yml :: NPU Worker | Install worker dependencies from its manifest",
})


def _tasks(node):
    """Yield every mapping that looks like a task, depth-first."""
    if isinstance(node, list):
        for item in node:
            yield from _tasks(item)
    elif isinstance(node, dict):
        if any(k in _SCANNED_MODULES for k in node):
            yield node
        for value in node.values():
            yield from _tasks(value)


def _payload_text(task) -> str:
    module = next(k for k in task if k in _SCANNED_MODULES)
    payload = task[module]
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return " ".join(f"{k}={v}" for k, v in payload.items())
    return str(payload)


def _delegates_to_controller(task) -> bool:
    """True only when delegate_to names the controller itself."""
    target = task.get("delegate_to")
    return isinstance(target, str) and target.strip() in _CONTROLLER_DELEGATES


def _scope_is_controller_only(scope: str) -> bool:
    """True when EVERY host token in the play scope is a controller scope.

    Exact per-token matching, not substring: `backend,localhost` contains a
    controller name but still targets fleet hosts, and `slm_nodes` merely starts
    with one. Either would be exempted by a naive `in` test.
    """
    tokens = [tok.strip() for tok in scope.replace(":", ",").split(",") if tok.strip()]
    return bool(tokens) and all(tok in _CONTROLLER_SCOPES for tok in tokens)


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


def _offenders(root: pathlib.Path | None = None) -> tuple[list[str], int]:
    """Offending tasks and the number of code_source tasks seen, under *root*."""
    root = _ANSIBLE if root is None else root
    offenders: list[str] = []
    seen = 0
    for path in sorted(root.rglob("*.yml")):
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
            module = next(k for k in task if k in _SCANNED_MODULES)
            if module not in _TARGET_FILE_MODULES and _delegates_to_controller(task):
                continue
            scope = _play_scope(doc, task)
            if scope is not None and _scope_is_controller_only(scope):
                continue
            offenders.append(
                f"{path.relative_to(root).as_posix()} :: "
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


def test_the_baseline_has_no_stale_entries():
    """A fixed site must be removed from the baseline, so the list only shrinks."""
    offenders, _ = _offenders()
    stale = sorted(_KNOWN_UNSTAGED - set(offenders))

    assert not stale, (
        "these baseline entries are no longer offenders -- delete them so the "
        "record cannot drift back upward (#17246):\n  " + "\n  ".join(stale)
    )


def test_no_target_side_task_reads_code_source_undelegated():
    """#17242/#17243: reading the controller's checkout on a node is rc=127."""
    offenders = [o for o in _offenders()[0] if o not in _KNOWN_UNSTAGED]

    assert not offenders, (
        "these tasks execute on the target and read code_source, which exists only on "
        "the controller -- add `delegate_to: localhost` (see "
        "_shared/tasks/sync_deletions.yml) or stage the file onto the node:\n  "
        + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Contrast pair. Scanning the repository only confirms the tree as it stands
# today: it cannot distinguish "the detector works" from "the detector matches
# nothing". These fixtures prove both directions on inputs whose answer is
# known by construction.
# ---------------------------------------------------------------------------

_OFFENDING = """
- name: Fleet play
  hosts: infrastructure
  tasks:
    - name: Run a script out of code_source on the target
      ansible.builtin.command:
        cmd: bash {{ code_source_dir }}/scripts/build-filtered-requirements.sh
"""

_DELEGATED = """
- name: Fleet play
  hosts: infrastructure
  tasks:
    - name: Run the same script on the controller
      ansible.builtin.command:
        cmd: bash {{ code_source_dir }}/scripts/build-filtered-requirements.sh
      delegate_to: localhost
"""

_CONTROLLER_PLAY = """
- name: Controller-only play
  hosts: localhost
  tasks:
    - name: Reading code_source here is fine
      ansible.builtin.command:
        cmd: git -C {{ code_source_dir }} rev-parse HEAD
"""

_FAKE_DELEGATE = """
- name: Fleet play
  hosts: infrastructure
  tasks:
    - name: delegate_to that does not reach the controller
      ansible.builtin.command:
        cmd: bash {{ code_source_dir }}/scripts/build-filtered-requirements.sh
      delegate_to: "{{ inventory_hostname }}"
"""

_MIXED_SCOPE = """
- name: Play that includes a controller name but also fleet hosts
  hosts: backend,localhost
  tasks:
    - name: Still runs on backend hosts
      ansible.builtin.command:
        cmd: bash {{ code_source_dir }}/scripts/build-filtered-requirements.sh
"""


def _scan_fixture(tmp_path, body: str):
    (tmp_path / "play.yml").write_text(body, encoding="utf-8")
    return _offenders(tmp_path)


def test_detector_flags_an_undelegated_target_side_task(tmp_path):
    """The positive half: the shape #17242 shipped must be reported."""
    offenders, seen = _scan_fixture(tmp_path, _OFFENDING)

    assert seen == 1
    assert len(offenders) == 1, f"detector missed the offending task: {offenders}"


def test_detector_allows_the_same_task_when_delegated(tmp_path):
    """The negative half: the fix must not still be reported."""
    offenders, seen = _scan_fixture(tmp_path, _DELEGATED)

    assert seen == 1, "fixture no longer reaches the detector"
    assert offenders == [], f"delegated task was wrongly flagged: {offenders}"


def test_detector_allows_a_controller_scoped_play(tmp_path):
    """A play pinned to the controller genuinely has the checkout."""
    offenders, seen = _scan_fixture(tmp_path, _CONTROLLER_PLAY)

    assert seen == 1
    assert offenders == []


def test_delegate_to_must_name_the_controller(tmp_path):
    """A truthy delegate_to that still lands on a fleet host is not an exemption."""
    offenders, seen = _scan_fixture(tmp_path, _FAKE_DELEGATE)

    assert seen == 1
    assert len(offenders) == 1, "delegate_to was accepted without checking its destination"


def test_a_compound_scope_is_not_controller_only(tmp_path):
    """`backend,localhost` contains a controller name but targets fleet hosts."""
    offenders, seen = _scan_fixture(tmp_path, _MIXED_SCOPE)

    assert seen == 1
    assert len(offenders) == 1, "substring scope matching exempted a fleet play"
