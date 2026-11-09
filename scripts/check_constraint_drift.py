#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Guard: shared dependency versions live in ONE place (#10524, #18060).

`constraints/shared.txt` is the single source of truth for libraries that must be
identical across all components (Ansible can co-locate roles on one host, so a
version split makes pip unsatisfiable and skews the numpy ABI on shared embeddings).

This guard fails if any component requirements file re-declares a *version* for a
library that the constraints file already pins. Components must reference the
constraint (``-c <rel>/constraints/shared.txt``) and list the package bare (``numpy``).

A package declared in two or more requirements files must also sit in the constraints file
(#18060), otherwise each file carries its own spec and they drift apart. EXEMPT lists the few
that cannot yet share one range.

Run from the repo root:  python3 scripts/check_constraint_drift.py
"""

import pathlib
import re
import sys

CONSTRAINTS = pathlib.Path("constraints/shared.txt")
# A requirement line carrying a version specifier for some package.
_SPEC = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(==|>=|<=|~=|!=|>|<)")
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:[=<>!~;]|$)")
# Test fixtures that merely match the `requirements*.txt` glob (package::reason lists, not manifests).
_EXCLUDE_TOP = ("repo_tests",)
# Packages declared in 2+ files that CANNOT share one pin yet. Each entry is a recorded conflict
# between planes; an entry leaves when the conflict is resolved, and a stale one is an error.
EXEMPT = {
    "websockets": "backend caps <16 (langgraph-sdk needs <16); the SLM backend floors >=17.3 -- no single range",
    "huggingface-hub": "tts-worker needs >=2.2,<3; ai-stack and npu-worker cap <2.0 -- no single range",
    "transformers": "the Windows NPU worker is exact-pinned to the vetted release (#15298); others float",
}
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
            if any(part in _EXCLUDE_DIRS for part in p.parts) or p.parts[0] in _EXCLUDE_TOP:
                continue
            if p == CONSTRAINTS or p in seen:
                continue
            seen.add(p)
            files.append(p)
    return sorted(files)


def _declarations(files: list[pathlib.Path]) -> dict[str, list[tuple[pathlib.Path, int, str, bool]]]:
    """package -> [(file, line number, raw line, carries a version spec)]."""
    decls: dict[str, list[tuple[pathlib.Path, int, str, bool]]] = {}
    for f in files:
        for n, raw in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.split("#", 1)[0].strip()
            if not line or line.startswith("-"):
                continue
            m = _NAME.match(line)
            if m:
                spec = bool(_SPEC.match(line.split(";", 1)[0]))
                decls.setdefault(_norm(m.group(1)), []).append((f, n, raw.strip(), spec))
    return decls


def find_violations(decls, pinned: set[str]) -> list[str]:
    """Re-pins of a constrained package, and multiply-declared packages outside the constraints."""
    out: list[str] = []
    for pkg, sites in sorted(decls.items()):
        if pkg in pinned:
            out += [f"{f}:{n}: '{raw}' re-pins a constrained package" for f, n, raw, spec in sites if spec]
        elif pkg not in EXEMPT and len({f for f, *_ in sites}) >= 2 and any(s for *_, s in sites):
            where = ", ".join(sorted({str(f) for f, *_ in sites}))
            out.append(
                f"{pkg}: declared in {len({f for f, *_ in sites})} files ({where}) but absent from {CONSTRAINTS}"
            )
    for pkg in sorted(EXEMPT):
        if pkg in pinned or len({f for f, *_ in decls.get(pkg, [])}) < 2:
            out.append(f"{pkg}: stale EXEMPT entry -- it no longer needs the exemption; remove it")
    return out


def main() -> int:
    if not CONSTRAINTS.exists():
        print(f"ERROR: {CONSTRAINTS} not found (run from repo root).", file=sys.stderr)
        return 2

    pinned = constrained_packages()
    if not pinned:
        print(f"ERROR: {CONSTRAINTS} pins no packages — nothing to guard.", file=sys.stderr)
        return 2

    violations = find_violations(_declarations(requirement_files()), pinned)
    if violations:
        print("Constraint drift — these versions belong ONLY in constraints/shared.txt:\n", file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        print(
            "\nFix: move the spec into constraints/shared.txt, list the package bare in each file, and add\n"
            "    -c <relative-path>/constraints/shared.txt\n",
            file=sys.stderr,
        )
        return 1

    print(f"OK: no constraint drift. {len(pinned)} packages guarded; {len(EXEMPT)} exempt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
