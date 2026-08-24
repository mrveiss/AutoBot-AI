# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-commit hook suites must actually be collected, and by CI (#14884).

#14884 was filed as "8 tests cannot run". Fixing the two harness defects made
them pass *when invoked by hand* — and that is where it would have stopped,
because nothing collects them. `pytest.ini`'s `testpaths` did not list
`autobot-infrastructure`, none of the three CI pytest invocations named it, and
`autobot-infrastructure/shared/tests/pytest.ini` sets
`testpaths = unit integration e2e`, which does not reach `shared/scripts/`. The
18 suites under `shared/scripts/hooks/` — the only tests of the hooks
themselves — were collected by nothing at all.

That is the same "absent reads as clean" shape as the bug being fixed, one
level up: the fail-closed proof for `git worktree list`, and the supply-chain
check on tag-pinned third-party actions, would each have been verified exactly
once, by hand, in the PR that claimed to restore them.

Two independent halves, because either alone can pass while the wiring is
broken:

* **configuration** — the path is in `pytest.ini` and in every CI invocation
  that runs this family of tests. Derived by scanning the workflows for
  `python -m pytest`, not from a list of three filenames, so a fourth workflow
  added later with the same omission fails here too.
* **behaviour** — pytest, configured by this repository's own `pytest.ini`,
  really does collect them. A path present in a config it then ignores is
  worth nothing, and only running the collector can tell the difference.
"""

from __future__ import annotations

import configparser
import re
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOKS_REL = "autobot-infrastructure/shared/scripts/hooks"
_HOOKS_DIR = _REPO_ROOT / _HOOKS_REL
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# A `python -m pytest` command and everything on its continued lines.
_PYTEST_CALL = re.compile(r"python -m pytest((?:[^\n]*\\\n)*[^\n]*)")

# Tests that must survive to the end of the collection, named individually.
# #14884's two suites, so a sweep that reaches the directory but drops these
# still fails.
_REQUIRED_MODULES = (
    "pre-commit-worktree-branch-guard_test.py",
    "pre-commit-no-tag-pinned-action_test.py",
)


def _pytest_invocations() -> list[tuple[str, list[str]]]:
    """Every `python -m pytest` in the workflows, as (workflow, argv tokens)."""
    found: list[tuple[str, list[str]]] = []
    for workflow in sorted(_WORKFLOWS.glob("*.yml")):
        text = workflow.read_text(encoding="utf-8")
        for match in _PYTEST_CALL.finditer(text):
            tokens = match.group(1).replace("\\\n", " ").split()
            found.append((workflow.name, tokens))
    return found


def test_the_hook_suites_exist_to_be_collected() -> None:
    """Presence floor. An empty directory makes every check below vacuous."""
    assert _HOOKS_DIR.is_dir(), f"{_HOOKS_REL} does not exist — no subject"
    modules = sorted(path.name for path in _HOOKS_DIR.rglob("*_test.py"))
    assert len(modules) >= 18, f"only {len(modules)} hook test modules found"
    for name in _REQUIRED_MODULES:
        assert name in modules, f"{name} is gone — #14884's subject vanished"


def test_pytest_testpaths_lists_the_hook_suites() -> None:
    """A bare `pytest` at the repo root must reach them (#14884).

    `testpaths` is what a developer's local run and several CI jobs use; a path
    missing from it is skipped in silence, which is how #13368, #13879 and
    #13880 each hid a red test for months.
    """
    parser = configparser.ConfigParser(inline_comment_prefixes=("#",))
    parser.read(_REPO_ROOT / "pytest.ini", encoding="utf-8")
    assert parser.has_option("pytest", "testpaths"), (
        "pytest.ini no longer declares testpaths"
    )
    # Parsed, not split on the first occurrence of the word: `testpaths` also
    # appears inside the #13084 comment above the option, and a naive split
    # picks that up and reads prose as configuration.
    entries = [
        line.strip()
        for line in parser.get("pytest", "testpaths").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    assert len(entries) >= 9, f"only {len(entries)} testpaths entries — the list shrank"
    assert _HOOKS_REL in entries, (
        f"{_HOOKS_REL} is not in pytest.ini's testpaths, so the 18 hook suites "
        "are collected by nothing on a bare `pytest` run (#14884)"
    )


def test_every_ci_pytest_invocation_that_runs_repo_tests_also_runs_the_hooks() -> None:
    """Derived from the workflows, not from a list of three filenames.

    The three invocations that carry `repo_tests` are the ones that run this
    family of guard tests; each had the identical omission, and fixing one
    would have left the drift. Deriving the set means a fourth workflow added
    later with the same shape fails here rather than quietly under-running.
    """
    invocations = _pytest_invocations()
    assert len(invocations) >= 4, (
        f"only found {len(invocations)} `python -m pytest` invocations in "
        f"{_WORKFLOWS} — the scanner has regressed and this test would pass "
        "having checked nothing"
    )
    carriers = [(wf, argv) for wf, argv in invocations if "repo_tests" in argv]
    assert len(carriers) >= 3, (
        f"only {len(carriers)} invocations name repo_tests — expected at least "
        "ci.yml, coverage.yml and test-durations.yml"
    )
    offenders = sorted(
        f"{wf}: {' '.join(argv[:8])}…"
        for wf, argv in carriers
        if _HOOKS_REL not in argv
    )
    assert not offenders, (
        "these CI invocations run repo_tests but not the hook suites, so the "
        f"18 suites under {_HOOKS_REL} are collected by nothing in CI and a "
        "regression in a hook ships green (#14884):\n  " + "\n  ".join(offenders)
    )


def test_pytest_really_collects_them_under_this_repos_config() -> None:
    """The behaviour half: run the collector, do not trust the config.

    A path can be listed in `testpaths` and still collect nothing — an ignore
    rule, a `norecursedirs` entry, or a rootdir mismatch all produce "0 tests"
    with a zero exit status, which reads exactly like success. This drives the
    real collector, with this repository's own `pytest.ini`, and asserts on
    what came back.
    """
    result = subprocess.run(
        [sys.executable, "-m", "pytest", _HOOKS_REL, "--collect-only", "-q", "-p", "no:cacheprovider"],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "collecting the hook suites failed outright:\n" + result.stdout[-4000:] + result.stderr[-2000:]
    )
    collected = re.search(r"(\d+) tests? collected", result.stdout)
    assert collected, f"no collection summary in pytest's output:\n{result.stdout[-2000:]}"
    assert int(collected.group(1)) >= 159, (
        f"only {collected.group(1)} tests collected from {_HOOKS_REL} — expected "
        "at least 159; the suites are being skipped rather than run"
    )
    for name in _REQUIRED_MODULES:
        assert name in result.stdout, (
            f"{name} was not collected, so the property #14884 exists to restore "
            "is still verified by nothing"
        )
