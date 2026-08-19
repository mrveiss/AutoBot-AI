#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#14550/#14551 — a required check that never triggers is satisfied, not failed.

``code-quality`` only does real work when its ``changes`` job's
``dorny/paths-filter`` reports a ``backend`` path touched — otherwise the
``code-quality`` job itself is skipped, and GitHub branch protection treats a
**skipped** required job the same as a **passing** one. #14550 and #14551
added two guards (``check_requirements_ci_drift.py``,
``check_ci_system_package_provisioning.py``) whose own input files —
``autobot-slm-backend/ansible/roles/backend/tasks/main.yml`` and
``.github/actions/setup-python-suite/action.yml`` — were not covered by that
filter at the time: a PR touching only one of them (say, deleting the
``ffmpeg`` apt line #14550 just added) matched no filter entry, so
``code-quality`` skipped, both ``--audit`` steps never ran, and the guard
could not fire on the exact change it exists to catch.

This is that failure shape one layer up: a guard whose *reach* is narrower
than the thing it claims to cover reads as coverage while providing none. So
each guard now declares its own ``GUARD_INPUT_PATHS`` (the checker's single
source of truth for what it reads), and this module re-derives the filter's
actual reach from ``.github/workflows/code-quality.yml`` and asserts every
guarded path is covered by it.

WHY THIS IS A SCRIPT AND NOT ONLY A TEST. The failure direction needs a
REQUIRED check for the same reason as its siblings: removing a path filter
entry, or forgetting to add one for a new guard input, makes this scan find
FEWER uncovered paths and go GREENER. ``.github/workflows/code-quality.yml``
itself is always in scope (it is a filter entry in its own right), so this
check runs on any edit to the filter. ``repo_tests/code_quality_guard_reach_test.py``
imports these functions rather than restating the rule.
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
import pathlib
import re
import sys

# Plain stdlib logging (matching every other tools/lint/check_*.py in this
# repo): this runs inside `code-quality`, which installs linters only, never
# the application's own dependencies -- so no third-party YAML parser here.
logger = logging.getLogger(__name__)

_WORKFLOW = ".github/workflows/code-quality.yml"

#: Checkers whose GUARD_INPUT_PATHS this meta-guard enforces. Add a new entry
#: here whenever a new required-check script gains its own GUARD_INPUT_PATHS.
_GUARDED_CHECKERS = (
    "tools/lint/check_requirements_ci_drift.py",
    "tools/lint/check_ci_system_package_provisioning.py",
    "tools/lint/check_composite_action_step_keys.py",
)

_FILTER_BULLET_RE = re.compile(r"^\s*-\s*'([^']+)'\s*$")


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[2]


def _load_module(root: pathlib.Path, rel_path: str):
    spec = importlib.util.spec_from_file_location(rel_path.replace("/", "_"), root / rel_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def guarded_input_paths(root: pathlib.Path | None = None) -> dict[str, tuple[str, ...]]:
    """``{checker_path: its GUARD_INPUT_PATHS}`` for every checker in scope."""
    base = root if root is not None else repo_root()
    result: dict[str, tuple[str, ...]] = {}
    for rel_path in _GUARDED_CHECKERS:
        if not (base / rel_path).is_file():
            continue
        module = _load_module(base, rel_path)
        result[rel_path] = tuple(getattr(module, "GUARD_INPUT_PATHS", ()))
    return result


def backend_filter_patterns(root: pathlib.Path | None = None) -> list[str]:
    """The dorny/paths-filter ``backend`` bullet list, parsed without a YAML lib.

    ``configparser``/stdlib ``tomllib`` cannot read a YAML file, and
    ``code-quality`` installs no third-party YAML parser, so this reads the
    literal ``filters: |`` block by locating it explicitly rather than
    trusting the first ``backend:`` in the file — ``outputs: backend: ...``
    two lines above the real filter list would otherwise match first.
    """
    base = root if root is not None else repo_root()
    path = base / _WORKFLOW
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8")
    filters_idx = text.find("filters: |")
    if filters_idx == -1:
        return []
    backend_idx = text.find("backend:", filters_idx)
    if backend_idx == -1:
        return []
    patterns: list[str] = []
    for line in text[backend_idx:].splitlines()[1:]:
        match = _FILTER_BULLET_RE.match(line)
        if match:
            patterns.append(match.group(1))
        elif patterns:
            break  # first non-bullet line after the list ends the block
    return patterns


def _pattern_regex(pattern: str) -> re.Pattern[str]:
    """Translate a dorny/paths-filter glob (`**`, `*`) to a regex, anchored.

    `**/` becomes an OPTIONAL `(.*/)?`, not a bare `.*/`: gitignore-style
    matching lets `**/foo` match a root-level `foo` with zero path segments,
    and a bare `.*/`  would demand a literal `/` that a top-level file (e.g.
    `requirements-ci.txt` against `**/requirements*.txt`) does not have --
    which would report a covered path as uncovered.
    """
    escaped = re.escape(pattern)
    escaped = escaped.replace(r"\*\*/", "(?:.*/)?")
    escaped = escaped.replace(r"\*\*", ".*")
    escaped = escaped.replace(r"\*", "[^/]*")
    return re.compile(escaped + r"$")


def uncovered_paths(guarded: dict[str, tuple[str, ...]], patterns: list[str]) -> dict[str, list[str]]:
    """Guarded paths matched by NO filter pattern, grouped by owning checker."""
    compiled = [_pattern_regex(p) for p in patterns]
    result: dict[str, list[str]] = {}
    for checker, paths in guarded.items():
        misses = [p for p in paths if not any(rx.search(p) for rx in compiled)]
        if misses:
            result[checker] = misses
    return result


def audit_reach(root: pathlib.Path | None = None) -> tuple[int, list[str]]:
    """Apply the invariant. Returns ``(guarded_paths_checked, problems)``."""
    base = root if root is not None else repo_root()
    problems: list[str] = []

    guarded = guarded_input_paths(base)
    total = sum(len(v) for v in guarded.values())
    if total == 0:
        return 0, ["no GUARD_INPUT_PATHS found on any tracked checker — the guard checked nothing."]

    patterns = backend_filter_patterns(base)
    if not patterns:
        return total, [f"{_WORKFLOW} parsed to zero `backend` filter patterns — the guard checked nothing."]

    missed = uncovered_paths(guarded, patterns)
    if missed:
        for checker, paths in missed.items():
            problems.append(
                f"{checker} reads {paths}, none of which is covered by {_WORKFLOW}'s "
                "`backend` path filter — a PR touching only that path skips the "
                "`code-quality` job entirely, and a skipped required job satisfies "
                "branch protection. Add a matching entry to both the `on.push.paths` "
                "list and the `changes` job's `filters.backend` list."
            )

    return total, problems


def configure_logging() -> None:
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)


def run_audit() -> int:
    reached, problems = audit_reach()
    if problems:
        logger.error("%s", "\n\n".join(problems))
        logger.error("\ncode-quality guard-reach audit FAILED over %d guarded path(s) (#14550/#14551).", reached)
        return 1
    logger.info("code-quality guard-reach audit clean over %d guarded path(s) (#14550/#14551).", reached)
    return 0


def main(argv: list[str]) -> int:
    configure_logging()
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--audit",
        action="store_true",
        help="verify the code-quality path filter covers every guarded checker's inputs",
    )
    args = parser.parse_args(argv)
    if not args.audit:
        parser.error("nothing to do — pass --audit")
    return run_audit()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
