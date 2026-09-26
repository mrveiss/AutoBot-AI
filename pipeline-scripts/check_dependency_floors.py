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
import json
import os
import platform
import re
import subprocess
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

#: (package, declaring requirements file) pairs known to sit below their own
#: declared floor for a *documented* cross-venv reason -- never a blanket
#: license to ignore a shortfall, only an exact (name, source file) match.
#: ``--strict`` treats a listed pair as satisfied; everything else it still
#: fails on. Each value is the reason a human can act on, not just a marker.
#:
#: Stays empty (#16394). Its one-ever entry -- websockets vs
#: autobot-slm-backend/requirements.txt, because #13300's ci.yml shared one
#: venv between the backend and SLM suites -- is gone now that
#: .github/actions/setup-python-suite/action.yml builds the SLM suite its own
#: venv from its own requirements.txt, and ci.yml's floor-check steps are each
#: scoped with --roots to what that venv actually installs. A real cross-venv
#: mismatch is once again possible in principle, but the fix is a genuinely
#: separate venv for whichever caller needs it, the way this one now works --
#: not a new entry here. check_dependency_floors_test.py pins this empty.
KNOWN_CROSS_VENV_EXEMPTIONS: Mapping[tuple[str, str], str] = {}

MAX_REPORTED = 10

#: Stands in for a version in a :class:`Shortfall` raised for a distribution
#: that is not installed at all. Only reachable when a caller asks for it --
#: see ``require_present`` on :func:`shortfalls`.
ABSENT = "(absent)"

#: Installed, but the check could NOT determine its version -- duplicate
#: dist-info directories from an in-place upgrade that never removed the old
#: metadata (#15063: the deployed venv is append-only), or metadata with no
#: Version field. Unlike ABSENT this is ALWAYS reported: "not installed" is
#: an answer, "could not read it" is the absence of one, and #17449 found a
#: deployed venv where the two were indistinguishable -- a package carrying
#: two dist-info directories was silently skipped and the environment read
#: as fully satisfied.
UNREADABLE = "(version unreadable)"

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
        if self.installed == UNREADABLE:
            return (
                f"{self.declaration.name}: INSTALLED BUT VERSION UNREADABLE, declared {declared} "
                f"({self.declaration.source}) -- usually duplicate *.dist-info from an in-place "
                "upgrade; this floor was NOT checked"
            )
        return (
            f"{self.declaration.name}: installed {self.installed}, " f"declared {declared} ({self.declaration.source})"
        )


def is_exempt(shortfall: Shortfall, exemptions: Mapping[tuple[str, str], str] = KNOWN_CROSS_VENV_EXEMPTIONS) -> bool:
    """True when *shortfall* is a documented cross-venv mismatch, not real drift.

    Matches by (package, declaring file) only -- never by line number, which
    shifts on an unrelated edit -- and never partially: a package exempted
    for one requirements file still fails for every other file that declares
    it below floor.
    """
    source_file = shortfall.declaration.source.rsplit(":", 1)[0]
    return (shortfall.declaration.name, source_file) in exemptions


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


#: Seconds the probe may take before the target counts as unreadable.
_PROBE_TIMEOUT = 120


class InterpreterUnreadable(RuntimeError):
    """A named interpreter could not be queried. NOT the same as 'nothing installed'."""


def _probe_source() -> str:
    """The script run inside the target interpreter. Imports nothing from this repo."""
    return (
        "import json,sys,collections\n"
        "from importlib.metadata import version,distributions,PackageNotFoundError\n"
        "def c(n): return n.lower().replace('_','-').replace('.','-')\n"
        "seen=collections.Counter()\n"
        "for d in distributions():\n"
        "    try: nm=d.metadata['Name']\n"
        "    except Exception: nm=None\n"
        "    if nm: seen[c(nm)]+=1\n"
        "dup=sorted(k for k,v in seen.items() if v>1)\n"
        "out={}\n"
        "for n in json.load(sys.stdin):\n"
        "    try: out[n]=version(n) or ''\n"
        "    except PackageNotFoundError: continue\n"
        "    except Exception: out[n]=''\n"
        "json.dump({'v':'%d.%d.%d'%sys.version_info[:3],'p':out,'dup':dup},sys.stdout)\n"
    )


def duplicate_metadata_names() -> frozenset[str]:
    """Canonical names with MORE THAN ONE dist-info in this interpreter.

    An in-place upgrade that leaves the previous ``*.dist-info`` behind gives
    one distribution two metadata directories. `importlib.metadata.version()`
    then has two answers and returns neither usefully, so the package reads as
    "not installed" and its floor is never checked. That is #15063's
    append-only venv showing up as a hole in the instrument rather than as a
    stale package.
    """
    seen: dict[str, int] = {}
    try:
        from importlib.metadata import distributions
    except ImportError:  # pragma: no cover
        return frozenset()
    for dist in distributions():
        try:
            name = dist.metadata["Name"]
        except Exception:  # noqa: BLE001 - malformed metadata raises many types
            continue
        if name:
            key = canonical(name)
            seen[key] = seen.get(key, 0) + 1
    return frozenset(k for k, n in seen.items() if n > 1)


def installed_versions(names: Iterable[str], python: Path | None = None) -> dict[str, str]:
    """Version of each named distribution installed in the target environment.

    Without *python* this reads the interpreter running the check, which is the
    only thing it could do before #17449 -- and is why no DEPLOYED service venv
    had ever been checked, despite that being the only environment serving
    traffic. One was found below its own declared floor the first time anyone
    looked.

    With *python* it asks that interpreter instead, over a script that imports
    nothing from this repository, so a deployed venv can be audited without the
    repo being present or importable there. Every comparison downstream is
    unchanged: this function is the whole seam.
    """
    wanted = sorted(set(names))
    if python is None:
        found: dict[str, str] = {}
        for name in wanted:
            try:
                found[name] = version(name) or UNREADABLE
            except PackageNotFoundError:
                continue
            except Exception:  # noqa: BLE001 - malformed metadata raises many types
                found[name] = UNREADABLE
        # Hoisted: each call scans EVERY installed distribution, so calling it
        # per name made one audit do N+1 full metadata scans (#17502 review).
        duplicates = duplicate_metadata_names()
        if duplicates:
            for name in wanted:
                if canonical(name) in duplicates:
                    found[name] = UNREADABLE
        return found
    _, versions, duplicates = _remote_versions(wanted, python)
    return {name: (UNREADABLE if (not raw or canonical(name) in duplicates) else raw) for name, raw in versions.items()}


def _remote_versions(names: Sequence[str], python: Path) -> tuple[str, dict[str, str], frozenset[str]]:
    """``(interpreter version, {name: version})`` from *python*.

    Raises rather than returning empty: an interpreter that could not be read
    and one with nothing installed are the same value to every caller
    downstream, and reporting the first as a clean environment is the exact
    failure this module exists to prevent.
    """
    if not python.is_file():
        raise InterpreterUnreadable(f"{python} is not a file")
    try:
        completed = subprocess.run(
            [str(python), "-c", _probe_source()],
            input=json.dumps(list(names)),
            capture_output=True,
            text=True,
            timeout=_PROBE_TIMEOUT,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        # Not an OSError, so the clause below never caught it: a hung target
        # ended the run with a traceback instead of the documented FATAL + exit
        # 2. This is the same third-state argument one layer out -- a probe that
        # did not finish is "could not look", never "nothing is installed".
        raise InterpreterUnreadable(f"{python} did not answer within {_PROBE_TIMEOUT}s") from exc
    except OSError as exc:
        raise InterpreterUnreadable(f"could not run {python}: {exc}") from exc
    if completed.returncode != 0:
        raise InterpreterUnreadable(f"{python} exited {completed.returncode}: {completed.stderr.strip()[:200]}")
    try:
        payload = json.loads(completed.stdout)
    except ValueError as exc:
        raise InterpreterUnreadable(f"{python} returned unparseable output: {exc}") from exc
    try:
        return payload["v"], payload["p"], frozenset(payload.get("dup", ()))
    except (KeyError, TypeError) as exc:
        # Valid JSON of the wrong shape is still an unread environment.
        raise InterpreterUnreadable(f"{python} returned JSON without the expected keys: {exc}") from exc


def resolve_interpreter(target: Path) -> Path:
    """Accept a venv directory or an interpreter path; return the interpreter."""
    if target.is_dir():
        for candidate in (target / "bin" / "python", target / "Scripts" / "python.exe"):
            if candidate.is_file():
                return candidate
        raise InterpreterUnreadable(f"{target} is a directory with no bin/python")
    return target


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
        if have == UNREADABLE:
            # Never gated on require_present: this is not "absent", it is "the
            # check could not answer", and reporting that as satisfied is the
            # failure this module exists to prevent.
            out.append(Shortfall(declaration, UNREADABLE))
            continue
        if not satisfies(have, declaration.operator, declaration.required):
            out.append(Shortfall(declaration, have))
    return out


def audit(
    root: Path,
    roots: Sequence[str] | None = None,
    require_present: bool = False,
    python: Path | None = None,
) -> tuple[list[Shortfall], int]:
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
    names = [d.name for d in declarations]
    # Called with ONE argument on the local path, deliberately: existing callers
    # and test stubs bind `installed_versions(names)`, and #17449 is an added
    # capability rather than a changed contract. Only the --venv path passes a
    # second argument, and only that path is new.
    installed = installed_versions(names) if python is None else installed_versions(names, python)
    return shortfalls(declarations, installed, require_present), len(declarations)


def render(
    found: Sequence[Shortfall],
    examined: int,
    limit: int = MAX_REPORTED,
    *,
    in_ci: bool = False,
    environment: str | None = None,
) -> list[str]:
    """The report, one line per element; *limit* caps the per-package detail.

    *in_ci* names the reference correctly for where this prints (#16264). Off a
    developer's box, the interpreter making the report is some OTHER
    environment than the one CI installs, so the second line points there. A
    caller that IS CI -- the ``python-shard`` ``--strict`` step, or this
    plugin's own ``pytest_terminal_summary`` when ``CI`` is set -- passes
    ``in_ci=True`` instead, because the interpreter making the report there
    already IS the declared set: saying a pass "carries no information about
    CI" would be false when the box printing it is CI's own.
    """
    # #17449: name the environment beside the number. With --venv the report is
    # about an interpreter this process is NOT running in, and saying "the
    # interpreter running this check" there attributes a deployed venv's numbers
    # to the local box. Two sessions retracted conclusions from exactly that
    # confusion on one CI log; a tool that prints it is worse than a log that
    # merely allows it.
    where = environment or f"the interpreter running this check (python {platform.python_version()})"
    if not found:
        return [f"dependency floors: {examined} declarations checked against {where}, all satisfied"]
    lines = [f"{len(found)} of {examined} declared versions are NOT satisfied by {where}."]
    if in_ci:
        lines.append(
            "This IS the CI job's own environment -- these are the packages CI itself "
            "installed, below the floor it declares, not a stand-in for it."
        )
    else:
        lines.append("A pass here therefore carries no information about CI, which installs " "the declared set.")
    if environment is not None:
        del lines[1:]  # the CI-parity framing above is about a local box, not this one
        # The advice below is about reproducing CI on a developer's box. None of
        # it applies to a deployed venv, and printing it there would tell an
        # operator to fix production by running a CI-parity script.
        lines.extend(f"  {shortfall.describe()}" for shortfall in found[:limit])
        if len(found) > limit:
            # Without this the deployed report silently truncated and never said
            # so -- a list that hides entries without admitting it (#17502).
            lines.append(f"  ... and {len(found) - limit} more; re-run with --all to list them")
        lines.append(
            "This is a DEPLOYED environment, not a local or CI one: these are the versions "
            "actually serving traffic. Changing them goes through the builtin updater, never "
            "an ad-hoc pip install."
        )
        return lines
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
        "--venv",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "audit this virtualenv or interpreter instead of the one running this check "
            "(#17449) -- a venv directory or a path to a python binary"
        ),
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
    interpreter: Path | None = None
    environment: str | None = None
    if args.venv is not None:
        try:
            interpreter = resolve_interpreter(args.venv.resolve())
            environment = f"{interpreter} (python {_remote_versions((), interpreter)[0]})"
        except InterpreterUnreadable as exc:
            # Never fall back to this interpreter: answering for the wrong
            # environment is worse than not answering (#17449).
            print(f"FATAL: {exc}", file=sys.stderr)  # noqa: print
            return 2

    try:
        found, examined = audit(
            root,
            None if args.roots is None else tuple(args.roots),
            require_present=args.require_present,
            python=interpreter,
        )
    except EmptyEnumerationError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)  # noqa: print
        return 2
    # #16264: GitHub Actions (and every other major CI system) sets CI=true --
    # the same signal autobot-backend/tests/test_ocr_fallback_13896.py already
    # keys on for the same distinction.
    in_ci = bool(os.environ.get("CI"))
    for line in render(found, examined, len(found) if args.all else MAX_REPORTED, in_ci=in_ci, environment=environment):
        print(line)  # noqa: print
    # #16264: a shortfall matching KNOWN_CROSS_VENV_EXEMPTIONS is still printed
    # above (it is real, in this interpreter) but never fails --strict -- it is
    # a documented cross-venv mismatch, not drift this run should gate on.
    gating = [shortfall for shortfall in found if not is_exempt(shortfall)]
    return 1 if gating and args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
