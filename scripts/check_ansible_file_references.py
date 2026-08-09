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

# The deploy syncs the repo to this prefix, so what follows it is a repo path.
_DEPLOYED_SRC_PREFIX = "/opt/autobot/src/"

# Keys whose value is a path to a file the repo is expected to provide.
_FILE_KEYS = ("requirements", "src", "chdir", "creates")

_EXCLUDE_DIRS = (".worktrees", ".git", "node_modules", "__pycache__")

_ASSIGNMENT = re.compile(
    r"^\s*(?P<key>" + "|".join(_FILE_KEYS) + r")\s*:\s*(?P<value>\S+)\s*$",
)

_HOSTS = re.compile(r"^\s*hosts:\s*(?P<pattern>\S+)\s*$")

# Patterns Ansible resolves without an inventory group of that name.
_IMPLICIT_GROUPS = frozenset({"all", "localhost", "*", "127.0.0.1"})

# Patterns supplied by the caller at run time rather than by a shipped
# inventory. Each entry needs a tracking issue: a bare name here is
# indistinguishable from the silent-skip bug this guard exists to catch, so the
# allowlist records *why* it is not one rather than hiding it.
#   `target` — slm-service-control.yml / slm-service-logs.yml, the SLM remote
#   service-control path. No shipped inventory defines it and no in-repo caller
#   passes one; whether it should become `{{ target }}` (loud failure) is a
#   remote-execution decision tracked in #13786.
_RUNTIME_SUPPLIED_PATTERNS = frozenset({"target"})


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


def _referenced_repo_paths(text: str) -> list[tuple[int, str, str]]:
    """Return ``(line_no, key, repo_relative_path)`` for deployed-src references."""
    hits = []
    for line_no, line in enumerate(text.splitlines(), 1):
        match = _ASSIGNMENT.match(line)
        if not match:
            continue
        value = match.group("value").strip("\"'")
        if not value.startswith(_DEPLOYED_SRC_PREFIX):
            continue
        # A templated segment cannot be resolved statically; skip rather than guess.
        if "{{" in value or "$" in value:
            continue
        hits.append((line_no, match.group("key"), value[len(_DEPLOYED_SRC_PREFIX) :]))
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
    return {
        m.group(1).split(":")[0]
        for line in text.splitlines()
        if (m := re.match(r"^\s*\[([^\]]+)\]\s*$", line))
    }


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


def main() -> int:
    """Report every deployed-src reference with no matching repo path."""
    root = pathlib.Path(".").resolve()
    inventories = inventory_groups(root)
    all_groups = set().union(*inventories.values()) if inventories else set()

    path_violations, host_violations = [], []
    paths_checked = hosts_checked = 0

    for play in _ansible_files(root):
        try:
            text = play.read_text(encoding="utf-8")
        except OSError:
            continue
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

    print(
        f"check_ansible_file_references: {paths_checked} deployed-src reference(s) resolve; "
        f"{hosts_checked} host pattern(s) resolve against {len(inventories)} inventor"
        f"{'y' if len(inventories) == 1 else 'ies'}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
