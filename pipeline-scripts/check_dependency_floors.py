#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Report installed distributions sitting BELOW a version this repo declares (#15091).

Local verification runs under whatever interpreter is on PATH. When that
interpreter's packages are older than the versions the repo declares, every
local gate still passes -- and the pass says nothing about CI, which installs
the declared set.

#14998 lost a diagnosis cycle to exactly that: a guard enumerating a router's
routes returned 26 locally and 3 in CI, because ``include_router`` defers on
the declared fastapi 0.141.1 and does not on the 0.135.2 that happened to be
installed. #15093 records that behaviour; this script records the condition
that let it go unnoticed.

Reporting, not gating. ``scripts/setup-ci-parity-env.sh`` builds an environment
that satisfies the declared set without touching anything outside its venv;
``--strict`` is for a caller that wants the non-zero exit instead.
"""

from __future__ import annotations

import argparse
import platform
import re
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Iterable, Mapping, Sequence

#: Entry points of the requirement graph describing the environment local
#: verification is meant to reproduce. Each is expanded through its ``-r``
#: includes, so ``requirements-ci.txt``'s twelve children are covered without
#: being named here -- a child added later is picked up for free.
DECLARATION_ROOTS: tuple[str, ...] = (
    "requirements-ci.txt",
    "requirements-ci-test.txt",
    "autobot-backend/requirements.txt",
    "autobot-slm-backend/requirements.txt",
)

MAX_REPORTED = 10

#: Stands in for a version in a :class:`Shortfall` raised for a distribution
#: that is not installed at all. Only reachable when a caller asks for it --
#: see ``require_present`` on :func:`shortfalls`.
ABSENT = "(absent)"

_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(?:\[[^\]]*\])?\s*(==|>=|~=|>)\s*([0-9][A-Za-z0-9.]*)")
_INCLUDE = re.compile(r"^\s*(?:-r|--requirement)[\s=]+(\S+)")
_RELEASE = re.compile(r"^(\d+(?:\.\d+)*)(.*)$")


class EmptyEnumerationError(RuntimeError):
    """Raised when the requirement sweep finds nothing to check.

    "Nothing is below floor" drawn from zero declarations is indistinguishable
    from a healthy environment. This repo has already shipped a test that
    passed that way (#15087), so the empty case is an error, never a pass.
    """


@dataclass(frozen=True)
class Declaration:
    """One lower bound a requirements file imposes on a distribution."""

    source: str  # repo-relative "path:line"
    name: str  # canonical distribution name
    operator: str
    required: str


@dataclass(frozen=True)
class Shortfall:
    """A declared floor the environment running this check does not meet."""

    declaration: Declaration
    installed: str

    def describe(self) -> str:
        declared = f"{self.declaration.operator}{self.declaration.required}"
        if self.installed == ABSENT:
            return f"{self.declaration.name}: NOT INSTALLED, declared {declared} ({self.declaration.source})"
        return (
            f"{self.declaration.name}: installed {self.installed}, " f"declared {declared} ({self.declaration.source})"
        )


def canonical(name: str) -> str:
    """PEP 503 style name folding, so ``PyJWT`` and ``pyjwt`` are one key."""
    return re.sub(r"[-_.]+", "-", name).lower()


def _ordinal(raw: str) -> tuple[tuple[int, ...], int]:
    """Release numbers plus a final-release flag, for ordering two versions.

    The flag puts ``1.6.0rc1`` below ``1.6.0`` while leaving every plain
    release comparison exact. Epochs and post-releases are not modelled -- no
    declaration in this repo uses one -- and an unparsable version sorts
    lowest, so it is reported rather than silently accepted.

    A PEP 440 local segment is dropped first, so ``2.13.0+cpu`` compares as the
    ``2.13.0`` it is. Without that it read as a pre-release and was reported as
    below its own pin -- and the CPU torch build it names is one
    ``scripts/setup-ci-parity-env.sh`` installs on purpose, so the shortfall
    was both false and permanent (#15130).
    """
    public = raw.strip().partition("+")[0]
    match = _RELEASE.match(public)
    if not match:
        return (0,), 0
    return tuple(int(part) for part in match.group(1).split(".")), 0 if match.group(2) else 1


def satisfies(installed: str, operator: str, required: str) -> bool:
    """True when *installed* meets the ``operator required`` lower bound."""
    have_release, have_final = _ordinal(installed)
    want_release, want_final = _ordinal(required)
    width = max(len(have_release), len(want_release))
    have = ((have_release + (0,) * width)[:width], have_final)
    want = ((want_release + (0,) * width)[:width], want_final)
    if operator == ">":
        return have > want
    if operator == "==":
        return have == want
    return have >= want


def _includes(path: Path) -> list[Path]:
    """Files pulled in by ``-r`` / ``--requirement`` lines of *path*."""
    out: list[Path] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        match = _INCLUDE.match(raw.split("#")[0])
        if match:
            out.append((path.parent / match.group(1)).resolve())
    return out


def declaration_files(root: Path, roots: Sequence[str] | None = None) -> list[Path]:
    """Every requirements file reachable from *roots* (default :data:`DECLARATION_ROOTS`).

    Resolved at call time, not bound as a default, so a caller that rebinds
    :data:`DECLARATION_ROOTS` still steers this.
    """
    seen: list[Path] = []
    queue = [(root / name).resolve() for name in (DECLARATION_ROOTS if roots is None else roots)]
    while queue:
        current = queue.pop(0)
        if current in seen or not current.is_file():
            continue
        seen.append(current)
        queue.extend(_includes(current))
    return seen


def parse_declarations(files: Iterable[Path], root: Path) -> list[Declaration]:
    """Every lower bound declared across *files*, in file order."""
    out: list[Declaration] = []
    for path in files:
        source = path.relative_to(root).as_posix()
        for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            line = raw.split("#")[0].strip()
            if not line or line.startswith("-"):
                continue
            match = _REQUIREMENT.match(line)
            if match:
                out.append(Declaration(f"{source}:{lineno}", canonical(match.group(1)), match.group(2), match.group(3)))
    return out


def installed_versions(names: Iterable[str]) -> dict[str, str]:
    """Version of each named distribution that is importable in this interpreter."""
    found: dict[str, str] = {}
    for name in set(names):
        try:
            found[name] = version(name)
        except PackageNotFoundError:
            continue
    return found


def shortfalls(
    declarations: Sequence[Declaration],
    installed: Mapping[str, str],
    require_present: bool = False,
) -> list[Shortfall]:
    """Declared floors *installed* does not meet.

    By default an absent distribution is not a shortfall: an arbitrary box
    simply does not have it, which says nothing about the version CI would
    resolve.

    *require_present* flips that for the one caller where absence IS the
    defect. ``scripts/setup-ci-parity-env.sh`` installs these very files, so a
    declaration with nothing installed against it means the install did not
    take -- and the consequence is silent, because a test module that
    ``importorskip``s the missing package is never collected at all. Nine such
    packages were sitting in the parity venv when this was written, one of them
    the docker SDK whose own requirement comment warns that its absence skips a
    whole smoke suite without a word (#15130).
    """
    out: list[Shortfall] = []
    for declaration in declarations:
        have = installed.get(declaration.name)
        if have is None:
            if require_present:
                out.append(Shortfall(declaration, ABSENT))
            continue
        if not satisfies(have, declaration.operator, declaration.required):
            out.append(Shortfall(declaration, have))
    return out


def audit(root: Path, roots: Sequence[str] | None = None, require_present: bool = False) -> tuple[list[Shortfall], int]:
    """Shortfalls in *root*'s declared set, plus how many declarations were read.

    *roots* narrows the sweep to a subset of the entry points. A caller that
    installs only part of the graph -- ``scripts/setup-ci-parity-env.sh``
    installs ``requirements-ci.txt`` and ``requirements-ci-test.txt`` and
    nothing else -- must be judged against what it installs, or the backend
    declarations it never had would read as its own drift (#15130).

    Raises :class:`EmptyEnumerationError` when the sweep reads nothing, so an
    empty enumeration can never be reported as a clean environment.
    """
    swept = DECLARATION_ROOTS if roots is None else roots
    files = declaration_files(root, swept)
    declarations = parse_declarations(files, root)
    if not declarations:
        raise EmptyEnumerationError(
            f"no version declarations found under {root}: "
            f"{len(files)} requirement file(s) reachable from {list(swept)}"
        )
    installed = installed_versions(declaration.name for declaration in declarations)
    return shortfalls(declarations, installed, require_present), len(declarations)


def render(found: Sequence[Shortfall], examined: int, limit: int = MAX_REPORTED) -> list[str]:
    """The report, one line per element; *limit* caps the per-package detail."""
    if not found:
        return [f"dependency floors: {examined} declarations checked, all satisfied"]
    lines = [
        f"{len(found)} of {examined} declared versions are NOT satisfied by the "
        f"interpreter running this check (python {platform.python_version()}).",
        "A pass here therefore carries no information about CI, which installs " "the declared set.",
    ]
    lines.extend(f"  {shortfall.describe()}" for shortfall in found[:limit])
    if len(found) > limit:
        remaining = len(found) - limit
        lines.append(
            f"  ... and {remaining} more; " "run pipeline-scripts/check_dependency_floors.py --all to list them"
        )
    lines.append("Reproduce the declared environment: scripts/setup-ci-parity-env.sh")
    lines.append("Otherwise push and read CI. Known divergence: #15093 (include_router defers).")
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Report installed packages below a declared floor.")
    parser.add_argument("--root", type=Path, default=None, help="repo root to audit")
    parser.add_argument("--strict", action="store_true", help="exit 1 when any declared floor is unsatisfied")
    parser.add_argument("--all", action="store_true", help="list every shortfall, not just the first few")
    parser.add_argument(
        "--require-present",
        action="store_true",
        help="also report declarations with nothing installed against them",
    )
    parser.add_argument(
        "--roots",
        nargs="*",
        metavar="FILE",
        default=None,
        help="repo-relative requirement entry points to sweep (default: every root)",
    )
    args = parser.parse_args(argv)
    root = (args.root or Path(__file__).resolve().parents[1]).resolve()
    if args.roots is not None and not args.roots:
        print("FATAL: --roots was given no files, so there is nothing to check", file=sys.stderr)  # noqa: print
        return 2
    try:
        found, examined = audit(
            root, None if args.roots is None else tuple(args.roots), require_present=args.require_present
        )
    except EmptyEnumerationError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)  # noqa: print
        return 2
    for line in render(found, examined, len(found) if args.all else MAX_REPORTED):
        print(line)  # noqa: print
    return 1 if found and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
