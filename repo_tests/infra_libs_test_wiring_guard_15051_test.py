# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A tracked test module under these two roots must reach a pytest invocation (#15051).

`autobot-infrastructure/shared/tests` and `libs` were named by no `pytest.ini`
`testpaths` entry and no pytest invocation in any workflow — not `ci.yml`, not
`coverage.yml`, not `test-durations.yml`, not `marker-tests.yml`. 28 test
functions ran nowhere: 12 marker-carrying (fixed by wiring a third invocation
into `marker-tests.yml`, #13286/#15048) and the rest selected by nothing at
all, ever, because `repo_tests/marker_suite_root_coverage_test.py` only checks
the MARKED population — its own docstring says so. This is the "not only when
a marked one is" half #15051's acceptance criteria call for.

SCOPED to the two roots this issue actually fixed, not a repo-wide sweep.
`autobot-infrastructure` as a whole does not collect (pytest.ini's own comment
above the `autobot-infrastructure/shared/scripts/hooks` entry: 23 collection
errors, one of them an `INTERNALERROR`-causing `sys.exit(0)` at import time)
and is explicitly filed as separate work rather than bundled into any prior
wiring fix. A repo-wide version of this guard would fail on arrival against
that pre-existing, already-deferred debt — the same failure mode
`repo_tests/marker_suite_root_coverage_test.py`'s own restraint (marked
modules only) exists to avoid. This file is the regression guard for the
specific fix #15051 made: once wired in, `autobot-infrastructure/shared/tests`
and `libs` must STAY named by pytest.ini and by every CI invocation, marked or
not.
"""

from __future__ import annotations

import configparser
import re
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
WATCHED_ROOTS = ("autobot-infrastructure/shared/tests", "libs")

# A pytest invocation in any of this repository's spellings, plus everything on
# its continued lines — the same pattern `hook_suites_run_in_ci_test.py` uses,
# duplicated rather than imported: these are independent guards over the same
# workflow tree, and importing one from the other would make a bug in the
# shared regex invisible to whichever guard runs second.
_PYTEST_CALL = re.compile(r"(?:python[0-9.]*\s+-m\s+pytest|(?<![-\w/])pytest)((?:[^\n]*\\\n)*[^\n]*)")


def _yaml_sources() -> list[Path]:
    roots = (REPO_ROOT / ".github" / "workflows", REPO_ROOT / ".github" / "actions")
    return sorted(
        path for root in roots if root.is_dir() for pattern in ("*.yml", "*.yaml") for path in root.rglob(pattern)
    )


def _workflow_roots() -> set[str]:
    """Every path token named by every pytest invocation across the whole workflow tree.

    Unlike `hook_suites_run_in_ci_test.py`, NOT filtered to invocations naming
    `repo_tests` — `marker-tests.yml`'s third invocation, which selects only
    the marked subset of these two roots, still counts as "names the module",
    matching the issue's own framing: "no pytest invocation ... not only when a
    marked one is" is about SELECTION being marker-gated, not about which other
    paths an invocation happens to share.
    """
    found: set[str] = set()
    for source in _yaml_sources():
        text = source.read_text(encoding="utf-8")
        for match in _PYTEST_CALL.finditer(text):
            command = match.group(1).replace("\\\n", " ")
            try:
                tokens = shlex.split(command)
            except ValueError:
                tokens = command.split()
            for index, token in enumerate(tokens):
                if token.startswith("-"):
                    continue
                if index and tokens[index - 1].startswith("-"):
                    continue
                if (REPO_ROOT / token).exists():
                    found.add(token)
    return found


def _testpaths_roots() -> set[str]:
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(REPO_ROOT / "pytest.ini", encoding="utf-8")
    return {
        line.strip()
        for line in parser.get("pytest", "testpaths").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _tracked_modules_under(root: str) -> list[str]:
    listed = subprocess.run(  # nosec B603
        ["git", "ls-files", "-z", "--", f"{root}/*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [
        path
        for path in listed.split("\0")
        if path and (Path(path).name.startswith("test_") or path.endswith("_test.py"))
    ]


def test_the_scan_actually_finds_modules_under_both_roots() -> None:
    """A reach floor: a glob that stopped matching must fail loudly, not report clean over nothing."""
    for root in WATCHED_ROOTS:
        modules = _tracked_modules_under(root)
        assert len(modules) >= 1, (
            f"no tracked test module found under {root} — either the tree emptied or this "
            "scan has stopped seeing it, and either way the checks below would be vacuous"
        )
    # 5 under `autobot-infrastructure/shared/tests` (test_architecture_compliance.py,
    # test_db_initialization.py, test_distributed_system_integration.py,
    # test_performance_optimization.py, test_redis_db_ssot.py), 1 under `libs`
    # (libs/autobot-sdk-python/tests/test_integration.py) — measured, not guessed.
    total = sum(len(_tracked_modules_under(root)) for root in WATCHED_ROOTS)
    assert total >= 5, f"only {total} tracked test modules found under {WATCHED_ROOTS} — expected at least 5"


def test_pytest_ini_names_both_roots() -> None:
    """`testpaths` is what a bare local `pytest` and several CI jobs use."""
    testpaths = _testpaths_roots()
    missing = [root for root in WATCHED_ROOTS if root not in testpaths]
    assert not missing, (
        f"{missing} left pytest.ini's testpaths — a bare local `pytest` no longer reaches "
        "them (#15051)"
    )


def test_every_module_under_both_roots_is_named_by_some_pytest_invocation() -> None:
    """Every module under these roots must be reachable, marked or not (#15051).

    `repo_tests/marker_suite_root_coverage_test.py` already guards the MARKED
    population against exactly this drift. This is the unmarked half: a module
    here that no invocation names at all — not `pytest.ini`, not any workflow —
    runs nowhere, which is the defect #15051 fixed and this exists to keep fixed.
    """
    covered_roots = _testpaths_roots() | _workflow_roots()
    orphans = []
    for root in WATCHED_ROOTS:
        for module in _tracked_modules_under(root):
            if not any(module == covered or module.startswith(f"{covered.rstrip('/')}/") for covered in covered_roots):
                orphans.append(module)
    assert not orphans, (
        "these tracked test modules are named by no pytest invocation anywhere — not "
        "pytest.ini's testpaths, not any CI workflow (#15051):\n  " + "\n  ".join(sorted(orphans))
    )


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
