#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15070 — a package declared in both requirements files must carry ONE specifier.

``autobot-backend/requirements.txt`` carries ``-r ../requirements.txt``, so the
root file is *included* by the backend file. Four packages (protobuf,
aiosqlite, defusedxml, python-docx) are nonetheless declared in both. pip
resolves a doubly-declared package against the **intersection** of the two
specifiers, so the pair is safe only while they agree:

* agreeing — the duplicate is redundant and harmless;
* diverging with an overlap (``>=7.36,<8`` vs ``>=7.0,<8``) — the effective
  constraint silently becomes the tighter one, which no single line states;
* diverging with no overlap (``>=7.36,<8`` vs ``<7.0``) — ResolutionImpossible,
  and the traceback names neither file.

#15070 is the near miss: the root file's protobuf line carried a rationale
saying the cap was ``<7.0`` and that a 7.x floor was unsatisfiable, while the
line it annotated said ``>=7.36.0,<8.0.0``. The verbatim-duplicated note in
``autobot-backend/requirements.txt`` said the same. A maintainer trusting the
note over the constraint would have edited one file back to ``<7.0`` — the
no-overlap case — and nothing in the repo would have objected until a deploy.

WHY THIS IS A SCRIPT AND NOT ONLY A TEST. The failure direction is the one that
needs a REQUIRED check (the same argument as ``check_requirements_ci_drift.py``
and ``check_python_file_size.py``): every way of weakening this guard makes it
report FEWER problems. A file renamed or emptied parses to zero packages and
the comparison passes vacuously; deduplicating the last shared package empties
the overlap and the guard then asserts nothing at all. Both are hard errors
here rather than a clean run over nothing — the #15087 shape, where a check
over an enumeration passed because the enumeration was empty.

``repo_tests/requirements_pin_parity_test.py`` imports these functions rather
than restating the rule, so there is one definition of "parity".
"""

from __future__ import annotations

import argparse
import logging
import pathlib
import re
import sys

# Plain stdlib logging, deliberately (#1082, matching check_requirements_ci_drift.py
# and check_python_file_size.py): this runs inside `code-quality`, which installs
# linters only — never the application's own dependencies — so
# `autobot_shared.logging_manager` is not importable here.
logger = logging.getLogger(__name__)

#: The two files that declare the same packages. Order is (root, backend) and
#: is reported that way; the backend file `-r`-includes the root one.
_ROOT_REQUIREMENTS = "requirements.txt"
_BACKEND_REQUIREMENTS = "autobot-backend/requirements.txt"

#: Every repo-relative path this checker reads. code-quality.yml's
#: dorny/paths-filter `backend` list must cover each of these, or a PR that
#: touches only one of them skips the required check entirely — verified by
#: tools/lint/check_code_quality_guard_reach.py.
GUARD_INPUT_PATHS = (_ROOT_REQUIREMENTS, _BACKEND_REQUIREMENTS)

_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[2]


def _normalize(name: str) -> str:
    """PEP 503 style normalisation so `python_docx` and `python-docx` match."""
    return re.sub(r"[-_.]+", "-", name).lower()


def parse_direct_requirements(path: pathlib.Path) -> dict[str, str]:
    """``{normalized_name: specifier}`` for the declarations written IN this file.

    Deliberately does NOT follow ``-r`` includes, which is what separates it
    from ``check_requirements_ci_drift.parse_requirements``: that one answers
    "what does this file resolve to" and merges an include's declarations in
    last-wins, which would fold the root file's protobuf line onto the backend
    file's and hide the very divergence this guard exists to find. This one
    answers "what does this file itself say".

    The specifier is everything after the package name with whitespace and the
    trailing comment stripped, so ``protobuf>=7.36.0,<8.0.0   # note`` and
    ``protobuf >= 7.36.0, <8.0.0`` compare equal — the guard is about the
    resolved constraint, not about formatting.
    """
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        match = _NAME_RE.match(line)
        if match:
            out[_normalize(match.group(1))] = line[match.end() :].replace(" ", "")
    return out


def compute_divergence(root: dict[str, str], backend: dict[str, str]) -> list[str]:
    """Names declared in both mappings whose specifiers differ, sorted."""
    return sorted(name for name in set(root) & set(backend) if root[name] != backend[name])


def audit_parity(base: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Apply the invariant. Returns ``(shared_packages_compared, problems)``.

    ``shared_packages_compared`` is counted from the parse, so a run that
    compared nothing cannot report itself clean.
    """
    root_dir = base if base is not None else repo_root()
    root = parse_direct_requirements(root_dir / _ROOT_REQUIREMENTS)
    backend = parse_direct_requirements(root_dir / _BACKEND_REQUIREMENTS)

    for rel, parsed in ((_ROOT_REQUIREMENTS, root), (_BACKEND_REQUIREMENTS, backend)):
        if not parsed:
            return 0, [f"{rel} parsed to zero packages — the guard checked nothing (#15070)."]

    shared = sorted(set(root) & set(backend))
    if not shared:
        return 0, [
            f"{_ROOT_REQUIREMENTS} and {_BACKEND_REQUIREMENTS} now declare no package in "
            "common, so this guard compared nothing (#15070). If that de-duplication was "
            "deliberate, delete this checker and its code-quality step in the same commit "
            "— do not leave it passing over an empty set (#15087)."
        ]

    divergent = compute_divergence(root, backend)
    if not divergent:
        return len(shared), []

    lines = "\n".join(
        f"  {name}: {_ROOT_REQUIREMENTS} {root[name]!r} vs {_BACKEND_REQUIREMENTS} {backend[name]!r}"
        for name in divergent
    )
    return len(shared), [
        f"{len(divergent)} package(s) declared in both requirements files with different "
        f"specifiers:\n{lines}\n"
        f"{_BACKEND_REQUIREMENTS} `-r`-includes {_ROOT_REQUIREMENTS}, so pip resolves the "
        "intersection: the effective constraint is one no single line states, and a "
        "non-overlapping pair fails the install outright. Make the two identical, or "
        "delete one of them (#15070)."
    ]


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def run_audit() -> int:
    compared, problems = audit_parity()
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\nrequirements pin-parity audit FAILED over %d shared package(s) (#15070).", compared)
        return 1
    logger.info("requirements pin-parity audit clean over %d shared package(s) (#15070).", compared)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="compare specifiers for packages declared in both requirements files",
    )
    args = parser.parse_args(argv)
    if not args.audit:
        parser.error("nothing to do — pass --audit")
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
