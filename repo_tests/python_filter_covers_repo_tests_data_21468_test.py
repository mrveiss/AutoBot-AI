# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The python-suite filter must cover the DATA files under ``repo_tests`` (#21468).

``python_filter_covers_its_guards_test.py`` leaves ``repo_tests`` out of its read
detection (``_NOT_A_READ``) because the guards' own sources are Python and
``**/*.py`` already covers them. The non-Python files that live beside them are
a different population: baselines, frozen re-measure lists and fixtures that
guards read. A pull request editing only one of those matches no ``**/*.py``
pattern, computes ``python != 'true'``, and the guard written to read the file
never runs.

This sweeps the tracked non-Python files under ``repo_tests`` and asks the
existing matcher (imported, never re-implemented) whether the filter covers
each. It examines every such file rather than only those a guard names: a file
read through a variable is invisible to a name scan, and the class entry in the
filter is one tree glob, so the stronger claim costs nothing.
"""

from __future__ import annotations

from repo_tests._paths import repo_root
from repo_tests.python_filter_covers_its_guards_test import _filter_patterns, _is_covered

from tools.lint._scan_helpers import tracked_paths

_TREE = "repo_tests"

#: Anchors for the reach check, by name and not by count: a baseline and a
#: fixture directory that guards read today. If the enumeration stops finding
#: them it has stopped looking at the tree, and a clean result means nothing.
_REACH_ANCHORS = (
    "repo_tests/unconnected_code_baseline.txt",
    "repo_tests/secrets_baseline_legacy_keys.json",
    "repo_tests/fixtures/pre_15360_changes_jobs.json",
)


def _data_files() -> list[str]:
    """Tracked non-Python paths under the tree, sorted."""
    return sorted(tracked_paths(repo_root(), _TREE, exclude=("*.py",)))


def uncovered_data_files(paths: list[str], patterns: list[str]) -> list[str]:
    """The non-Python *paths* under the tree that *patterns* do not cover."""
    return sorted(p for p in paths if p.startswith(f"{_TREE}/") and not _is_covered(p, patterns))


def test_the_sweep_reaches_the_data_files_it_claims_to() -> None:
    """Reach before findings: an empty or partial enumeration must fail."""
    found = set(_data_files())
    missing = [anchor for anchor in _REACH_ANCHORS if anchor not in found]
    assert not missing, f"the enumeration no longer finds {missing}; it is not reading {_TREE}"
    assert not any(p.endswith(".py") for p in found), "the enumeration must exclude the Python files"


def test_python_filter_covers_every_repo_tests_data_file() -> None:
    uncovered = uncovered_data_files(_data_files(), _filter_patterns())
    assert not uncovered, (
        f"the python-suite filter does not cover these {len(uncovered)} data files under {_TREE}/ -- an edit "
        "confined to one takes the required-context shim's green and the guard that reads it never runs "
        "(#21468). Cover the class in .github/filters/python-paths.yml:\n  " + "\n  ".join(uncovered)
    )


def test_a_planted_uncovered_data_file_is_reported() -> None:
    """Control: the check can say no, on synthetic paths and a synthetic filter."""
    planted = ["repo_tests/new_baseline.txt", "repo_tests/fixtures/new.json", "repo_tests/a_test.py"]
    assert uncovered_data_files(planted, ["**/*.py"]) == [
        "repo_tests/fixtures/new.json",
        "repo_tests/new_baseline.txt",
    ]
    assert uncovered_data_files(planted, ["**/*.py", f"{_TREE}/**"]) == []


def test_the_real_filter_covers_a_data_file_added_later() -> None:
    """The class entry covers files that do not exist yet, not just today's twenty."""
    patterns = _filter_patterns()
    assert uncovered_data_files(["repo_tests/not_yet_added_baseline.txt", "repo_tests/sub/dir/x.json"], patterns) == []
