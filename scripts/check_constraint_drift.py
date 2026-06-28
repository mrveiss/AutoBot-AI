#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: shared dependency versions live in ONE place (#10524).

`constraints/shared.txt` is the single source of truth for libraries that must be
identical across all components (Ansible can co-locate roles on one host, so a
version split makes pip unsatisfiable and skews the numpy ABI on shared embeddings).

This guard fails if any component requirements file re-declares a *version* for a
library that the constraints file already pins. Components must reference the
constraint (``-c <rel>/constraints/shared.txt``) and list the package bare (``numpy``).

Run from the repo root:  python3 scripts/check_constraint_drift.py
"""

import pathlib
import re
import sys

CONSTRAINTS = pathlib.Path("constraints/shared.txt")
# A requirement line carrying a version specifier for some package.
_SPEC = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(==|>=|<=|~=|!=|>|<)")
_EXCLUDE_DIRS = ("node_modules", ".worktrees", ".git", "__pycache__")


def _norm(name: str) -> str:
    """PEP 503 normalization so Numpy / numpy / NUMPY compare equal."""
    return re.sub(r"[-_.]+", "-", name).lower()


def constrained_packages() -> set[str]:
    """Package names that constraints/shared.txt pins a version for."""
    pkgs = set()
    for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        m = _SPEC.match(line)
        if m:
            pkgs.add(_norm(m.group(1)))
    return pkgs


def requirement_files() -> list[pathlib.Path]:
    files = []
    seen = set()
    # `requirements*.txt` anywhere, plus every *.txt inside a `requirements*` directory
    # (e.g. requirements-ci/ai-ml.txt, which is a requirements file not named requirements*).
    for pattern in ("requirements*.txt", "requirements*/*.txt"):
        for p in pathlib.Path(".").rglob(pattern):
            if any(part in _EXCLUDE_DIRS for part in p.parts):
                continue
            if p == CONSTRAINTS or p in seen:
                continue
            seen.add(p)
            files.append(p)
    return sorted(files)


def main() -> int:
    if not CONSTRAINTS.exists():
        print(f"ERROR: {CONSTRAINTS} not found (run from repo root).", file=sys.stderr)
        return 2

    pinned = constrained_packages()
    if not pinned:
        print(f"ERROR: {CONSTRAINTS} pins no packages — nothing to guard.", file=sys.stderr)
        return 2

    violations: list[str] = []
    for f in requirement_files():
        for n, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            m = _SPEC.match(line)
            if m and _norm(m.group(1)) in pinned:
                violations.append(f"{f}:{n}: '{raw.strip()}' re-pins a constrained package")

    if violations:
        print("Constraint drift — these versions belong ONLY in constraints/shared.txt:\n", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            f"\nFix: remove the version and reference the constraint instead, e.g.\n"
            f"    -c <relative-path>/constraints/shared.txt\n"
            f"    {sorted(pinned)[0]}\n",
            file=sys.stderr,
        )
        return 1

    print(f"OK: no constraint drift. Guarded packages: {', '.join(sorted(pinned))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
