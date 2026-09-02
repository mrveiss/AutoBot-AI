# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Python interpreter minor is declared in 22 files and nothing compared them (#13842).

``.python-version`` says ``3.14``. So do a mypy pin, a runtime floor in
``startup_validator.py``, five lines across two Dockerfiles, a composite
action's input default, 16 ``python-version:`` keys across 13 workflows, and
five Ansible ``python_interpreter_version`` values. Thirty-one declarations, no
oracle: a bump that reaches 30 of them leaves one tree building, deploying or
type-checking against a different interpreter, and every check in the repository
still reports green. Measured before this guard existed: ``python-version-file``
appears **zero** times repo-wide, and no test read ``.python-version`` at all.

**Scope, deliberately.** This is the drift *check*, not the derivation. Making
the sites read ``.python-version`` is a separate design decision -- and probably
not "rewrite 13 workflows to ``python-version-file:``", because
``.github/actions/setup-python-ci/action.yml`` already defaults the version for
its callers and its self-hosted branch resolves the interpreter from ``PATH``,
so the eventual single source is more likely that action reading the file than
13 workflows each adopting a new key. That call is not made here. What is made
here is the assertion that the declarations agree, so the drift this guard
exists to catch is caught while the derivation is settled separately.

**The one deliberate exclusion** is black's ``target-version = ["py312"]`` in
``pyproject.toml``. It disagrees with ``.python-version`` on purpose -- black
must not emit syntax a worker's older interpreter cannot parse -- and the
exception is written down in ``docs/audit/python_314_consistency.md``. It is
excluded by name, and ``test_the_black_target_exception_is_still_documented``
fails if the disagreement ever stops being documented, so the exclusion cannot
go quiet.

Every floor here measures the *input*, not the finding count: a sweep whose
pathspec matches nothing reports clean having compared nothing, which is the
exact failure this guard is built to make impossible.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from pathlib import Path
from typing import NamedTuple

import pytest

from autobot_shared.paths import scrubbed_git_env

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Excluded by path RELATIVE to the repository root, never absolute: a checkout
#: that itself lives under a directory of one of these names would otherwise
#: match every file and sweep nothing (#14484).
_SKIP_PARTS = {".git", "node_modules", "__pycache__", ".worktrees", ".claude", "venv", ".venv"}

#: The reference every other declaration is compared against.
_REFERENCE_FILE = ".python-version"


class Sweep(NamedTuple):
    """One family of declaration sites, with the floors that prove it was read."""

    label: str
    pathspecs: tuple[str, ...]
    pattern: re.Pattern[str]
    min_files_swept: int
    min_declarations: int


#: Each pattern was verified against the literal text its subject actually
#: emits; the counts are measured, not estimated. Multi-group patterns are
#: joined with ``.`` so ``sys.version_info < (3, 14)`` normalises to ``3.14``.
_SWEEPS: tuple[Sweep, ...] = (
    Sweep(
        "workflow python-version",
        (".github/workflows/*.yml", ".github/workflows/*.yaml"),
        re.compile(r"^\s*python-version:\s*['\"]?(\d+\.\d+)"),
        min_files_swept=40,
        min_declarations=16,
    ),
    Sweep(
        "setup-python-ci input default",
        (".github/actions/setup-python-ci/action.yml",),
        re.compile(r"^\s*default:\s*['\"](\d+\.\d+)['\"]"),
        min_files_swept=1,
        min_declarations=1,
    ),
    Sweep(
        "ansible python_interpreter_version",
        ("*/ansible/*",),
        re.compile(r"python_interpreter_version:\s*['\"](\d+\.\d+)['\"]"),
        min_files_swept=100,
        min_declarations=5,
    ),
    Sweep(
        "backend image interpreter",
        ("docker/backend/Dockerfile",),
        re.compile(r"python:?(\d+\.\d+)"),
        min_files_swept=1,
        min_declarations=5,
    ),
    Sweep(
        "slm image ARG default",
        ("docker/slm/Dockerfile",),
        re.compile(r"ARG PYTHON_VERSION=(\d+\.\d+)"),
        min_files_swept=1,
        min_declarations=2,
    ),
    Sweep(
        "mypy python_version",
        ("pyproject.toml",),
        re.compile(r"^python_version\s*=\s*['\"](\d+\.\d+)['\"]"),
        min_files_swept=1,
        min_declarations=1,
    ),
    Sweep(
        "startup_validator runtime floor",
        ("autobot-backend/startup_validator.py",),
        re.compile(r"sys\.version_info\s*<\s*\((\d+),\s*(\d+)\)"),
        min_files_swept=1,
        min_declarations=1,
    ),
)


class Declaration(NamedTuple):
    """One interpreter version declared at one line of one file."""

    label: str
    relative_path: str
    line: int
    version: str


def _tracked(pathspecs: tuple[str, ...]) -> list[str]:
    """Repository-relative paths matching these git pathspecs.

    ``git ls-files`` and not ``rglob``: a filesystem walk from this file's root
    picks up whatever sits beside it, and a sibling checkout's declarations
    belong to another branch.
    """
    out = subprocess.run(  # nosec B603  # fixed argv, no shell
        ["git", "-C", str(_REPO_ROOT), "ls-files", "-z", "--", *pathspecs],
        capture_output=True,
        text=True,
        check=True,
        env=scrubbed_git_env(),
    ).stdout
    return [
        rel
        for rel in out.split("\0")
        if rel and not any(part in _SKIP_PARTS for part in Path(rel).parts)
    ]


def versions_in_text(text: str, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    """``(line number, version)`` for every match, groups joined with a dot."""
    found: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        for match in pattern.finditer(line):
            found.append((number, ".".join(g for g in match.groups() if g is not None)))
    return found


def _sweep(sweep: Sweep) -> tuple[list[Declaration], int]:
    """Every declaration this sweep finds, and how many files it actually read."""
    declarations: list[Declaration] = []
    swept = 0
    for rel in _tracked(sweep.pathspecs):
        try:
            text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        swept += 1
        for line, version in versions_in_text(text, sweep.pattern):
            declarations.append(Declaration(sweep.label, rel, line, version))
    return declarations, swept


def _reference_version() -> str:
    """The interpreter minor declared by ``.python-version``."""
    path = _REPO_ROOT / _REFERENCE_FILE
    if not path.is_file():
        pytest.fail(f"{_REFERENCE_FILE} is missing — the drift check has no reference to compare against")
    return path.read_text(encoding="utf-8").strip()


def test_the_sweep_actually_reached_every_declaration_site() -> None:
    """Floors on the INPUT. A pathspec matching nothing compares nothing and passes.

    Defined before the drift test so a collapsed sweep fails here first, naming
    the family that went dark, rather than reporting a clean comparison of an
    empty set.
    """
    reference = _reference_version()
    assert re.fullmatch(r"\d+\.\d+", reference), (
        f"{_REFERENCE_FILE} holds {reference!r}, which is not a MAJOR.MINOR version — "
        "FIX THE SWEEP, every comparison below is against a value nothing can match"
    )
    for sweep in _SWEEPS:
        declarations, swept = _sweep(sweep)
        assert swept >= sweep.min_files_swept, (
            f"{sweep.label}: pathspecs {sweep.pathspecs} matched {swept} files, "
            f"floor {sweep.min_files_swept} — FIX THE SWEEP, a sweep that reads "
            "nothing reports no drift having looked at nothing"
        )
        assert len(declarations) >= sweep.min_declarations, (
            f"{sweep.label}: matched {len(declarations)} declarations across "
            f"{swept} files, floor {sweep.min_declarations} — FIX THE SWEEP, the "
            "pattern no longer matches the text these files emit"
        )


def _all_declarations() -> list[Declaration]:
    """Every interpreter declaration in the repository, across all sweeps."""
    found: list[Declaration] = []
    for sweep in _SWEEPS:
        declarations, _ = _sweep(sweep)
        found.extend(declarations)
    return found


def test_every_declared_python_version_agrees_with_the_python_version_file() -> None:
    """The #13842 defect: a bump that misses one site leaves the repo green and split."""
    reference = _reference_version()
    declarations = _all_declarations()
    assert len(declarations) >= 30, (
        f"only {len(declarations)} declarations collected — FIX THE SWEEP, "
        "this comparison would pass vacuously"
    )
    drifted = [
        f"{d.relative_path}:{d.line}  declares {d.version}  ({d.label})"
        for d in declarations
        if d.version != reference
    ]
    assert not drifted, (
        f"these declare a Python interpreter version other than the {reference} in "
        f"{_REFERENCE_FILE}. Every one of them is a tree that builds, deploys or "
        "type-checks against a different interpreter than the rest of the "
        "repository, with no check anywhere that would notice (#13842):\n  "
        + "\n  ".join(drifted)
    )


def test_the_black_target_exception_is_still_documented() -> None:
    """The single deliberate exclusion, excluded by name rather than silently.

    black's ``target-version`` is allowed to lag ``.python-version`` — it must
    not emit syntax an older worker interpreter cannot parse. The exception is
    only legitimate while it is written down; if the disagreement outlives its
    audit entry, that is drift wearing an exception's clothes.
    """
    pyproject = (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r"^target-version\s*=\s*\[\"py(\d)(\d+)\"\]", pyproject, re.M)
    assert match is not None, "black target-version is gone from pyproject.toml — the exclusion is stale"
    target = f"{match.group(1)}.{match.group(2)}"
    if target == _reference_version():
        return
    audit = _REPO_ROOT / "docs/audit/python_314_consistency.md"
    assert audit.is_file(), (
        f"black targets py{match.group(1)}{match.group(2)} against a "
        f"{_reference_version()} repository and {audit.name} no longer exists to justify it"
    )
    text = audit.read_text(encoding="utf-8")
    assert f"py{match.group(1)}{match.group(2)}" in text and "exception" in text.lower(), (
        f"black targets py{match.group(1)}{match.group(2)} while {_REFERENCE_FILE} says "
        f"{_reference_version()}, and that exception is no longer recorded in {audit.name}"
    )


_SYNTHETIC = "3.9"


@pytest.mark.parametrize(
    "sweep",
    _SWEEPS,
    ids=[s.label.replace(" ", "_") for s in _SWEEPS],
)
def test_the_detector_still_fires_on_a_drifting_declaration(sweep: Sweep) -> None:
    """Positive control per family: a planted disagreement must be extracted.

    A guard is only worth its floors if the pattern still matches the shape its
    subject emits. Each control rewrites a real matching line to the synthetic
    version and asserts the extractor reports it.
    """
    declarations, _ = _sweep(sweep)
    assert declarations, f"{sweep.label} matched nothing — cannot build a control"
    sample = declarations[0]
    text = (_REPO_ROOT / sample.relative_path).read_text(encoding="utf-8")
    line = text.splitlines()[sample.line - 1]
    planted = line.replace(sample.version, _SYNTHETIC).replace(
        sample.version.replace(".", ", "), _SYNTHETIC.replace(".", ", ")
    )
    extracted = versions_in_text(planted, sweep.pattern)
    assert extracted and extracted[0][1] == _SYNTHETIC, (
        f"{sweep.label}: planting {_SYNTHETIC} into {sample.relative_path}:{sample.line} "
        f"produced {extracted!r} — the pattern does not match what this file emits"
    )
