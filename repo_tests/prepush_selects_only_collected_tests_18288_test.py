# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The pre-push test selection is a subset of what pytest.ini collects (#18288).

A changed ``test_*.py`` anywhere was selected and run, including the live probe scripts under
``autobot-infrastructure/shared/scripts/analysis``: no CI shard collects them, so the push ran
them against the developer's machine (an index of the whole project, LLM and Redis calls) and
failed on files nobody gates on. The roots now come from ``pytest.ini`` ``testpaths``, the one list.
"""

from __future__ import annotations

from repo_tests._paths import repo_root

from tools.lint.prepush_selection import pytest_settings, pytest_testpaths, select

PROBE = "autobot-infrastructure/shared/scripts/analysis/test_x.py"
COLLECTED = "repo_tests/x_test.py"


def _selected(changed: list[str], existing: set[str]) -> dict[str, str]:
    ini = (repo_root() / "pytest.ini").read_text(encoding="utf-8")
    patterns, ignores = pytest_settings(ini)
    return select(
        changed,
        patterns=patterns,
        ignores=ignores,
        exists=existing.__contains__,
        testpaths=pytest_testpaths(ini),
    )


def test_testpaths_are_read_from_pytest_ini() -> None:
    roots = pytest_testpaths((repo_root() / "pytest.ini").read_text(encoding="utf-8"))
    assert {"repo_tests", "autobot-backend", "autobot-slm-backend", "autobot_shared"} <= set(roots)
    assert all(root and not root.startswith("#") for root in roots)


def test_contrast_a_probe_script_is_not_selected_and_a_collected_test_is() -> None:
    got = _selected([PROBE, COLLECTED], {PROBE, COLLECTED})
    assert COLLECTED in got
    assert PROBE not in got


def test_a_probe_script_is_not_selected_through_co_location_either() -> None:
    probe_module = "autobot-infrastructure/shared/scripts/analysis/x.py"
    probe_test = "autobot-infrastructure/shared/scripts/analysis/x_test.py"
    assert _selected([probe_module], {probe_test}) == {}


def test_every_selected_path_lies_under_a_testpath() -> None:
    roots = pytest_testpaths((repo_root() / "pytest.ini").read_text(encoding="utf-8"))
    changed = [
        PROBE,
        COLLECTED,
        "autobot-backend/tests/test_y.py",
        "autobot-infrastructure/shared/scripts/hooks/z_test.py",
    ]
    got = _selected(changed, set(changed))
    assert got and all(any(p == r or p.startswith(r + "/") for r in roots) for p in got)
