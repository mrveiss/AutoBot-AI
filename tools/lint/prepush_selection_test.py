# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-push test selection (#16711), driven with fixture changesets.

#16700's changeset held three ``tests/test_*.py`` files and a ``*_test.py`` guard; the
old selection ran only the guard, so a broken assertion in one of the others failed
first in CI.
"""

from __future__ import annotations

from pathlib import Path

from tools.lint.prepush_selection import format_selection, pytest_settings, select

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PATTERNS = ("test_*.py", "*_test.py")


def _run(changed, *, present=None, ignores=()):
    """Select for *changed*; every changed path exists unless *present* names the files that do."""
    files = set(changed) if present is None else set(present)
    return select(changed, patterns=_PATTERNS, ignores=ignores, exists=lambda rel: rel in files)


def test_the_16700_changeset_runs_every_test_it_changed():
    """#16711: each tests/test_*.py here was classified as production and never ran."""
    changed = [
        "autobot-backend/tests/test_npu_bootstrap_credential_16657.py",
        "autobot-slm-backend/tests/test_redis_password_provisioned_16627.py",
        "autobot-slm-backend/tests/test_redis_username_plumbing_16626.py",
        "repo_tests/redis_password_literal_guard_test.py",
    ]
    assert _run(changed) == {path: "changed" for path in changed}


def test_the_naming_conventions_come_from_pytest_ini():
    ini = "[pytest]\npython_files = test_*.py *_test.py check_*.py\naddopts =\n    -ra\n    --ignore=vendor/tree\n"
    assert pytest_settings(ini) == (("test_*.py", "*_test.py", "check_*.py"), ("vendor/tree",))
    patterns, _ = pytest_settings((_REPO_ROOT / "pytest.ini").read_text(encoding="utf-8"))
    assert {"test_*.py", "*_test.py"} <= set(patterns)


def test_a_changed_module_still_selects_its_co_located_test():
    module, sibling = "autobot-backend/knowledge/facts.py", "autobot-backend/knowledge/facts_test.py"
    assert _run([module], present={sibling}) == {sibling: f"co-located with {module}"}


def test_a_changed_test_module_is_not_given_a_sibling():
    """A test_*.py is a test; looking for test_x_test.py was the #16711 misclassification."""
    assert _run(["pkg/tests/test_x.py"], present={"pkg/tests/test_x.py", "pkg/tests/test_x_test.py"}) == {
        "pkg/tests/test_x.py": "changed"
    }


def test_an_ignored_or_vanished_test_is_never_selected():
    assert _run(["vendor/tree/x_test.py"], ignores=("vendor/tree",)) == {}
    assert _run(["gone_test.py"], present=set()) == {}
    assert _run(["docs/readme.md"]) == {}


def test_every_selected_test_is_printed_with_its_reason():
    assert format_selection({"a_test.py": "changed", "b_test.py": "co-located with b.py"}) == (
        "a_test.py\tchanged\nb_test.py\tco-located with b.py\n"
    )
