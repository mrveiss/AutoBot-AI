#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: Ansible plays only reference repo files that exist (#13744).

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

Run from the repo root:  python3 scripts/check_ansible_file_references.py
"""

import pathlib
import re
import sys

# The deploy syncs the repo to this prefix, so what follows it is a repo path.
_DEPLOYED_SRC_PREFIX = "/opt/autobot/src/"

# Keys whose value is a path to a file the repo is expected to provide.
_FILE_KEYS = ("requirements", "src", "chdir", "creates")

_EXCLUDE_DIRS = (".worktrees", ".git", "node_modules", "__pycache__")

_ASSIGNMENT = re.compile(
    r"^\s*(?P<key>" + "|".join(_FILE_KEYS) + r")\s*:\s*(?P<value>\S+)\s*$",
)


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


def main() -> int:
    """Report every deployed-src reference with no matching repo path."""
    root = pathlib.Path(".").resolve()
    violations = []
    checked = 0

    for play in _ansible_files(root):
        try:
            text = play.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, key, rel in _referenced_repo_paths(text):
            checked += 1
            if not (root / rel).exists():
                violations.append(f"{play.relative_to(root)}:{line_no}: {key} -> {rel} does not exist in the repo")

    if violations:
        print("Ansible plays reference repo paths that do not exist:")
        print("\n".join(f"  {v}" for v in violations))
        print("\nThe deploy syncs the repo to /opt/autobot/src/, so each of these")
        print("resolves to a repo path. A wrong one fails on a host, not in CI.")
        return 1

    print(f"check_ansible_file_references: {checked} deployed-src reference(s) resolve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
