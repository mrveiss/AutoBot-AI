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

import os
import subprocess
from pathlib import Path

import pytest


#: Git variables a hook exports into its child processes. With ``GIT_DIR`` set
#: and no ``GIT_WORK_TREE``, git treats the *current directory* as the work
#: tree, so ``rev-parse --show-toplevel`` answers `repo_tests/` rather than the
#: repository root and every path derived from it is wrong. The pre-push hook
#: runs this module, so that is a real environment here, not a hypothetical.
_AMBIENT_GIT_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")


def _git_env() -> dict[str, str]:
    """The environment minus whatever git state a calling hook exported."""
    return {k: v for k, v in os.environ.items() if k not in _AMBIENT_GIT_VARS}


def project_root() -> Path:
    """Repository root via git, or a skip when this is not a git checkout.

    Deliberately not `autobot_shared.paths.project_root()` (#13652): that helper
    is not on this branch yet, and this module already shells out to git, so the
    same call answers both questions without a second root derivation. Once the
    #13659 stack lands, switching to the canonical resolver removes this
    dependency entirely.

    The whole module is git-driven — every check enumerates *tracked* files — so
    without git there is nothing to assert rather than something failing. This
    repository ships a `.dockerignore` that strips `.git` from build contexts,
    so a git-less checkout is a real configuration here, not a hypothetical, and
    it must skip rather than raise `CalledProcessError` out of ten tests.
    """
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent),
        env=_git_env(),
        check=False,
    )
    if out.returncode != 0:
        pytest.skip("not a git checkout — these checks enumerate tracked files")
    return Path(out.stdout.strip())


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
    "libs": (
        "marker-tests.yml, the 'marked tests -- infrastructure and libs' step "
        "(#13543); the suite is marker-selected, so ci.yml's invocations, which "
        "deselect every marker, would collect it and run nothing"
    ),
}

#: Path prefix -> why nothing collects it. Reasons, not endorsements.
INTENTIONALLY_UNCOLLECTED = {
    "autobot-npu-worker": (
        "not in either ci.yml invocation; pytest.ini only --ignore's its resources/ "
        "subdirectory (Windows-only, PySide6), so the other suites are simply uncollected"
    ),
    "autobot-infrastructure": "conftest imports unified_config_manager, which no longer resolves",
    "plugins": "optional plugin tools; deps not installed by the CI requirements",
    "autobot-frontend": "Python helper beside the Vue app; not part of either backend suite",
}

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
            env=_git_env(),
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

    for prefix, reason in INTENTIONALLY_UNCOLLECTED.items():
        if path.startswith(f"{prefix}/"):
            return f"excluded: {reason}"
    return None


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

    assert not stale, (
        f"these recorded prefixes match no test file and should be removed: {stale}"
    )


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
    assert (project_root() / directory).is_dir(), (
        f"{directory} is named in ci.yml's collection list but does not exist"
    )
