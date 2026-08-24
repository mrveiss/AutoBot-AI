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
import shlex
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_HOOKS_REL = "autobot-infrastructure/shared/scripts/hooks"
_HOOKS_DIR = _REPO_ROOT / _HOOKS_REL
_WORKFLOWS = _REPO_ROOT / ".github" / "workflows"

# A pytest invocation in any of the spellings this repository actually uses,
# plus everything on its continued lines. Measured across the workflow tree:
# 27 bare `pytest`, 19 `python -m pytest`, 1 `python3 -m pytest`. Matching only
# the middle spelling is how the first version of this guard missed
# marker-tests.yml — a guard narrower than its own subject reads as coverage.
_PYTEST_CALL = re.compile(
    r"(?:python[0-9.]*\s+-m\s+pytest|(?<![-\w/])pytest)((?:[^\n]*\\\n)*[^\n]*)"
)

# Tests that must survive to the end of the collection, named individually.
# #14884's two suites, so a sweep that reaches the directory but drops these
# still fails.
_REQUIRED_MODULES = (
    "pre-commit-worktree-branch-guard_test.py",
    "pre-commit-no-tag-pinned-action_test.py",
)

# Markers whose presence or absence decides whether an invocation could select a
# hook test at all: the four this repository excludes from the main suite and
# selects in the marker-excluded one.
_SELECTION_MARKERS = ("integration", "slow", "distributed", "performance")


def _yaml_sources() -> list[Path]:
    """Every file that could carry a pytest invocation into CI.

    Both extensions and the composite actions, not just `workflows/*.yml`: a
    `.yaml` workflow or a composite action step is as capable of running the
    suite as anything else, and would be invisible to a narrower sweep.
    """
    roots = (_WORKFLOWS, _REPO_ROOT / ".github" / "actions")
    return sorted(
        path
        for root in roots
        if root.is_dir()
        for pattern in ("*.yml", "*.yaml")
        for path in root.rglob(pattern)
    )


def _pytest_invocations() -> list[tuple[str, list[str], str]]:
    """Every pytest invocation in CI configuration, as (file, argv, file text).

    Derived by scanning the files themselves — never from a list of workflow
    names. The list is the thing that goes stale: this guard's first version
    named the three workflows a review had identified, and there turned out to
    be a fourth.
    """
    found: list[tuple[str, list[str], str]] = []
    for source in _yaml_sources():
        text = source.read_text(encoding="utf-8")
        for match in _PYTEST_CALL.finditer(text):
            command = match.group(1).replace("\\\n", " ")
            try:
                tokens = shlex.split(command)
            except ValueError:
                # An unbalanced quote is not something to drop silently: fall
                # back to a naive split so the invocation still reaches the
                # checks rather than vanishing from the population.
                tokens = command.split()
            found.append((source.name, tokens, text))
    return found


def _marker_expression(argv: list[str], text: str) -> str | None:
    """An invocation's `-m` expression, with a shell variable resolved.

    Returns "" when there is no `-m` at all (selects everything), and None when
    the expression is a variable this cannot resolve — which is treated as a
    hard failure rather than an exemption, because "I could not tell" must never
    read the same as "it does not need the hook suites".
    """
    if "-m" not in argv:
        return ""
    index = argv.index("-m")
    if index + 1 >= len(argv):
        return None
    value = argv[index + 1].strip()
    if not value.startswith("$"):
        return value
    name = value.lstrip("$").strip("{}")
    # Resolved from the same file: `NAME: ${{ ... || 'default' }}` in an env block.
    declared = re.search(rf"^\s*{re.escape(name)}:\s*(.+)$", text, re.M)
    if not declared:
        return None
    fallback = re.search(r"\|\|\s*'([^']*)'", declared.group(1))
    return fallback.group(1) if fallback else declared.group(1).strip()


def _selects_unmarked_tests(expression: str) -> bool:
    """True when this expression can select a test that carries no marker.

    `not integration and not slow and ...` selects the unmarked set — the hook
    suites belong in it. `integration or slow or ...` selects only marked tests,
    so an invocation using it would collect the hook suites and select nothing
    from them.
    """
    return "not " in f" {expression} " or expression == ""


def _hook_tests_carrying_a_selection_marker() -> list[str]:
    """Hook tests that carry one of the markers a positive selection would pick.

    This is what earns the exemption below. It is a property of the hook suites,
    re-derived here rather than assumed, so the exemption dies the moment a hook
    test gains an `integration` or `slow` marker.
    """
    marked: list[str] = []
    pattern = re.compile(r"@pytest\.mark\.(" + "|".join(_SELECTION_MARKERS) + r")\b")
    for module in sorted(_HOOKS_DIR.rglob("*_test.py")):
        for lineno, line in enumerate(module.read_text(encoding="utf-8").splitlines(), 1):
            if pattern.search(line):
                marked.append(f"{module.name}:{lineno}")
    return marked


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
    sources = _yaml_sources()
    assert len(sources) >= 55, f"only {len(sources)} CI yaml files found — the sweep broke"
    invocations = _pytest_invocations()
    assert len(invocations) >= 40, (
        f"only found {len(invocations)} pytest invocations across {len(sources)} CI "
        "files — the scanner has regressed and this test would pass having checked "
        "nothing (measured: 64)"
    )
    # `repo_tests` as a bare path token, so `-p repo_tests.stable_shard` is not
    # mistaken for a path. Measured: exactly 4 carriers.
    carriers = [(wf, argv, text) for wf, argv, text in invocations if "repo_tests" in argv]
    assert len(carriers) >= 4, (
        f"only {len(carriers)} invocations name repo_tests as a path — expected 4; "
        "either one was removed or the argv splitter has regressed"
    )

    # An invocation needs the hook suites only if it can SELECT them. Split by
    # each invocation's own `-m` expression rather than by filename:
    # marker-tests.yml selects `integration or slow or distributed or
    # performance`, and no hook test carries any of those, so adding the path
    # there would collect 18 modules and select nothing from them.
    unresolved = [wf for wf, argv, text in carriers if _marker_expression(argv, text) is None]
    assert not unresolved, (
        "could not resolve the -m expression for these invocations, so whether "
        f"they select the hook suites is unknown: {unresolved}. Unknown is not an "
        "exemption — resolve it or name the expression literally"
    )
    selecting = [
        (wf, argv) for wf, argv, text in carriers
        if _selects_unmarked_tests(_marker_expression(argv, text) or "")
    ]
    marker_only = [wf for wf, argv, text in carriers if (wf, argv) not in selecting]
    assert len(selecting) >= 3, (
        f"only {len(selecting)} carriers select the unmarked set — expected at least "
        "ci.yml, coverage.yml and test-durations.yml"
    )
    assert marker_only, (
        "no carrier is marker-only, so the branch that exempts one is untested — "
        "marker-tests.yml should be here"
    )

    # The exemption is EARNED, not asserted: it holds only while no hook test
    # carries a marker a positive selection would pick up.
    marked = _hook_tests_carrying_a_selection_marker()
    assert not marked, (
        "these hook tests now carry a selection marker, so the marker-only "
        f"invocations {marker_only} would select them and must name the hook "
        f"suites after all: {marked}"
    )

    offenders = sorted(
        f"{wf}: {' '.join(argv[:8])}…"
        for wf, argv in selecting
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


def _root_paths(argv: list[str]) -> list[str]:
    """The test roots an invocation names, in order.

    A bare token that exists as a path in the repository, and is not the value
    of the option before it — `--shard-durations .test_durations` names a file
    that exists and is emphatically not a test root, so a naive "does it exist"
    filter reads a durations file as a fourth tree.
    """
    return [
        token
        for index, token in enumerate(argv)
        if not token.startswith("-")
        and not (index and argv[index - 1].startswith("-"))
        and (_REPO_ROOT / token).exists()
    ]


def test_every_ci_invocation_carrying_repo_tests_names_the_same_roots() -> None:
    """The root lists must agree, and nothing used to check that they did (#14917).

    `tools`, `scripts` and `pipeline-scripts` were wired into ci.yml by #13368,
    #13653, #13879 and #13880 — and into none of the other three invocations.
    The consequences were invisible in exactly the way this repository keeps
    being bitten by: their lines counted toward no coverage gate, they had no
    entries in `.test_durations` so the shard balancer placed them by hash with
    zero weight, and `scripts/check_script_exec_bits_test.py`'s
    `@pytest.mark.integration` case was selected by *nothing at all* — ci.yml,
    coverage.yml and test-durations.yml all deselect that marker, and
    marker-tests.yml, which selects it, did not name the tree it lives in.

    Comparing the four sets to each other rather than to a hard-coded list is
    the point: a fifth invocation added later is checked on arrival, and no
    entry here goes stale when a tree is renamed.
    """
    carriers = [
        (workflow, _root_paths(argv))
        for workflow, argv, _ in _pytest_invocations()
        if "repo_tests" in argv
    ]
    assert len(carriers) >= 4, (
        f"only {len(carriers)} invocations name repo_tests as a path — expected at "
        "least 4 (ci, coverage, test-durations, marker-tests); either one was "
        "removed or the argv splitter has regressed and this test checks nothing"
    )
    roots = {workflow: tuple(paths) for workflow, paths in carriers}
    sizes = {len(paths) for paths in roots.values()}
    assert sizes and min(sizes) >= 8, (
        f"a carrier names only {min(sizes)} test roots — the shared root list has "
        f"shrunk or stopped being recognised: {roots}"
    )
    distinct = {frozenset(paths) for paths in roots.values()}
    assert len(distinct) == 1, (
        "these CI pytest invocations disagree about which trees they run, so a "
        "tree is counted by one job and invisible to another (#14917):\n  "
        + "\n  ".join(f"{workflow}: {sorted(paths)}" for workflow, paths in sorted(roots.items()))
    )


def test_marker_selected_tests_exist_in_every_shared_root() -> None:
    """The shared root list is not cosmetic — a marked test lives outside the core trees.

    This is the property that made the drift a correctness hole rather than a
    reporting one, and it is re-derived rather than asserted: if every marked
    test moved back into `autobot-backend`, this fails and says so instead of
    quietly protecting nothing.
    """
    pattern = re.compile(r"@pytest\.mark\.(" + "|".join(_SELECTION_MARKERS) + r")\b")
    outside = [
        str(module.relative_to(_REPO_ROOT))
        for tree in ("tools", "scripts", "pipeline-scripts")
        for module in sorted((_REPO_ROOT / tree).rglob("*_test.py"))
        if pattern.search(module.read_text(encoding="utf-8"))
    ]
    assert outside, (
        "no test under tools/, scripts/ or pipeline-scripts/ carries a selection "
        "marker any more. The root-set agreement above is then only a coverage and "
        "shard-weighting property — re-derive whether it still needs asserting "
        "rather than leaving a floor that guards nothing (#14917)"
    )
