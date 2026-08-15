# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A component must not be reported stale for files its role never deploys (#14283).

`autobot-slm-agent` was permanently in `stale_components`: the walk compared
`health_collector_state_change_test.py` and `version_test.py`, which live in the
role's `files/` tree but are never copied to a node. No sync could clear it, so
the signal that exists to say "something needs attention" always said so.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ROLE_TASKS = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "slm_agent" / "tasks" / "main.yml"
_AGENT_SOURCE = _REPO_ROOT / "autobot-slm-backend" / "ansible" / "roles" / "slm_agent" / "files" / "slm" / "agent"


@pytest.fixture
def drift():
    """Co-located beside drift_checker.py on purpose.

    Under tests/services/ the root conftest stubs `services.*` as MagicMocks, so
    `source_only_patterns(...)` returned a MagicMock and every assertion here
    compared against one — the tests failed for a reason that had nothing to do
    with the behaviour. drift_checker_test.py already lives here for the same
    reason.
    """
    import drift_checker

    return drift_checker


def test_the_agent_excludes_its_undeployed_tests(drift):
    assert drift.source_only_patterns("autobot-slm-agent") == ("*_test.py", "test_*.py")


def test_the_exclusion_is_not_global(drift):
    """The backend components rsync their whole tree, so their co-located tests
    ARE deployed and ARE comparable — 1382 files under autobot-backend on a live
    host. Excluding `*_test.py` everywhere would hide real drift in all of them.
    """
    for component in ("autobot-backend", "autobot-slm-backend", "autobot-frontend"):
        assert drift.source_only_patterns(component) == ()


def test_the_role_really_does_not_deploy_those_files(drift):
    """The premise. If the role ever starts copying its tests, excluding them
    would hide real drift instead of removing a false signal.
    """
    tasks = _ROLE_TASKS.read_text(encoding="utf-8")
    test_sources = [p.name for p in _AGENT_SOURCE.glob("*_test.py")]

    assert test_sources, "no test files in the agent source — this test proves nothing"
    for name in test_sources:
        assert name not in tasks, f"the role now deploys {name}; the exclusion would hide drift"


def test_every_excluded_pattern_matches_something_in_the_source(drift):
    """A pattern matching nothing is dead configuration that reads as protection."""
    import fnmatch

    names = [p.name for p in _AGENT_SOURCE.iterdir() if p.is_file()]
    for pattern in drift.source_only_patterns("autobot-slm-agent"):
        assert any(fnmatch.fnmatch(n, pattern) for n in names), f"{pattern} matches no source file"


def test_the_filter_removes_those_files_from_a_walk(drift, tmp_path):
    """Assert on the collector's output, not on the constant.

    A pattern that is defined but never reaches `_collect_checksums` would leave
    the false signal exactly as it was.
    """
    (tmp_path / "agent.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "agent_test.py").write_text("x = 2\n", encoding="utf-8")

    without = drift._collect_checksums(tmp_path, frozenset({".py"}))
    with_filter = drift._collect_checksums(
        tmp_path, frozenset({".py"}), drift.source_only_patterns("autobot-slm-agent")
    )

    assert "agent_test.py" in without
    assert "agent_test.py" not in with_filter
    assert "agent.py" in with_filter, "the filter removed a real source file"
