# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A generated manifest's paths must resolve where pip reads it, not where it was written.

#17242 moved the generation of the filtered backend manifest onto the
controller, because `code_source` is the controller's git checkout and no task
syncs it to a node. It did not move the path that generation writes INTO the
file. `scripts/build-filtered-requirements.sh` rewrote the sibling-relative
`-c ../constraints/...` include to `${code_source_dir}/constraints/...`, that
line was copied to the target with the rest of the file, and pip -- which
resolves a nested `-c` against the directory of the file containing it, not
against the CWD -- opened it on the target and aborted:

    ERROR: Could not open constraint file: [Errno 2] No such file or directory:
           '<base_dir>/code_source/constraints/shared.txt'

So provisioning still failed on every non-manager host after #17242, one task
later. That is #17331.

Why this guard is separate from
`repo_tests/ansible_code_source_delegation_17243_test.py`: that one reads a
task's PAYLOAD and asks whether it names `code_source`. Here the payload is
clean -- `requirements: {{ backend_code_dir }}/filtered-requirements.txt` --
and the controller-only path lives inside the file's CONTENTS, produced at run
time by a shell script. A guard that reads task payloads cannot see a path that
a generator writes, which is why the first fix passed review.

What is checked: every invocation of the filter script that is generated on the
controller for a fleet target passes an explicit rewrite root, that root is not
inside `code_source`, and the files it names are actually staged onto the node.

CI does not execute Ansible, so none of this is observable before a fleet node
hits it.

Mutation check: drop the `{{ autobot.base_dir }}` argument from the generate
task in `roles/backend/tasks/main.yml` and `test_every_delegated_generation_names_a_target_side_root`
goes red naming that file; delete the `constraints/shared.txt` copy from
`roles/_shared/tasks/stage_shared_manifests.yml` and
`test_the_rewrite_root_is_staged_onto_the_node` goes red.
"""

from __future__ import annotations

import pathlib
import re

import yaml

from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_SCRIPT_NAME = "build-filtered-requirements.sh"
_STAGING_TASKS = _ANSIBLE / "roles" / "_shared" / "tasks" / "stage_shared_manifests.yml"

# Modules whose payload is a command line the script can be invoked from.
_EXEC_MODULES = {
    "shell", "ansible.builtin.shell",
    "command", "ansible.builtin.command",
}

# A floor, not a census. If the walk stops finding invocations at all, every
# assertion below would pass by matching nothing. See MEASUREMENT_DISCIPLINE.md.
_MIN_INVOCATIONS_SEEN = 2

# The includes the filter script rewrites, and therefore the files that must
# exist under the rewrite root on the machine that runs pip. Derived from the
# script's two `sed` expressions, not restated from memory: see
# `scripts/build-filtered-requirements.sh`.
_REWRITTEN_INCLUDES = ("constraints/shared.txt", "requirements.txt")


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


def _command_text(task) -> str:
    module = next(k for k in task if k in _EXEC_MODULES)
    payload = task[module]
    if isinstance(payload, str):
        return payload
    if isinstance(payload, dict):
        return " ".join(str(v) for v in payload.values())
    return str(payload)


# `{{ code_source_dir | default(...) }}` is ONE argument to the shell, and it
# contains spaces. Splitting the command line on whitespace alone turns a single
# path into eight tokens and makes every positional check below look at the
# wrong thing -- silently, since the result is still a list of plausible
# strings. Whitespace inside a Jinja expression is collapsed first.
_JINJA_EXPR = re.compile(r"\{\{.*?\}\}", re.S)


def _invocation_args(text: str) -> list[str]:
    """Arguments after the script name, up to the redirect that captures it.

    The invocations are folded YAML scalars, so newlines are already spaces by
    the time this sees them.
    """
    after = text.split(_SCRIPT_NAME, 1)[1]
    after = after.split(">", 1)[0]
    after = _JINJA_EXPR.sub(lambda m: re.sub(r"\s+", "", m.group(0)), after)
    return [tok for tok in after.split() if tok]


def _delegates_to_controller(task) -> bool:
    target = task.get("delegate_to")
    return isinstance(target, str) and target.strip() in {"localhost", "127.0.0.1"}


def _invocations() -> list[tuple[str, str, list[str], bool]]:
    """(file, task name, args, delegated) for every filter-script invocation."""
    found: list[tuple[str, str, list[str], bool]] = []
    for path in sorted(_ANSIBLE.rglob("*.yml")):
        if "/tests/" in path.as_posix():
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            continue
        for task in _tasks(doc):
            text = _command_text(task)
            if _SCRIPT_NAME not in text:
                continue
            found.append((
                path.relative_to(_ANSIBLE).as_posix(),
                str(task.get("name", "<unnamed>"))[:70],
                _invocation_args(text),
                _delegates_to_controller(task),
            ))
    return found


def test_the_scan_reaches_the_invocations_it_guards():
    """A walk that matches nothing would make every assertion below vacuous."""
    found = _invocations()

    assert len(found) >= _MIN_INVOCATIONS_SEEN, (
        f"only {len(found)} invocation(s) of {_SCRIPT_NAME} were found in "
        f"{_ANSIBLE.name}/, expected at least {_MIN_INVOCATIONS_SEEN} -- this "
        "guard has stopped reaching the tasks it checks"
    )


def test_every_delegated_generation_names_a_target_side_root():
    """#17331: generated HERE, installed THERE -- so say where THERE is.

    A task delegated to the controller writes a file that is copied to a node.
    Leaving the rewrite root implicit makes it the SOURCE root, which is the
    controller's checkout, and the node has no such directory.
    """
    offenders: list[str] = []
    for rel, name, args, delegated in _invocations():
        if not delegated:
            continue
        # args excludes the script name itself, so the script's three
        # positionals are 0=<requirements_file> 1=<code_source_dir>
        # 2=[rewrite_root].
        if len(args) < 3:
            offenders.append(
                f"{rel} :: {name} -- no rewrite root argument; the generated "
                "file would name the controller's own checkout"
            )
            continue
        rewrite_root = args[2]
        if "code_source" in rewrite_root:
            offenders.append(
                f"{rel} :: {name} -- rewrite root {rewrite_root!r} is inside "
                "code_source, which exists only on the controller"
            )

    assert not offenders, (
        "a manifest generated on the controller and installed on a node must "
        "rewrite its includes to a path the NODE has (#17331, #17242):\n  "
        + "\n  ".join(offenders)
    )


def test_the_rewrite_root_is_staged_onto_the_node():
    """The rewritten path is only honest if something puts the files there.

    Checked against the shared staging task rather than against a hardcoded
    path, so moving the staging destination moves this assertion with it.
    """
    assert _STAGING_TASKS.is_file(), (
        f"{_STAGING_TASKS.relative_to(repo_root())} is missing -- the rewritten "
        "includes name a node-local path that nothing stages (#17331)"
    )
    staged = _STAGING_TASKS.read_text(encoding="utf-8")

    missing = [
        include for include in _REWRITTEN_INCLUDES
        if not re.search(r"dest:.*" + re.escape(include), staged)
    ]

    assert not missing, (
        "build-filtered-requirements.sh rewrites these includes, so each must "
        f"be staged onto the node by {_STAGING_TASKS.name} (#17331, #11135): "
        + ", ".join(missing)
    )


def test_every_role_that_generates_a_manifest_stages_its_includes():
    """A role carries its own precondition, whatever playbook invoked it."""
    offenders: list[str] = []
    for rel, name, _args, delegated in _invocations():
        if not delegated or not rel.startswith("roles/"):
            continue
        role_file = _ANSIBLE / rel
        if _STAGING_TASKS.name not in role_file.read_text(encoding="utf-8"):
            offenders.append(f"{rel} :: {name}")

    assert not offenders, (
        f"these generate a manifest whose includes are rewritten to a staged "
        f"path but never include {_STAGING_TASKS.name}, so the path is empty "
        "when a playbook other than the updater runs them (#17331):\n  "
        + "\n  ".join(offenders)
    )
