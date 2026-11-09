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

The CI plane (requirements-ci/*, requirements-ci-test.txt) carries exact pins and, for the long-standing ones,
floors. Either may repeat a constrained package ONLY when its version satisfies the constraint, compared by
PEP 440 (so ``2.0rc1`` is below ``>=2.0``); one below a shared floor or past a cap is a violation. Converting
those floors to exact pins needs a resolver run against the whole CI set and is not done here.

Not covered (stated gap): a second declaration inside ``pyproject.toml`` (autobot_shared) is not seen,
because this guard reads requirements files only. That manifest has no ``-c`` and no dependabot block
reaches ``constraints/shared.txt`` from it, so ``repo_tests/autobot_shared_restates_no_constrained_floor_20092_test.py``
guards it instead.

Run from the repo root:  python3 scripts/check_constraint_drift.py
"""

import pathlib
import re
import sys

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

CONSTRAINTS = pathlib.Path("constraints/shared.txt")
# A requirement line carrying a version for some package: a specifier (also in the parenthesised form
# ``pkg (>=1)``) or a direct URL (``pkg @ https://...``), which pins a build just as a specifier does.
_SPEC = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*\(?\s*(===|==|>=|<=|~=|!=|>|<|@)")
_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(?:[=<>!~;(@]|$)")
# Test fixtures that merely match the `requirements*.txt` glob (package::reason lists, not manifests).
_EXCLUDE_TOP = ("repo_tests",)
# Packages declared in 2+ files that CANNOT share one pin yet. Each entry is a recorded conflict
# between planes; an entry leaves when the conflict is resolved, and a stale one is an error.
EXEMPT = {
    "websockets": "backend caps <16 (langgraph-sdk needs <16); the SLM backend floors >=17.3 -- no single range",
    "huggingface-hub": "tts-worker needs >=2.2,<3; ai-stack and npu-worker cap <2.0 -- no single range",
    "transformers": "the Windows NPU worker is exact-pinned to the vetted release (#15298); others float",
    "tokenizers": "ai-stack and npu-worker cap <0.24, which implies huggingface-hub<2.0; tts-worker gets tokenizers "
    "transitively and needs hub>=2.2 -- a shared cap would bind it (same conflict as huggingface-hub)",
    "pandas": "the backend and ai-stack manifests want >=3.1.0, but the CI llama-index-readers-file "
    "(every release up to 0.7.0) declares pandas<3 -- a shared constraint is unsatisfiable in the CI install",
    "redis": "declared >=8.1 in six manifests but the backend has no spec and a transitive redisvl "
    "(via langgraph-checkpoint-redis) that requires redis<8.0 -- a shared >=8.1 would major-bump the backend",
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


def _satisfies(version: str, spec: str) -> bool:
    """Does *version* meet the shared specifier? PEP 440 semantics: ``2.0rc1`` is below ``>=2.0``."""
    try:
        return SpecifierSet(spec).contains(Version(version), prereleases=True)
    except (InvalidSpecifier, InvalidVersion):
        return False


def constraint_specs() -> dict[str, str]:
    """Package -> its specifier text in constraints/shared.txt."""
    specs = {}
    for line in CONSTRAINTS.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*((?:==|>=|<)[^#\s]*)", line.strip())
        if m:
            specs[_norm(m.group(1))] = m.group(2)
    return specs


def _is_ci_plane(path: pathlib.Path) -> bool:
    return path.parts[0] == "requirements-ci" or path.name in ("requirements-ci.txt", "requirements-ci-test.txt")


def _ci_pin_ok(path: pathlib.Path, raw: str, spec: str | None) -> bool:
    """A CI-plane exact pin (or floor) that itself satisfies the shared constraint."""
    if spec is None or not _is_ci_plane(path):
        return False
    m = re.match(
        r"^\s*[A-Za-z0-9._-]+\s*(?:\[[^\]]*\])?\s*(?:==|>=)\s*([0-9][^\s,;#]*)",
        raw.split("#", 1)[0].split(";", 1)[0],
    )
    return bool(m) and _satisfies(m.group(1), spec)


def find_violations(decls, pinned: set[str], specs: dict[str, str] | None = None) -> list[str]:
    """Re-pins of a constrained package, and multiply-declared packages outside the constraints."""
    out: list[str] = []
    specs = specs or {}
    for pkg, sites in sorted(decls.items()):
        if pkg in pinned:
            out += [
                f"{f}:{n}: '{raw}' re-pins a constrained package"
                for f, n, raw, spec in sites
                if spec and not _ci_pin_ok(f, raw, specs.get(pkg))
            ]
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

    violations = find_violations(_declarations(requirement_files()), pinned, constraint_specs())
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
