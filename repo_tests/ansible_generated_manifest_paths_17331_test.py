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

import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

_ANSIBLE = repo_root() / "autobot-slm-backend" / "ansible"
_SCRIPT_NAME = "build-filtered-requirements.sh"
_STAGING_TASKS = _ANSIBLE / "roles" / "_shared" / "tasks" / "stage_shared_manifests.yml"

# Modules whose payload is a command line the script can be invoked from.
_EXEC_MODULES = {
    "shell",
    "ansible.builtin.shell",
    "command",
    "ansible.builtin.command",
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
            found.append(
                (
                    path.relative_to(_ANSIBLE).as_posix(),
                    str(task.get("name", "<unnamed>"))[:70],
                    _invocation_args(text),
                    _delegates_to_controller(task),
                )
            )
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
        "rewrite its includes to a path the NODE has (#17331, #17242):\n  " + "\n  ".join(offenders)
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

    missing = [include for include in _REWRITTEN_INCLUDES if not re.search(r"dest:.*" + re.escape(include), staged)]

    assert not missing, (
        "build-filtered-requirements.sh rewrites these includes, so each must "
        f"be staged onto the node by {_STAGING_TASKS.name} (#17331, #11135): " + ", ".join(missing)
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
        "when a playbook other than the updater runs them (#17331):\n  " + "\n  ".join(offenders)
    )


# ---------------------------------------------------------------------------
# Checked-in manifests installed in place (#17892)
# ---------------------------------------------------------------------------
#
# The generated case above is half the family. The other half is a pip task that
# installs a CHECKED-IN manifest straight from the deployed tree: pip resolves its
# sibling-relative `-c ../constraints/shared.txt` against the deployed file, so the
# include lands at `<base_dir>/constraints/shared.txt` -- a path only
# stage_shared_manifests.yml puts on a node. slm_manager installed
# `{{ slm_backend_dir }}/requirements.txt` without staging, and a clean-machine
# install aborted with "Could not open constraint file" (#17892). Two earlier
# instances are recorded in scripts/build-filtered-requirements.sh's header.
#
# Derived, not enumerated: every pip site with `requirements:` is found by walking
# the roles; its manifest is resolved through the role's defaults; every relative
# include in it is resolved where pip will open it. A site whose path cannot be
# resolved statically must be named in _UNRESOLVED_SITES with its reason.
#
# What the path-filter meta-guard cannot see here: the manifests are read as
# `repo_root() / <resolved path>`, a VARIABLE composition, which
# python_filter_covers_its_guards_test's detectors do not register (#17632). Its
# green therefore says nothing about whether a manifest-only change runs this
# guard; that rests on the filter covering the manifests' trees directly.

_ROLES = _ANSIBLE / "roles"
_PIP_MODULES = {"pip", "ansible.builtin.pip"}
_INCLUDE_MODULES = {"include_tasks", "ansible.builtin.include_tasks", "import_tasks", "ansible.builtin.import_tasks"}
_BASE_DIR = yaml.safe_load((_ANSIBLE / "inventory" / "group_vars" / "all.yml").read_text(encoding="utf-8"))["autobot"][
    "base_dir"
]
#: What stage_shared_manifests.yml places on a node, relative to base_dir.
_STAGED_PATHS = {f"{_BASE_DIR}/{rel}" for rel in _REWRITTEN_INCLUDES}
_RELATIVE_INCLUDE = re.compile(r"^-[cr]\s+(\.\./\S+)", re.M)
_VAR = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
#: Floor on the WORK, not the survey: manifests actually resolved, read and
#: scanned for includes. Counting pip sites instead left the scan running on zero
#: real manifests once every live site was staged (#17895 review). Measured: 3
#: (root requirements.txt via agent_config, browser worker, SLM backend).
_MIN_MANIFESTS_SCANNED = 3
_GENERATED_MANIFEST = re.compile(r"(^|/)filtered-requirements[^/]*\.txt$")

#: (role task file, requirements value) -> why the static resolution does not apply.
#: EQUALITY-pinned by _UNRESOLVED_SITE_COUNT: adding an exemption is a recorded
#: decision, never a quiet way past this check.
_UNRESOLVED_SITES = {
    (
        "npu-worker/tasks/main.yml",
        "{{ code_source_dir | default(autobot.base_dir ~ '/code_source') }}/autobot-npu-worker/requirements.txt",
    ): "installs from the code_source checkout, where its `-c ../constraints` resolves inside that same "
    "checkout; whether code_source exists on the node is the #17243 family, not this one",
    (
        "dependency_patching/tasks/update-venv.yml",
        "/tmp/requirements-security-update.txt",
    ): "rendered from templates/requirements-security-update.txt.j2, which declares no -c/-r includes "
    "(asserted by test_the_patching_template_declares_no_includes)",
    (
        "backend_services/tasks/main.yml",
        "/opt/autobot/app/requirements.txt",
    ): "/opt/autobot/app is a synchronize of autobot-slm-backend/, not a repo-mirrored path; its includes resolve "
    "to the staged files (the role stages first). Install-before-copy ordering is #17896",
}
_UNRESOLVED_SITE_COUNT = 3


def _pip_sites(roles_dir: Path = _ROLES) -> list[tuple[str, str, bool]]:
    """(role-relative task file, requirements value, staged-before) for every pip site with a manifest."""
    sites = []
    for path in sorted(roles_dir.glob("*/tasks/*.yml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        staged = False
        for task in _flat_tasks(doc):
            if any("stage_shared_manifests" in str(task.get(m, "")) for m in _INCLUDE_MODULES):
                staged = True
            module = next((m for m in _PIP_MODULES if m in task), None)
            requirements = task[module].get("requirements") if module and isinstance(task[module], dict) else None
            if requirements:
                sites.append((path.relative_to(roles_dir).as_posix(), str(requirements).strip(), staged))
    return sites


def _flat_tasks(node) -> list[dict]:
    """Tasks in file order, descending into block/rescue/always."""
    out: list[dict] = []
    for task in node if isinstance(node, list) else []:
        if isinstance(task, dict):
            out.append(task)
            for key in ("block", "rescue", "always"):
                out.extend(_flat_tasks(task.get(key)))
    return out


def resolve_path(value: str, variables: dict[str, str]) -> str | None:
    """Substitute simple ``{{ var }}`` references until none remain; None if any cannot be."""
    for _ in range(10):
        unresolved = _VAR.findall(value)
        if not unresolved:
            return None if "{{" in value else value
        for name in unresolved:
            if name not in variables:
                return None
            value = re.sub(r"\{\{\s*" + name + r"\s*\}\}", variables[name], value)
    return None


def unplaced_includes(manifest_on_node: str, manifest_text: str, placed: set[str]) -> list[str]:
    """Node paths of relative includes that resolve outside the deployed tree and are not placed."""
    missing = []
    for include in _RELATIVE_INCLUDE.findall(manifest_text):
        target = (Path(manifest_on_node).parent / include).resolve().as_posix()
        repo_rel = target.removeprefix(f"{_BASE_DIR}/")
        ships_with_tree = (repo_root() / repo_rel).is_file() and repo_rel not in _REWRITTEN_INCLUDES
        if target not in placed and not ships_with_tree:
            missing.append(target)
    return missing


def _role_vars(role_file: str, roles_dir: Path = _ROLES) -> dict[str, str]:
    defaults = roles_dir / role_file.split("/", 1)[0] / "defaults" / "main.yml"
    data = yaml.safe_load(defaults.read_text(encoding="utf-8")) if defaults.is_file() else {}
    return {k: str(v) for k, v in (data or {}).items() if isinstance(v, (str, int))}


def check_sites(sites: list[tuple[str, str, bool]], roles_dir: Path = _ROLES) -> tuple[list[str], int]:
    """(failures, manifests scanned). Every resolvable site is scanned, staged or not.

    A staged site's includes may land on the staged paths; an unstaged site's may
    not. A path that resolves but mirrors no repo manifest FAILS unless it is a
    generated filtered manifest (owned by the checks above) or a named exemption:
    a silent skip there is how a diverged base-dir default would go unnoticed.
    """
    failures, scanned = [], 0
    for role_file, requirements, staged in sites:
        if (role_file, requirements) in _UNRESOLVED_SITES:
            continue
        on_node = resolve_path(requirements, _role_vars(role_file, roles_dir))
        if on_node is None:
            failures.append(f"{role_file}: cannot resolve {requirements!r} -- name it in _UNRESOLVED_SITES")
            continue
        if _GENERATED_MANIFEST.search(on_node):
            continue
        manifest = repo_root() / on_node.removeprefix(f"{_BASE_DIR}/")
        if not manifest.is_file():
            failures.append(f"{role_file}: {requirements} resolves to {on_node}, which mirrors no repo manifest")
            continue
        scanned += 1
        placed = _STAGED_PATHS if staged else set()
        for target in unplaced_includes(on_node, manifest.read_text(encoding="utf-8"), placed):
            failures.append(f"{role_file}: {requirements} includes {target}, which nothing places before pip runs")
    return failures, scanned


def test_every_installed_manifest_include_resolves_to_a_placed_path():
    """A relative -c/-r in an installed manifest must land on something the role put there."""
    failures, scanned = check_sites(_pip_sites())
    assert (
        scanned >= _MIN_MANIFESTS_SCANNED
    ), f"scanned {scanned} manifests for includes (floor {_MIN_MANIFESTS_SCANNED}) -- the work did not happen"
    assert not failures, "\n".join(failures)


def test_the_walk_catches_the_slm_manager_defect_it_was_written_for(tmp_path):
    """The live role with its staging include removed must fail -- proven on the walk, not a string."""
    role = tmp_path / "slm_manager"
    (role / "tasks").mkdir(parents=True)
    (role / "defaults").mkdir()
    (role / "defaults" / "main.yml").write_text(
        (_ROLES / "slm_manager" / "defaults" / "main.yml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    tasks = yaml.safe_load((_ROLES / "slm_manager" / "tasks" / "main.yml").read_text(encoding="utf-8"))
    unstaged = [t for t in tasks if "stage_shared_manifests" not in str(t)]
    assert len(unstaged) == len(tasks) - 1, "the staging include was not found to remove"
    (role / "tasks" / "main.yml").write_text(yaml.safe_dump(unstaged), encoding="utf-8")

    failures, scanned = check_sites(_pip_sites(tmp_path), roles_dir=tmp_path)

    assert scanned == 1
    assert failures == [
        "slm_manager/tasks/main.yml: {{ slm_backend_dir }}/requirements.txt includes "
        f"{_BASE_DIR}/constraints/shared.txt, which nothing places before pip runs"
    ]


def test_no_unresolved_site_exemption_is_stale():
    live = {(role_file, requirements) for role_file, requirements, _ in _pip_sites()}
    stale = sorted(set(_UNRESOLVED_SITES) - live)
    assert not stale, f"exemptions for sites that no longer exist: {stale}"


def test_the_exemption_list_only_changes_on_purpose():
    """Equality, like the uncovered-reads record: headroom would admit a new exemption silently."""
    assert len(_UNRESOLVED_SITES) == _UNRESOLVED_SITE_COUNT


def test_the_patching_template_declares_no_includes():
    template = _ROLES / "dependency_patching" / "templates" / "requirements-security-update.txt.j2"
    assert not _RELATIVE_INCLUDE.search(template.read_text(encoding="utf-8"))


def test_an_unstaged_relative_constraint_is_reported():
    """Contrast pair for the detector: a constraint include with nothing placed is named; once placed, it is not."""
    on_node = f"{_BASE_DIR}/autobot-slm-backend/requirements.txt"
    text = "fastapi>=1\n-c ../constraints/shared.txt\n"
    assert unplaced_includes(on_node, text, placed=set()) == [f"{_BASE_DIR}/constraints/shared.txt"]
    assert unplaced_includes(on_node, text, placed=_STAGED_PATHS) == []


def test_a_diverged_base_dir_fails_instead_of_passing_silently(tmp_path):
    """A role whose base-dir default stops matching autobot.base_dir must not be skipped (#17895 review)."""
    role = tmp_path / "slm_manager"
    (role / "tasks").mkdir(parents=True)
    (role / "defaults").mkdir()
    defaults = yaml.safe_load((_ROLES / "slm_manager" / "defaults" / "main.yml").read_text(encoding="utf-8"))
    defaults["slm_base_dir"] = "/srv/elsewhere"
    (role / "defaults" / "main.yml").write_text(yaml.safe_dump(defaults), encoding="utf-8")
    (role / "tasks" / "main.yml").write_text(
        (_ROLES / "slm_manager" / "tasks" / "main.yml").read_text(encoding="utf-8"), encoding="utf-8"
    )

    failures, scanned = check_sites(_pip_sites(tmp_path), roles_dir=tmp_path)

    assert scanned == 0
    assert failures and "mirrors no repo manifest" in failures[0], failures
