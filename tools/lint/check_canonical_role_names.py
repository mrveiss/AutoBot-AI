#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Regression-prevention check for #7053 Ansible role-name canonicalization.

Blocks new gate conditions that check short-form role names directly against
``node_roles``.  The canonical form is ``autobot-X`` (e.g. ``autobot-backend``);
short forms like ``'backend' in node_roles`` are deprecated.

Preferred pattern for new gates:
    when: role_backend_active          # use the shared fact (best)
    when: "'autobot-backend' in ..."   # canonical direct check (acceptable)

Blocked patterns:
    when: "'backend' in node_roles"    # short form — DEPRECATED (#7053)
    when: "'frontend' in node_roles"
    # ... etc. for all deprecated aliases

Allowlist: group_vars/all.yml and vars/role_active_facts.yml must maintain
the OR-chains for backward compat with existing hosts — those files are
excluded from this check.

Exit code:
  0 — clean
  1 — banned patterns found (commit blocked)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

REPO_ROOT = Path(__file__).resolve().parents[2]

# Deprecated short-form role names and their canonical replacements (#7053).
# Update this dict when adding new roles — see docs/developer/ANSIBLE_ROLE_NAMES.md.
DEPRECATED_SHORT_FORMS: Dict[str, str] = {
    "backend": "autobot-backend",
    "frontend": "autobot-frontend",
    "ai-stack": "autobot-ai-stack",
    "npu-worker": "autobot-npu-worker",
    "browser": "autobot-browser-worker",
    "browser-service": "autobot-browser-worker",
    "tts-worker": "autobot-tts-worker",
}

# Files allowed to use the deprecated short forms (backward-compat OR-chains).
ALLOWLIST: frozenset[str] = frozenset(
    {
        # The facts themselves must check both forms for backward compat.
        "autobot-slm-backend/ansible/inventory/group_vars/all.yml",
        "autobot-slm-backend/ansible/playbooks/vars/role_active_facts.yml",
        # This file and its test.
        "tools/lint/check_canonical_role_names.py",
        "tools/lint/check_canonical_role_names_test.py",
    }
)

# Matches: 'short-name' in node_roles  (various quote styles)
# Captures: the role name (group 1).
# Examples matched:
#   'backend' in node_roles
#   "frontend" in node_roles
#   ('ai-stack' in node_roles)
# Not matched (canonical):
#   'autobot-backend' in node_roles
_ROLE_PAT = re.compile(
    r"""['"](""" + "|".join(re.escape(k) for k in DEPRECATED_SHORT_FORMS) + r""")['"]\s+in\s+node_roles"""
)


def iter_yaml_files(root: Path) -> Iterable[Path]:
    """Yield .yml/.yaml files under root, skipping vendored/cached dirs."""
    skip_dirs = {".git", "__pycache__", "node_modules", ".worktrees", "venv", ".venv"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in {".yml", ".yaml"}:
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        yield path


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def find_violations(path: Path) -> List[Tuple[int, str, str, str]]:
    """Return (lineno, deprecated_name, canonical_name, snippet) tuples."""
    rel = _rel(path)
    if rel in ALLOWLIST:
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    violations: List[Tuple[int, str, str, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        # Skip comment lines (Ansible YAML comment = leading #).
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        for match in _ROLE_PAT.finditer(line):
            deprecated = match.group(1)
            canonical = DEPRECATED_SHORT_FORMS[deprecated]
            violations.append((lineno, deprecated, canonical, line.strip()[:120]))
    return violations


def main(paths: List[str]) -> int:
    if paths:
        targets = [Path(p) for p in paths]
        files = [p for p in targets if p.is_file() and p.suffix in {".yml", ".yaml"}]
    else:
        # Scan the whole Ansible tree if invoked with no args (manual run).
        files = list(iter_yaml_files(REPO_ROOT / "autobot-slm-backend" / "ansible"))

    found = False
    for path in files:
        for lineno, deprecated, canonical, snippet in find_violations(path):
            rel = _rel(path)
            print(
                f"{rel}:{lineno}: deprecated role name '{deprecated}' in node_roles (#7053)\n"
                f"  Use canonical form '{canonical}' or the shared fact "
                f"role_{deprecated.replace('-', '_')}_active\n"
                f"  {snippet}",
                file=sys.stderr,
            )
            found = True

    if found:
        print(
            "\n--- BLOCKED ---\n"
            "Short-form role names in node_roles checks are deprecated (#7053).\n"
            "Options:\n"
            "  1. Use the shared boolean fact:  when: role_X_active\n"
            "  2. Use the canonical form:       when: \"'autobot-X' in node_roles\"\n"
            "See docs/developer/ANSIBLE_ROLE_NAMES.md for the full canonical name table.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
