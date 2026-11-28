#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Single-source guard: the role_*_active facts have exactly ONE definition (#14678).

This replaces ``check_role_facts_synced.py``, which asserted that two tracked
copies stayed byte-equal. A guard that keeps copies equal is the right guard
for a duplication you intend to keep and the wrong one for a duplication you
intend to remove: it passes while the duplicate is re-created. This guard
asserts the opposite -- that no second tracked definition can exist at all.

Rules, each checked over the tracked ``*.yml``/``*.yaml`` files under ansible/:

1. ``role_*_active`` / ``chromadb_service_owner`` are defined as top-level keys
   in exactly one file, ``inventory/group_vars/all.yml``,
   and that file defines every one of them it is expected to (non-empty set).
2. No other tracked file is named ``role_active_facts.yml``.
3. Every ``vars_files:`` entry that loads a facts file loads the canonical one.

Role ``defaults/main.yml`` files are out of scope: they hold deliberate,
lowest-precedence per-role floors (e.g. ``chromadb_service_owner`` in the
redis and ai-stack roles) that apply when no vars layer is loaded.

The CI test inventory's group_vars copy is generated and gitignored, so it is
not "tracked" and is covered instead by ``check_test_inventory_is_generated.py``.

Usage (from anywhere): ``python3 tools/lint/check_role_facts_single_source.py``
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from autobot_shared.paths import scrubbed_git_env  # noqa: E402

ANSIBLE = REPO / "autobot-slm-backend" / "ansible"
CANONICAL = "inventory/group_vars/all.yml"
FACTS_FILENAME = "role_active_facts.yml"

_FACT_KEY = re.compile(r"^(role_\w+_active|chromadb_service_owner):", re.MULTILINE)
_ROLE_DEFAULTS = re.compile(r"^roles/[^/]+/defaults/")
_VARS_FILES_ENTRY = re.compile(
    r"^\s*-\s*['\"]?([^\s'\"#]*(?:" + re.escape(FACTS_FILENAME) + r"|group_vars/all\.yml))['\"]?\s*$", re.MULTILINE
)


def defined_facts(text: str) -> set[str]:
    """Top-level fact keys a YAML text defines (indented keys are not definitions)."""
    return set(_FACT_KEY.findall(text))


def violations(files: dict[str, str]) -> list[str]:
    """Return every rule violation for ``{path relative to ansible/: text}``."""
    found: list[str] = []
    definers = sorted(rel for rel, text in files.items() if defined_facts(text) and not _ROLE_DEFAULTS.match(rel))
    if definers != [CANONICAL]:
        found.append(f"role_*_active facts must be defined in exactly {CANONICAL}; defined in: {definers or 'NO file'}")
    elif len(defined_facts(files[CANONICAL])) < 2:
        found.append(f"{CANONICAL} defines fewer than 2 facts -- the single source is empty")
    for rel in sorted(files):
        if rel.rsplit("/", 1)[-1] == FACTS_FILENAME and rel != CANONICAL:
            found.append(f"{rel}: a second {FACTS_FILENAME} -- there is one definition, at {CANONICAL}")
    for rel, text in sorted(files.items()):
        for entry in _VARS_FILES_ENTRY.findall(text):
            resolved = (Path(rel).parent / entry).as_posix()
            if _normalise(resolved) != CANONICAL:
                found.append(f"{rel}: vars_files loads {entry!r}, not the single definition {CANONICAL}")
    return found


def _normalise(path: str) -> str:
    parts: list[str] = []
    for part in Path(path).parts:
        if part == "..":
            if parts:
                parts.pop()
        elif part != ".":
            parts.append(part)
    return "/".join(parts)


def tracked_yaml(root: Path = ANSIBLE) -> dict[str, str]:
    """Tracked ansible YAML, read from git so untracked/generated copies are excluded."""
    out = subprocess.run(
        ["git", "ls-files", "--", "*.yml", "*.yaml"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout.split()
    return {rel: (root / rel).read_text(encoding="utf-8") for rel in out if (root / rel).is_file()}


def main() -> int:
    files = tracked_yaml()
    if not files:
        print("NO TRACKED YAML FOUND under ansible/ -- the guard did not look at anything")
        return 1
    problems = violations(files)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"OK -- {len(defined_facts(files[CANONICAL]))} facts, one definition ({CANONICAL}); {len(files)} files read")
    return 0


if __name__ == "__main__":
    sys.exit(main())
