#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: Ansible plays reference files and host groups that exist (#13744, #13745).

``deploy-native-services.yml`` installed the NPU worker from
``/opt/autobot/src/docker/npu-worker/requirements.txt`` — a path that has never
existed in this repository. Nothing caught it, because a wrong path in a play is
only discovered by running the play on a host, and the failure surfaces as a
deploy error rather than as a broken reference.

Scope is deliberately narrow: paths under the deployed source root
(``/opt/autobot/src/...``) map one-to-one onto repo paths, so they can be checked
without an inventory or a host. Anything else — templated values, host paths,
role-relative lookups — is skipped rather than guessed at, because a guard that
reports false positives gets switched off.

A second failure mode shares the shape (#13745): a play whose ``hosts:`` pattern
matches no group is **skipped silently** — the run reports ``ok=0 changed=0`` for
that play and exits 0, which reads as success. A group defined by no inventory at
all can only ever do nothing, so it is checked here too.

Deliberately "at least one inventory", not "every inventory": five are shipped
and they describe different topologies, so a play that legitimately has no target
in one of them is not a defect. ``ansible.cfg`` configures no default inventory —
every invocation passes ``-i`` explicitly — so there is no single one to check
against.

Run from the repo root:  python3 scripts/check_ansible_file_references.py
"""

import pathlib
import re
import sys

import yaml

# scripts/ is not a Python package; put the repository root on the path so
# the shared vacuity floor is importable when this runs as a bare script.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from tools.lint._scan_helpers import enforce_reach  # noqa: E402

# The deploy syncs the repo to this prefix, so what follows it is a repo path.
_DEPLOYED_SRC_PREFIX = "/opt/autobot/src/"

# Keys whose value is a path to a file the repo is expected to provide.
_FILE_KEYS = ("requirements", "src", "chdir", "creates")

_EXCLUDE_DIRS = (".worktrees", ".git", "node_modules", "__pycache__")

# The value is one unbroken token, except that a ``{{ name }}`` reference may
# contain spaces inside its braces. A plain ``\S+`` stops at the first space and
# so cannot match a templated value at all -- which would have made #15687's
# whole point unreachable.
_ASSIGNMENT = re.compile(
    r"^\s*(?P<key>" + "|".join(_FILE_KEYS) + r")\s*:\s*(?P<value>(?:\{\{[^{}]*\}\}|\S)+)\s*$",
)

_HOSTS = re.compile(r"^\s*hosts:\s*(?P<pattern>\S+)\s*$")

# Patterns Ansible resolves without an inventory group of that name.
_IMPLICIT_GROUPS = frozenset({"all", "localhost", "*", "127.0.0.1"})

# Patterns supplied by the caller at run time rather than by a shipped
# inventory. Each entry needs a tracking issue: a bare name here is
# indistinguishable from the silent-skip bug this guard exists to catch, so the
# allowlist records *why* it is not one rather than hiding it.
# (#13786 resolved the only entry this ever held: slm-service-control.yml and
# slm-service-logs.yml now declare `hosts: "{{ target }}"`, so an unset target is
# an undefined-variable error rather than a play that matches nothing and reports
# success. Templated patterns are skipped above, so an entry for it here would be
# a dormant exemption -- one that guards nothing while reading as though it does.)
_RUNTIME_SUPPLIED_PATTERNS: frozenset = frozenset()


def _ansible_files(root: pathlib.Path) -> list[pathlib.Path]:
    """Every playbook and task file, excluding worktrees and vendored trees.

    Exclusions are matched against the path **relative to root**: the checkout
    itself may live under a directory named in ``_EXCLUDE_DIRS`` (a git worktree
    at ``.worktrees/<branch>/`` is the normal case here), and matching the
    absolute path would silently exclude the entire repository.
    """
    found = []
    for path in root.rglob("*.y*ml"):
        rel_parts = path.relative_to(root).parts
        if any(part in _EXCLUDE_DIRS for part in rel_parts):
            continue
        if "ansible" in rel_parts:
            found.append(path)
    return sorted(found)


#: A ``vars:`` entry whose value is an absolute path, e.g.
#: ``deployed_src_root: /opt/autobot/src``. Only these are substituted -- a map
#: built from every ``key: value`` in the file would let an unrelated task key
#: shadow a variable name.
_VARS_BLOCK = re.compile(r"^(?P<indent>\s*)vars:\s*$")
_VAR_DEFINITION = re.compile(r"^(?P<indent>\s+)(?P<name>\w+)\s*:\s*(?P<value>/\S+)\s*$")

#: One ``{{ name }}`` reference, with or without inner spacing.
_TEMPLATE_REF = re.compile(r"\{\{\s*(?P<name>\w+)\s*\}\}")


def _var_definitions(text: str) -> dict[str, str]:
    """Absolute-path variables declared in this file's ``vars:`` blocks.

    Scoped to ``vars:`` deliberately. #15687 moves twenty literal deploy-root
    references behind a variable, and without substitution every one of them
    leaves this guard's population -- which is how #13744 would become
    undetectable again. The guard has to learn the templated form *before* the
    literals move, not after.
    """
    # YAML first: PyYAML resolves anchors (`&name` / `*name`) and merge keys
    # (`<<:`) for us, which is how the deploy root can be stated once in a file
    # of seven plays. A line scan cannot see through an alias -- it would read
    # `vars: *deploy_paths` as defining nothing, and every reference behind it
    # would silently leave this guard's population.
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        document = None
    if isinstance(document, list):
        resolved: dict[str, str] = {}
        for play in document:
            if not isinstance(play, dict):
                continue
            play_vars = play.get("vars")
            if not isinstance(play_vars, dict):
                continue
            for name, value in play_vars.items():
                if isinstance(value, str) and value.startswith("/"):
                    resolved[str(name)] = value
        if resolved:
            return resolved

    definitions: dict[str, str] = {}
    block_indent: int | None = None
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        opening = _VARS_BLOCK.match(line)
        if opening:
            block_indent = len(opening.group("indent"))
            continue
        if block_indent is None:
            continue
        definition = _VAR_DEFINITION.match(line)
        if definition and len(definition.group("indent")) > block_indent:
            definitions[definition.group("name")] = definition.group("value")
            continue
        # Any line at or left of the `vars:` indent ends the block.
        if len(line) - len(line.lstrip()) <= block_indent:
            block_indent = None
    return definitions


def _resolve(value: str, variables: dict[str, str]) -> str | None:
    """Substitute ``{{ name }}`` from *variables*; None when it cannot be resolved."""
    resolved = _TEMPLATE_REF.sub(lambda m: variables.get(m.group("name"), m.group(0)), value)
    if "{{" in resolved or "$" in resolved:
        return None
    return resolved


def _referenced_repo_paths(text: str) -> list[tuple[int, str, str]]:
    """Return ``(line_no, key, repo_relative_path)`` for deployed-src references."""
    variables = _var_definitions(text)
    hits = []
    for line_no, line in enumerate(text.splitlines(), 1):
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        value = match.group("value").strip("\"'")
        # Resolve templates against this file's vars before judging the prefix:
        # a value is no less checkable for being spelled `{{ root }}/x` (#15687).
        resolved = _resolve(value, variables)
        if resolved is None:
            continue
        if not resolved.startswith(_DEPLOYED_SRC_PREFIX):
            continue
        hits.append((line_no, match.group("key"), resolved[len(_DEPLOYED_SRC_PREFIX) :]))
    return hits


def _groups_in(node, acc: set) -> None:
    """Collect every group **and host** name declared in a parsed inventory.

    ``hosts:`` in a play accepts a host name as readily as a group name, so
    collecting only groups reports every host-targeted play as broken. A guard
    that cries wolf gets switched off, so both are gathered.
    """
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if key == "vars":
            continue
        if key == "hosts":
            if isinstance(value, dict):
                acc.update(value.keys())
            continue
        if key == "children":
            _groups_in(value, acc)
            continue
        acc.add(key)
        if isinstance(value, dict):
            _groups_in(value, acc)


def _inventory_paths(root: pathlib.Path) -> list[pathlib.Path]:
    """Every shipped inventory: the ``inventory/`` tree and ``inventory*`` files.

    Both forms are in use — ``ansible/inventory/hosts.yml`` and a sibling
    ``ansible/inventory.yml`` — and missing either makes plays that target the
    other look broken.
    """
    seen = {}
    for pattern in ("inventory/*.y*ml", "inventory*.y*ml", "inventory*.ini"):
        for path in root.rglob(pattern):
            rel_parts = path.relative_to(root).parts
            if any(part in _EXCLUDE_DIRS for part in rel_parts):
                continue
            seen[path] = None
    return sorted(seen)


def _ini_groups(text: str) -> set:
    """Group names from an INI-format inventory (``[group]`` headers)."""
    return {m.group(1).split(":")[0] for line in text.splitlines() if (m := re.match(r"^\s*\[([^\]]+)\]\s*$", line))}


def inventory_groups(root: pathlib.Path) -> dict[str, set]:
    """Return ``{inventory path: {group and host names}}`` for every inventory."""
    found = {}
    for path in _inventory_paths(root):
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        acc: set = set()
        if path.suffix == ".ini":
            acc = _ini_groups(text)
        else:
            try:
                parsed = yaml.safe_load(text)
            except yaml.YAMLError:
                # An inventory this script cannot parse is not evidence of a bad
                # play; skip it rather than reporting every pattern as unresolved.
                continue
            _groups_in(parsed, acc)
        if acc:
            found[str(path.relative_to(root))] = acc
    return found


def _host_patterns(text: str) -> list[tuple[int, str]]:
    """Return ``(line_no, pattern)`` for each play's ``hosts:`` declaration."""
    return [
        (line_no, match.group("pattern").strip("\"'"))
        for line_no, line in enumerate(text.splitlines(), 1)
        if (match := _HOSTS.match(line))
    ]


def _unresolvable_hosts(text: str, all_groups: set) -> list[tuple[int, str]]:
    """Host patterns that no shipped inventory defines."""
    unresolved = []
    for line_no, pattern in _host_patterns(text):
        if pattern in _IMPLICIT_GROUPS or "{{" in pattern or "$" in pattern:
            continue
        if pattern in _RUNTIME_SUPPLIED_PATTERNS:
            continue
        # A pattern may be a union/intersection expression; every named part
        # must come from somewhere.
        names = [n for n in re.split(r"[:,&!]", pattern) if n and n not in _IMPLICIT_GROUPS]
        if any(name not in all_groups for name in names):
            unresolved.append((line_no, pattern))
    return unresolved


#: Name this guard reports under.
HOOK_ID = "ansible-file-references"


# The vacuity floor below (#14896) counts plays READ, not references
# resolved. A walk that read no play at all -- wrong CWD, a renamed
# ansible/ directory, a discovery filter inverted -- used to print the
# success line and exit 0, reporting its own empty population as a pass.
# Flooring resolutions instead would be wrong in the other direction: a
# play whose only host pattern is runtime-supplied ('{{ target_group }}',
# 'localhost') legitimately resolves nothing, and that tree is honest.
def main() -> int:
    """Report every deployed-src reference with no matching repo path."""
    root = pathlib.Path(".").resolve()
    inventories = inventory_groups(root)
    all_groups = set().union(*inventories.values()) if inventories else set()

    path_violations, host_violations = [], []
    paths_checked = hosts_checked = plays_read = 0

    for play in _ansible_files(root):
        try:
            text = play.read_text(encoding="utf-8")
        except OSError:
            continue
        plays_read += 1
        rel_play = play.relative_to(root)
        for line_no, key, rel in _referenced_repo_paths(text):
            paths_checked += 1
            if not (root / rel).exists():
                path_violations.append(f"{rel_play}:{line_no}: {key} -> {rel} does not exist in the repo")
        hosts_checked += len(_host_patterns(text))
        for line_no, pattern in _unresolvable_hosts(text, all_groups):
            host_violations.append(f"{rel_play}:{line_no}: hosts: {pattern} — no inventory defines it")

    if path_violations:
        print("Ansible plays reference repo paths that do not exist:")
        print("\n".join(f"  {v}" for v in path_violations))
        print("\nThe deploy syncs the repo to /opt/autobot/src/, so each of these")
        print("resolves to a repo path. A wrong one fails on a host, not in CI.")

    if host_violations:
        print("Ansible plays target host groups no inventory defines:")
        print("\n".join(f"  {v}" for v in host_violations))
        print("\nA play whose pattern matches nothing is skipped silently —")
        print("ok=0 changed=0, exit 0 — which reads as a successful deploy.")

    if path_violations or host_violations:
        return 1

    # Vacuity floor (#14896) -- rationale in the comment above main().
    if enforce_reach(plays_read, 1, hook=HOOK_ID, full_repo=True):
        return 1

    print(
        f"check_ansible_file_references: {paths_checked} deployed-src reference(s) resolve; "
        f"{hosts_checked} host pattern(s) resolve against {len(inventories)} inventor"
        f"{'y' if len(inventories) == 1 else 'ies'}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
