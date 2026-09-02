# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A blanket module-level skip must say what is parked and which issue lifts it (#15488).

A module-level ``pytestmark = pytest.mark.skip(...)`` silences an entire file.
At a glance that is indistinguishable from a file that passes -- the suite reports
green and asserts nothing, the same shape as #15018 (an enumeration matching zero
files) and #15161 (a conftest that makes a directory collect nothing).

Found while closing #15173, where `api_endpoint_migrations_test.py` had been
skipped wholesale since #5359 with no record of what coverage was parked. The
decision to park it was legitimate; the absence of a record was not.

Scope is deliberately narrow: **unconditional** skips only. A ``skipif`` with a
real condition is a different thing -- it runs when the condition allows, and
its reason names an environment rather than a debt. Those are not counted.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from autobot_shared.paths import git_repo_root

REPO = git_repo_root()

# Every blanket skip in base, with the issue that would lift it. THIS ONLY SHRINKS.
# Never add an entry to make a new skip pass -- record the reason on the skip instead.
KNOWN_BLANKET_SKIPS = {
    "autobot-backend/api/api_endpoint_migrations_test.py": "15173",
}

# A sweep that matches nothing must fail by name rather than read as a clean tree
# (#15018). This is the count of test modules the sweep parses, not of skips.
_MIN_TEST_MODULES = 1800

_ISSUE = re.compile(r"#(\d{3,6})")


def _test_files() -> list[Path]:
    """Tracked test modules, by the same two patterns pytest collects.

    #14484: the exclusion is checked on the path RELATIVE to the repo root. An
    absolute check neuters the sweep when the checkout is itself a worktree under
    ``.worktrees/``, because every path then contains that segment -- which is how
    this guard first scored 0 modules and was caught only by the population floor.
    """
    out: list[Path] = []
    for pattern in ("*_test.py", "test_*.py"):
        for path in REPO.rglob(pattern):
            if ".worktrees" not in path.relative_to(REPO).parts:
                out.append(path)
    return out


def _blanket_skip_reason(tree: ast.AST) -> str | None:
    """The reason of a module-level unconditional ``pytest.mark.skip``, if any.

    Returns None when the module has no blanket skip. Returns "" when it has one
    whose reason is missing or empty -- the case this guard exists to catch.
    """
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets):
            continue
        call = node.value
        if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Attribute):
            continue
        if call.func.attr != "skip":  # skipif is conditional, and out of scope
            continue
        for kw in call.keywords:
            if kw.arg == "reason" and isinstance(kw.value, ast.Constant):
                return str(kw.value.value)
        return ""
    return None


def _scan() -> tuple[dict[str, str], int]:
    """(relative path -> reason) for every blanket skip, and the modules parsed."""
    found, parsed = {}, 0
    for path in _test_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        parsed += 1
        reason = _blanket_skip_reason(tree)
        if reason is not None:
            found[path.relative_to(REPO).as_posix()] = reason
    return found, parsed


def test_the_sweep_reaches_enough_modules_to_mean_anything() -> None:
    """Defined before every other check: an empty sweep must not read as clean."""
    _, parsed = _scan()
    assert parsed >= _MIN_TEST_MODULES, (
        f"the sweep parsed only {parsed} test modules, under the recorded floor of "
        f"{_MIN_TEST_MODULES}. FIX THE SWEEP -- a guard that matches nothing passes "
        f"everything, which is the defect this file exists to catch."
    )


def test_every_blanket_skip_names_the_issue_that_would_lift_it() -> None:
    found, _ = _scan()
    undocumented = {
        path: reason for path, reason in found.items() if not _ISSUE.search(reason or "")
    }
    assert not undocumented, (
        "these files are skipped wholesale, which is indistinguishable from passing, "
        "and their skip reason names no issue that would lift it. State what coverage "
        "is parked and the issue number:\n  "
        + "\n  ".join(f"{p} (reason: {r!r})" for p, r in sorted(undocumented.items()))
    )


def test_the_blanket_skip_population_only_ever_shrinks() -> None:
    found, _ = _scan()
    added = sorted(set(found) - set(KNOWN_BLANKET_SKIPS))
    assert not added, (
        "new blanket module-level skip(s) -- a whole file silenced reads as green.\n  "
        + "\n  ".join(added)
        + "\nPark individual tests with their own reason, or record why the file "
        "cannot run. Do not add an entry to KNOWN_BLANKET_SKIPS to make this pass."
    )


def test_known_entries_are_still_live() -> None:
    """A resolved entry must be deleted, so the map cannot rot into a wish list."""
    found, _ = _scan()
    stale = sorted(set(KNOWN_BLANKET_SKIPS) - set(found))
    assert not stale, (
        "these files no longer carry a blanket skip -- remove them from "
        f"KNOWN_BLANKET_SKIPS: {stale}"
    )
