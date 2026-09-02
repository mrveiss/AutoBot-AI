# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every test file must be accounted for by some runner (#13653).

`ci.yml` collects a hand-curated list of directories. Nothing checked that the
list covered the repository, so whole trees fell out of CI silently:

* `scripts/` — seven suites guarding the pre-commit checkers, run by nothing
  until #13660.
* `scripts/lib/*_test.sh` — including the #10035 branch-deletion regression
  suite, never executed by anything until `repo_tests/shell_lib_test.py`.
* `test_mcp_subscriptions.py` at the repository root — a **SyntaxError** that
  had survived since #9275 because no collector ever tried to import it
  (#13662).

The failure mode is not merely lost coverage: an uncollected directory will
happily hold a test file that does not even parse.

This guard makes exclusions *explicit*. Every tracked test file must be either
collected by one of the two pytest invocations, run by a named workflow, or
listed in ``INTENTIONALLY_UNCOLLECTED`` with a reason. Adding a new test
directory that nothing runs fails here instead of going unnoticed.

The allowlist records the status quo as measured; a reason string is not an
endorsement, and several entries are worth revisiting.

#15018: for its whole life this module enumerated with
``git ls-files "*_test.py" "test_*.py"`` and the second pathspec matched
**nothing**. A bare git pathspec carries no ``:(glob)`` magic, so it is anchored
at the start of the path: ``test_*.py`` matches only a file of that name sitting
at the repository root, and there are none. ``pytest.ini`` declares
``python_files = test_*.py *_test.py``, so the guard built to prove that every
test file is accounted for had never seen 878 of the 2045 files pytest itself
would collect -- including every suite this module's own docstring cites. The
one floor that existed asserted the *combined* list was non-empty, which
``*_test.py`` alone satisfied comfortably; a per-half floor is the assertion
that would have caught it, and is now here.
"""

from __future__ import annotations

import ast
import configparser
import re
import subprocess
from pathlib import Path

import pytest

from autobot_shared.paths import (
    GitRepoRootUnavailable,
    git_repo_root,
    scrubbed_git_env,
)


def project_root() -> Path:
    """Repository root via git, or a skip when this is not a git checkout.

    Deliberately not `autobot_shared.paths.project_root()` (#13652): that helper
    is not on this branch yet, and this module already shells out to git, so the
    same call answers both questions without a second root derivation. Once the
    #13659 stack lands, switching to the canonical resolver removes this
    dependency entirely.

    #15176: the ``GIT_DIR``/``GIT_WORK_TREE`` scrub this module introduced now
    lives in ``autobot_shared.paths`` — five sibling guards had the same
    unscrubbed call, and a per-site copy is how that became a family.

    The whole module is git-driven — every check enumerates *tracked* files — so
    without git there is nothing to assert rather than something failing. This
    repository ships a `.dockerignore` that strips `.git` from build contexts,
    so a git-less checkout is a real configuration here, not a hypothetical, and
    it must skip rather than raise `CalledProcessError` out of ten tests.
    """
    try:
        return git_repo_root(Path(__file__).resolve().parent)
    except GitRepoRootUnavailable:
        pytest.skip("not a git checkout — these checks enumerate tracked files")


#: Top-level directories collected by ci.yml's backend pytest invocation.
BACKEND_RUN = {
    "autobot-backend",
    "autobot_shared",
    "autobot-tts-worker",
    "repo_tests",
    "tools",
    "scripts",
    # #13880 put this on ci.yml's backend invocation and on pytest.ini's
    # testpaths. It was still recorded below as "run by
    # unwired-tracker-audit.yml, not the main suite" -- a reason string that
    # had stopped being true. Corrected here rather than left to read as an
    # exclusion (#15018).
    "pipeline-scripts",
}

#: Collected by the separate slm-backend invocation (#13084 keeps them apart:
#: both backends define identically-named top-level packages).
SLM_RUN = {"autobot-slm-backend"}

#: Path prefix -> the runner collecting it, for trees collected by a path
#: NARROWER than their top-level directory. ci.yml's backend invocation and
#: pytest.ini's testpaths name these exact paths and nothing above them, so a
#: top-level lookup cannot express them (#14884, #14986). Checked before
#: ``INTENTIONALLY_UNCOLLECTED``: ``autobot-infrastructure`` legitimately
#: appears in both, the hooks subtree collected and the rest not.
NARROWLY_COLLECTED = {
    ".claude/skills/claims-audit": (
        "backend-run: named explicitly in ci.yml and pytest.ini's testpaths "
        "(#14986); `.claude/` as a whole is harness territory and does not collect"
    ),
    "autobot-infrastructure/shared/scripts/hooks": (
        "backend-run: named explicitly in ci.yml and pytest.ini's testpaths "
        "(#14884); autobot-infrastructure as a whole does not collect"
    ),
    "autobot-infrastructure/shared/tests": (
        "backend-run: named by pytest.ini's testpaths (line 147) and by "
        "marker-tests.yml's 'marked tests -- infrastructure, libs and frontend' "
        "step (line 341). #15161 repointed this tree's conftest shim, so its "
        "`from config import unified_config_manager` resolves through "
        "autobot-backend/config/__init__.py's lazy `__getattr__` (line 242) and "
        "the tree collects on its own terms"
    ),
    "autobot-frontend/tests": (
        "marker-tests.yml ONLY -- the 'marked tests -- infrastructure, libs and "
        "frontend' step (line 341), added by #14979 and #15166. It shares that "
        "step with `libs` and shared/tests, but NOT their safety net: both of "
        "those are also on pytest.ini's testpaths (lines 147-148) and run "
        "unconditionally, while this tree is absent from testpaths and reaches "
        "ci.yml only as a path filter and npm/vitest steps. So a file added here "
        "carrying no marker MARKER_EXPRESSION selects runs NOWHERE, and "
        "`test_marker_only_trees_carry_a_marker_the_suite_selects` is what makes "
        "that fail rather than pass quietly (#15178)"
    ),
    "libs": (
        "marker-tests.yml, the 'marked tests -- infrastructure, libs and "
        "frontend' step (#13543); the suite is marker-selected, so ci.yml's "
        "invocations, which deselect every marker, would collect it and run nothing"
    ),
}

#: Path prefix -> the DECISION taken about it, and the issue that expires the
#: entry. A description of the breakage is not an exemption: "conftest imports
#: X, which no longer resolves" says what is wrong and nothing about who is
#: fixing it, which is how the `autobot-infrastructure` reason below outlived
#: the defect it named by two issues (#15178). Every entry states one of:
#:
#:   (a) COVERED ELSEWHERE -- and where,
#:   (b) WIRE IN -- and what has to happen first,
#:   (c) PARKED -- and the decision that is outstanding,
#:
#: plus the issue number that would remove the entry.
INTENTIONALLY_UNCOLLECTED = {
    "autobot-npu-worker": (
        "#15476 -- DECISION (b) WIRE IN, after the repairs that issue enumerates. "
        "11 tracked modules holding 168 test functions sit OUTSIDE the resources/ "
        "subtree that pytest.ini --ignore's at line 181 (Windows-only, PySide6); "
        "the remaining 3 are inside it. ONE of the 11 -- openvino/openvino_validation_test.py "
        "-- imports the `openvino` package, which requirements-ci.txt (the only requirements "
        "file ci.yml installs, at line 504) does not carry, so it cannot pass until the "
        "NPU dependency set becomes a CI concern. Three further files match the string "
        "`openvino` but import the local `openvino_dispatch` module, not the package. "
        "That dependency is the repair; this entry expires with it"
    ),
    "autobot-infrastructure": (
        "#15178 -- DECISION (b) WIRE IN. 51 tracked modules under shared/scripts/ "
        "(outside the hooks/ subtree NARROWLY_COLLECTED accounts for) and "
        "shared/tools/, named by no ci.yml invocation and no pytest.ini testpath. "
        "Wiring them in means taking on ~30 ad-hoc scripts under "
        "shared/scripts/analysis/, so it is a decision with a blast radius rather "
        "than a one-line testpath edit. It blocks the 11 uncollected test methods "
        "#14979 left in shared/scripts/{analysis,utilities} -- see "
        "repo_tests/test_methods_in_uncollected_classes_test.py. The reason this "
        "entry carried until #15178, 'conftest imports unified_config_manager, "
        "which no longer resolves', described shared/tests/conftest.py -- a tree "
        "this entry no longer covers, and a breakage #15161 had already repaired"
    ),
    "plugins": (
        "#15178 -- DECISION (c) PARKED. 2 modules under "
        "core-plugins/video-generation-plugin/tools/. `plugins/` is named by no "
        "ci.yml invocation and no pytest.ini testpath, and the plugin directory is "
        "hyphenated, so it is not an importable package -- both modules reach their "
        "subject through importlib.util.spec_from_file_location rather than an "
        "import. Whether dynamically-loaded plugin trees are gated at all is the "
        "outstanding decision, not a wiring fix; parked until it is taken"
    ),
}

#: Per-prefix ceilings on how many tracked test files each exclusion excuses.
#: DOWN-ONLY: an entry may shrink to zero and then be deleted, never grow. This
#: is not a record of today's number -- a growing exclusion is a tree quietly
#: falling out of CI, which is the whole defect #13653 and #15018 recorded, and
#: without a ceiling the allowlist absorbs it silently. Measured on
#: Dev_new_gui after the autobot-frontend and autobot-infrastructure/shared/tests
#: mis-classifications moved to NARROWLY_COLLECTED (#15178); the frontend entry
#: alone had been inflating this by 1 and shared/tests by 5.
#: NEVER raise one to make this pass.
_UNCOLLECTED_CEILINGS = {
    "autobot-infrastructure": 51,
    "autobot-npu-worker": 14,
    "plugins": 2,
}

#: Floor under the SUBJECT, not the finding. Every count above is derived from
#: `_tracked_test_files()`, so a pathspec that collapses to nothing reports zero
#: exclusions and a perfectly clean tree -- the exact failure #15018 recorded,
#: one layer up. Measured 2110 on Dev_new_gui; recorded ~10% under so ordinary
#: consolidation does not trip it. Raise as the tree grows; never lower.
_MIN_TRACKED_TEST_FILES = 1900

#: Minimum tracked files each half of ``python_files`` must match. The floor
#: that existed before #15018 was on the COMBINED list, which ``*_test.py``
#: alone kept non-empty while ``test_*.py`` matched zero for months. Only a
#: per-half floor can see that. Measured on Dev_new_gui: ``test_*.py`` -> 878,
#: ``*_test.py`` -> 1174; recorded ~10% under so that ordinary consolidation
#: does not trip the guard. Raise these as the tree grows. NEVER lower one to
#: make this pass -- a half whose count collapsed is a broken pathspec, which
#: is the entire defect this records.
PATTERN_FLOORS = {"test_*.py": 790, "*_test.py": 1050}


def _python_files_patterns() -> list[str]:
    """The ``python_files`` patterns, read from pytest.ini rather than repeated.

    pytest collects by these and this guard must enumerate by exactly the same
    set, or the two drift apart silently -- which is how #15018 happened.
    """
    ini = (project_root() / "pytest.ini").read_text(encoding="utf-8")
    patterns: list[str] = []
    for line in ini.splitlines():
        stripped = line.strip()
        if stripped.startswith("python_files"):
            patterns = stripped.partition("=")[2].split()
            break

    assert patterns, (
        "pytest.ini declares no `python_files` patterns, so this guard has "
        "nothing to enumerate by and must not report a clean tree"
    )
    return patterns


def _declared_testpaths() -> list[str]:
    """pytest.ini's ``testpaths``, read rather than restated.

    A ``NARROWLY_COLLECTED`` prefix that pytest.ini names runs unconditionally;
    one it does not is only ever reached by a marker-selected workflow. That is
    the difference `_marker_only_prefixes` turns on, so it is derived from the
    config instead of hand-listed here (#15178).
    """
    parser = configparser.ConfigParser()
    parser.read(project_root() / "pytest.ini", encoding="utf-8")
    return parser.get("pytest", "testpaths").split()


def _marker_only_prefixes() -> list[str]:
    """``NARROWLY_COLLECTED`` prefixes whose ONLY runner is marker-selected.

    Derived, not listed: a tree that loses its unconditional runner starts
    being checked here on the next run rather than when someone remembers.
    """
    declared = _declared_testpaths()
    return sorted(
        prefix
        for prefix in NARROWLY_COLLECTED
        if not any(prefix == entry or prefix.startswith(f"{entry}/") for entry in declared)
    )


def _marker_expression_markers() -> set[str]:
    """The marker names marker-tests.yml selects, read from the workflow.

    Restating them here would let the workflow narrow its expression while this
    guard kept vouching for files the run had stopped selecting.
    """
    workflow = project_root() / ".github" / "workflows" / "marker-tests.yml"
    match = re.search(r"MARKER_EXPRESSION:.*?'([^']+)'", workflow.read_text(encoding="utf-8"))

    assert match, (
        "marker-tests.yml no longer defines MARKER_EXPRESSION with a literal "
        "default, so this guard cannot tell which markers the suite selects"
    )
    return {token for token in match.group(1).split() if token != "or"}


def _declared_markers(path: Path) -> set[str]:
    """Marker names a module attaches, via `pytest.mark.X` anywhere in its AST.

    Covers both forms that matter -- a module-level ``pytestmark`` and a
    per-test decorator -- and, being an AST walk, cannot be satisfied by the
    string appearing in a comment or a docstring.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Attribute)
        and node.value.attr == "mark"
        and isinstance(node.value.value, ast.Name)
        and node.value.value.id == "pytest"
    }


def _tracked_test_files_by_pattern() -> dict[str, list[str]]:
    """Tracked files matching each ``python_files`` half, kept separate.

    ``:(glob)`` magic is load-bearing. Without it a pathspec is anchored at the
    start of the path and ``test_*.py`` matches only the repository root. With
    it, a leading ``**/`` matches zero directories too, so the same pathspec
    still covers root-level files -- which
    ``test_no_test_file_sits_at_the_repository_root`` depends on. The anchored
    form is listed alongside it so that dependence is written down rather than
    assumed.
    """
    root = str(project_root())
    matched: dict[str, list[str]] = {}
    for pattern in _python_files_patterns():
        out = subprocess.run(
            ["git", "ls-files", f":(glob){pattern}", f":(glob)**/{pattern}"],
            capture_output=True,
            text=True,
            cwd=root,
            env=scrubbed_git_env(),
            check=False,
        )
        matched[pattern] = sorted({line for line in out.stdout.splitlines() if line})
    return matched


def _tracked_test_files() -> list[str]:
    matched = _tracked_test_files_by_pattern()
    return sorted({path for paths in matched.values() for path in paths})


def _classify(path: str) -> str | None:
    """Return the runner accounting for *path*, or None if unaccounted."""
    for prefix, runner in NARROWLY_COLLECTED.items():
        if path.startswith(f"{prefix}/"):
            return runner

    top = Path(path).parts[0]
    if top in BACKEND_RUN:
        return "backend-run"
    if top in SLM_RUN:
        return "slm-run"

    prefix = _excluded_prefix(path)
    if prefix is not None:
        return f"excluded: {INTENTIONALLY_UNCOLLECTED[prefix]}"
    return None


def _excluded_prefix(path: str) -> str | None:
    """The ``INTENTIONALLY_UNCOLLECTED`` prefix naming *path*, or None.

    Only consulted after the collected prefixes have had their turn, so it is
    never asked about a path a runner already accounts for.
    """
    for prefix in INTENTIONALLY_UNCOLLECTED:
        if path.startswith(f"{prefix}/"):
            return prefix
    return None


def _uncollected_by_prefix() -> dict[str, int]:
    """Tracked test files each exclusion actually excuses, per prefix.

    Routed through ``_classify`` rather than matching the prefixes directly, so
    the count is exactly what the allowlist excuses and not what its prefixes
    happen to span. ``autobot-infrastructure`` spans a collected subtree and an
    uncollected one; counting the collected half as excluded is how the
    frontend and shared/tests entries overstated this number (#15178).
    """
    counts = dict.fromkeys(INTENTIONALLY_UNCOLLECTED, 0)
    for path in _tracked_test_files():
        runner = _classify(path)
        if runner is None or not runner.startswith("excluded: "):
            continue
        prefix = _excluded_prefix(path)
        if prefix is not None:
            counts[prefix] += 1
    return counts


def test_the_tracked_population_is_large_enough_to_mean_anything() -> None:
    """Floor under the subject. Zero files excused out of zero found is not clean.

    Deliberately the first assertion in this module: every other check counts
    what ``_tracked_test_files()`` returns, so a broken pathspec would let them
    all report a spotless tree. This one names the sweep instead.
    """
    files = _tracked_test_files()

    assert len(files) >= _MIN_TRACKED_TEST_FILES, (
        f"the sweep matched only {len(files)} tracked test files, under the "
        f"recorded floor of {_MIN_TRACKED_TEST_FILES}. FIX THE SWEEP -- every "
        "check in this module is derived from this enumeration, so a collapsed "
        "pathspec reads as a clean tree with nothing left uncollected, which is "
        "#15018 one layer up. Never lower this floor to make it pass"
    )


def test_the_uncollected_population_only_ever_shrinks() -> None:
    """``INTENTIONALLY_UNCOLLECTED`` is a ratchet, not a running total.

    A tree that stops being collected lands in an existing exclusion's prefix
    and changes nothing else: the allowlist already has a reason for it, so
    ``test_every_test_file_is_accounted_for`` stays green while coverage
    leaves. The ceiling is the assertion that sees it (#15178).
    """
    counts = _uncollected_by_prefix()

    assert set(counts) == set(_UNCOLLECTED_CEILINGS), (
        "every exclusion needs a ceiling, or it can absorb new files unnoticed: "
        f"allowlist={sorted(counts)} ceilings={sorted(_UNCOLLECTED_CEILINGS)}"
    )

    grew = sorted(
        f"{prefix}: {count} > {_UNCOLLECTED_CEILINGS[prefix]}"
        for prefix, count in counts.items()
        if count > _UNCOLLECTED_CEILINGS[prefix]
    )
    assert not grew, (
        "more test files are excused from collection than when these ceilings "
        "were measured. Collect the new files, or wire the tree in -- NEVER "
        "raise a ceiling to make this pass:\n  " + "\n  ".join(grew)
    )


def test_marker_only_trees_carry_a_marker_the_suite_selects() -> None:
    """A tree whose only runner is marker-selected must actually be selected.

    ``NARROWLY_COLLECTED`` takes a prefix OUT of the ratchet, and nothing else
    was checking what it took on. An unmarked file added under a marker-only
    tree is accounted for by ``_classify``, so the accounting test is green; its
    prefix is no longer in ``INTENTIONALLY_UNCOLLECTED``, so
    ``_UNCOLLECTED_CEILINGS`` never sees it; and
    ``repo_tests/marker_suite_root_coverage_test.py`` only fires on tests that
    DO carry a marker, so it is green too. The file runs nowhere, silently --
    #13653 and #15018 reproduced inside the guard against them (#15178).
    """
    root = project_root()
    selected = _marker_expression_markers()
    unmarked = sorted(
        f"{path} (carries: {sorted(_declared_markers(root / path)) or 'no pytest.mark at all'})"
        for prefix in _marker_only_prefixes()
        for path in _tracked_test_files()
        if path.startswith(f"{prefix}/") and not _declared_markers(root / path) & selected
    )

    assert not unmarked, (
        "these files sit under a NARROWLY_COLLECTED prefix whose only runner is "
        f"marker-selected ({sorted(selected)}), and carry no marker that runner "
        "selects. Nothing collects them and this allowlist excuses them -- mark "
        "them, or give the tree an unconditional runner:\n  " + "\n  ".join(unmarked)
    )


def test_every_test_file_is_accounted_for() -> None:
    """No tracked test file may be invisible to every runner."""
    files = _tracked_test_files()
    assert files, "git ls-files matched no test files — the glob may have drifted"

    unaccounted = sorted(p for p in files if _classify(p) is None)

    assert not unaccounted, (
        "these test files are collected by no pytest invocation and are not on "
        "INTENTIONALLY_UNCOLLECTED — add them to ci.yml's collection list, or to "
        f"the allowlist with a reason:\n  " + "\n  ".join(unaccounted)
    )


def test_no_test_file_sits_at_the_repository_root() -> None:
    """The root is in neither collection list, so a test there runs nowhere.

    This is what hid `test_mcp_subscriptions.py`'s SyntaxError for months
    (#13662). Colocate the file with its subject instead.
    """
    root_level = sorted(p for p in _tracked_test_files() if "/" not in p)

    assert not root_level, (
        "test files at the repository root are collected by nothing — move them "
        f"beside their subject:\n  " + "\n  ".join(root_level)
    )


def test_allowlist_has_no_stale_entries() -> None:
    """A recorded prefix that matches nothing is dead weight.

    Covers both prefix maps: a ``NARROWLY_COLLECTED`` entry naming a tree that
    no longer holds tests is the same dead weight as a stale exclusion, and it
    is the more dangerous of the two -- it would keep accounting for a renamed
    tree that had stopped being collected.
    """
    files = _tracked_test_files()

    stale = sorted(
        f"{name}[{prefix}]"
        for name, mapping in (
            ("INTENTIONALLY_UNCOLLECTED", INTENTIONALLY_UNCOLLECTED),
            ("NARROWLY_COLLECTED", NARROWLY_COLLECTED),
        )
        for prefix in mapping
        if not any(p.startswith(f"{prefix}/") for p in files)
    )

    assert not stale, f"these recorded prefixes match no test file and should be removed: {stale}"


def test_every_python_files_half_is_recorded_with_a_floor() -> None:
    """``PATTERN_FLOORS`` must name exactly what pytest.ini collects by.

    Adding a third pattern to ``python_files`` without a floor here would leave
    that half unfloored -- free to silently match zero, which is #15018 again.
    An empty pattern list fails here too, so the enumeration can never be
    vacuous.
    """
    patterns = set(_python_files_patterns())

    assert patterns == set(PATTERN_FLOORS), (
        "pytest.ini's `python_files` and PATTERN_FLOORS disagree. Every half "
        "pytest collects by needs a recorded floor, or it can match zero "
        f"unnoticed: pytest.ini={sorted(patterns)} floors={sorted(PATTERN_FLOORS)}"
    )


def test_every_python_files_half_matches_at_depth() -> None:
    """Each half separately must match, and match a non-trivial number.

    The pre-#15018 floor asserted only that the COMBINED list was non-empty, so
    ``*_test.py`` alone kept it green while ``test_*.py`` matched zero. A
    combined total hides exactly this bug.
    """
    matched = _tracked_test_files_by_pattern()
    assert matched, "no `python_files` patterns were enumerated at all"

    empty = sorted(pattern for pattern, files in matched.items() if not files)
    assert not empty, (
        "these `python_files` patterns matched NO tracked file. A bare git "
        "pathspec carries no `:(glob)` magic and is anchored at the start of "
        "the path, so a leading-literal pattern matches only at the repository "
        f"root (#15018): {empty}"
    )

    below = sorted(
        f"{pattern}: {len(files)} < {PATTERN_FLOORS[pattern]}"
        for pattern, files in matched.items()
        if len(files) < PATTERN_FLOORS[pattern]
    )
    assert not below, (
        "a `python_files` half matched far fewer files than recorded. Either "
        "the pathspec is broken, or the floor is stale -- check the pathspec "
        "first, and never lower a floor to make this pass:\n  " + "\n  ".join(below)
    )


@pytest.mark.parametrize("directory", sorted(BACKEND_RUN | SLM_RUN))
def test_collected_directories_still_exist(directory: str) -> None:
    """A renamed directory would silently stop being collected."""
    assert (project_root() / directory).is_dir(), f"{directory} is named in ci.yml's collection list but does not exist"
