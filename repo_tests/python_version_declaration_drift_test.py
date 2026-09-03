# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Python interpreter minor has ONE source of truth: `.python-version` (#13842).

This guard originally swept 31 independently-restated literals across seven
families and asserted they agreed with `.python-version` -- a *check*, not a
*derivation*, and its own docstring said so explicitly: "Making the sites read
`.python-version` is a separate design decision... That call is not made
here."

That call has now been made, for five of the seven families:

* 13 workflows' `python-version: 'X.Y'` and two composite actions'
  equivalent now read `python-version-file: '.python-version'` instead of
  restating the value -- `actions/setup-python` supports it directly.
* `.github/actions/setup-python-ci/action.yml`'s input default is empty; its
  own "Resolve Python version" step falls back to `.python-version`.
* The five Ansible `python_interpreter_version` literals are gone; only
  `roles/python_interpreter/defaults/main.yml` and `tasks/main.yml` remain,
  and they derive the value via `lookup('file', ...)` + `set_fact` rather
  than declaring it (`role_path` is only valid in-task, which is why it is a
  `set_fact` and not a lazy `defaults:` entry -- see that file).
* `docker/backend/Dockerfile` now takes `ARG PYTHON_VERSION` exactly the way
  `docker/slm/Dockerfile` already did, instead of hardcoding `python:3.14-`
  three times -- the two are now ONE sweep below, not two.
* `autobot-backend/startup_validator.py`'s runtime floor is read from
  `.python-version` directly (`_minimum_python_version`), not hardcoded --
  this is the site that drifted before (PR #13750) and the one a reader
  trusts most, being the only floor a running process enforces.

Derivation removes the *possibility* of drift for those five; a `Sweep`
comparing two numbers cannot fail once there is only one number left to read.
What replaces each retired `Sweep` is a structural test that the derivation
itself did not silently regress back into a restated literal -- proven either
by reading the source (no literal + the derivation call present) or, for
`startup_validator.py`, by calling the real function in a subprocess (isolated
so importing it here cannot leak `sys.modules` into other test files' own
conftest-swapping, which the repo's sys-modules-leak guard treats as a bug).

Two families remain genuine, independently-checked literals because TOML and
Dockerfile `ARG` defaults cannot themselves read a file:

* `pyproject.toml`'s `[tool.mypy] python_version`.
* `ARG PYTHON_VERSION=X.Y` in `docker/backend/Dockerfile` AND
  `docker/slm/Dockerfile` -- one sweep, not two, now that #13842 made the
  first file match the second's existing pattern.

**The one deliberate exclusion** is black's ``target-version = ["py312"]`` in
``pyproject.toml``. It disagrees with ``.python-version`` on purpose -- black
must not emit syntax a worker's older interpreter cannot parse -- and the
exception is written down in ``docs/audit/python_314_consistency.md``. It is
excluded by name, and ``test_the_black_target_exception_is_still_documented``
fails if the disagreement ever stops being documented, so the exclusion cannot
go quiet.

Every floor here measures the *input*, not the finding count: a sweep or scan
whose pathspec matches nothing reports clean having compared nothing, which is
the exact failure this guard is built to make impossible.
"""

from __future__ import annotations

import os
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
import sys
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
#: emits; the counts are measured, not estimated. The other five families
#: (workflow python-version, setup-python-ci's input default, ansible
#: python_interpreter_version, and startup_validator's runtime floor) no
#: longer declare a literal at all -- see the structural tests below instead.
_SWEEPS: tuple[Sweep, ...] = (
    Sweep(
        "docker ARG PYTHON_VERSION default",
        ("docker/backend/Dockerfile", "docker/slm/Dockerfile"),
        re.compile(r"ARG PYTHON_VERSION=(\d+\.\d+)"),
        min_files_swept=2,
        min_declarations=4,
    ),
    Sweep(
        "mypy python_version",
        ("pyproject.toml",),
        re.compile(r"^python_version\s*=\s*['\"](\d+\.\d+)['\"]"),
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
    """The #13842 defect: a bump that misses one site leaves the repo green and split.

    Only the two families that genuinely cannot derive (TOML, Dockerfile ARG
    defaults) are swept here now -- the other five are structurally checked
    below, where "agrees with the reference" is not the right question to ask
    of something that no longer states its own value.
    """
    reference = _reference_version()
    declarations = _all_declarations()
    assert len(declarations) >= 5, (
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


# --- Derived families (#13842) -----------------------------------------------
#
# Five of the seven original families no longer declare a literal at all -- the
# tests below assert the derivation is present and, where it is cheap to prove,
# that it actually resolves to the reference value.

_WORKFLOW_LITERAL_RE = re.compile(r"^\s*python-version:\s*['\"]?(\d+\.\d+)", re.M)
_WORKFLOW_FILE_RE_RE = re.compile(r"python-version-file:")


def test_no_workflow_or_action_restates_a_python_version_literal() -> None:
    """A reintroduced `python-version: 'X.Y'` is exactly the shape that drifted
    before -- checked as "the literal does not exist", not "it matches the
    reference", because the whole point of #13842's derivation is that there
    is no longer a second value to compare."""
    paths = _tracked((".github/workflows/*.yml", ".github/workflows/*.yaml", ".github/actions/*/action.yml"))
    assert len(paths) >= 10, "the workflow/action pathspec stopped matching anything — FIX THE SWEEP"

    offenders: list[str] = []
    file_ref_count = 0
    for rel in paths:
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        for line, version in versions_in_text(text, _WORKFLOW_LITERAL_RE):
            offenders.append(f"{rel}:{line}: python-version: '{version}'")
        file_ref_count += len(_WORKFLOW_FILE_RE_RE.findall(text))

    assert file_ref_count >= 14, (
        f"only {file_ref_count} `python-version-file:` reference(s) found across workflows/actions — "
        "FIX THE SWEEP, this no longer reaches the derivation it guards"
    )
    assert not offenders, "restated python-version literal(s) found (#13842):\n" + "\n".join(offenders)


def test_setup_python_ci_default_is_empty_not_a_restated_literal() -> None:
    """The composite action's own default must stay empty so a caller who omits
    `python-version` gets the SSOT via its "Resolve Python version" step,
    rather than a hardcoded fallback restated here."""
    path = _REPO_ROOT / ".github/actions/setup-python-ci/action.yml"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"^\s*default:\s*'([^']*)'\s*$", text, re.M)
    assert match, f"{path}: no `default:` line found for the first input — FIX THE SWEEP, wrong shape"
    assert match.group(1) == "", (
        f"{path}'s python-version input default is {match.group(1)!r}, not empty — a non-empty "
        "default restates the floor instead of deriving it from .python-version (#13842)"
    )
    assert "cat .python-version" in text, f"{path}'s resolve step no longer reads .python-version — FIX THE SWEEP"


_ANSIBLE_LITERAL_RE = re.compile(r"python_interpreter_version:\s*['\"](\d+\.\d+)['\"]")
_ROLE_DIR = "autobot-slm-backend/ansible/roles/python_interpreter/"


def test_no_ansible_file_restates_python_interpreter_version_as_a_literal() -> None:
    """Every prior literal `python_interpreter_version: "X.Y"` call-site override
    is gone; the role's own `set_fact` derivation (tasks/main.yml, anchored on
    `role_path` since `defaults:` cannot -- see that file) is what is left to
    still say a version, and that value is a Jinja lookup, not a quoted number."""
    paths = _tracked(("*/ansible/*",))
    assert len(paths) >= 100, "the ansible pathspec stopped matching anything — FIX THE SWEEP"

    offenders: list[str] = []
    for rel in paths:
        if rel.startswith(_ROLE_DIR):
            continue
        text = (_REPO_ROOT / rel).read_text(encoding="utf-8")
        for line, version in versions_in_text(text, _ANSIBLE_LITERAL_RE):
            offenders.append(f"{rel}:{line}: python_interpreter_version: '{version}'")
    assert not offenders, "python_interpreter_version restated as a literal outside the role (#13842):\n" + "\n".join(
        offenders
    )

    role_tasks = (_REPO_ROOT / _ROLE_DIR / "tasks" / "main.yml").read_text(encoding="utf-8")
    assert "lookup('file', role_path" in role_tasks and ".python-version" in role_tasks, (
        f"{_ROLE_DIR}tasks/main.yml no longer derives python_interpreter_version from .python-version — "
        "FIX THE SWEEP or the derivation itself"
    )


def test_startup_validator_derives_the_floor_at_runtime() -> None:
    """Calls the real function rather than regexing the source -- this is the
    floor #13842 says a reader trusts because it is the only one a running
    process enforces, and it is the one that silently drifted before (PR #13750).

    Run in a SUBPROCESS, not imported in-process: `startup_validator.py` pulls
    in `config.manager` / `constants.path_constants`, which stub/mock modules
    other test files' own conftests rely on staying unstubbed -- importing it
    here directly trips the repo's sys-modules-leak guard the moment this file
    runs in the same session as one of those.
    """
    source = (_REPO_ROOT / "autobot-backend/startup_validator.py").read_text(encoding="utf-8")
    assert not re.search(r"sys\.version_info\s*<\s*\(\d+,\s*\d+\)", source), (
        "startup_validator.py hardcodes a literal sys.version_info bound again — "
        "the exact PR #13750 defect #13842 exists to prevent"
    )

    env = dict(os.environ, PYTHONPATH=f"{_REPO_ROOT}:{_REPO_ROOT / 'autobot-backend'}")
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from startup_validator import _minimum_python_version; "
            "print('%d.%d' % _minimum_python_version())",
        ],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"startup_validator import/call failed: {result.stderr}"
    reported = result.stdout.strip()
    assert reported == _reference_version(), (
        f"startup_validator._minimum_python_version() returned {reported}, "
        f".python-version declares {_reference_version()!r} (#13842)"
    )
