#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Guard: ``group_vars/<name>.yml`` and ``group_vars/<name>/`` must never coexist (#18514).

Ansible resolves a group's vars to the DIRECTORY when both exist and then does
not load the sibling file at all. #18505 moved the role-active facts into
``group_vars/all/`` beside ``all.yml``; every key in ``all.yml`` (``autobot.base_dir``
first) became undefined and live updates failed. Nothing errors -- the file is
simply never read -- so only a structural guard catches it.

Scope: every ``group_vars`` and ``host_vars`` directory under ``autobot-slm-backend/ansible``
(tracked or not -- the CI test inventory's generated copy must obey it too).
Exit 1 on any shadowing, and on finding no group_vars directory at all (did not look).

Usage: ``python3 tools/lint/check_group_vars_no_shadow.py``
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
ANSIBLE = REPO / "autobot-slm-backend" / "ansible"
VARS_DIRS = ("group_vars", "host_vars")
VARS_SUFFIXES = (".yml", ".yaml", ".json")


def vars_roots(root: Path) -> list[Path]:
    """Every group_vars/host_vars directory under ``root``."""
    return sorted(p for p in root.rglob("*") if p.is_dir() and p.name in VARS_DIRS)


def violations(root: Path = ANSIBLE) -> list[str]:
    """Return one message per shadowing pair under ``root``."""
    found: list[str] = []
    for vars_root in vars_roots(root):
        for name in sorted({p.stem for p in vars_root.iterdir() if p.is_file() and p.suffix in VARS_SUFFIXES}):
            if (vars_root / name).is_dir():
                found.append(
                    f"{vars_root.relative_to(root)}/{name}/ shadows {name}{{.yml,.yaml,.json}}: "
                    "Ansible loads the directory and silently ignores the file (#18514). "
                    "Merge the directory's content into the file or move it elsewhere."
                )
    return found


def main() -> int:
    roots = vars_roots(ANSIBLE)
    if not roots:
        print(f"NO group_vars/host_vars DIRECTORY FOUND under {ANSIBLE} -- the guard did not look at anything")
        return 1
    problems = violations(ANSIBLE)
    for problem in problems:
        print(problem)
    if problems:
        return 1
    print(f"OK -- {len(roots)} vars director{'y' if len(roots) == 1 else 'ies'} checked, no file/directory shadowing")
    return 0


if __name__ == "__main__":
    sys.exit(main())
