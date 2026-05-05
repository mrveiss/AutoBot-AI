#!/usr/bin/env python3
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for pipeline-scripts/audit-unwired-trackers.py (#6929).

Covers the surfaces flagged in #6927 (SCAN_DIRS gap), #6928 (regex gap),
and #6929 (no tests). The script is the Tier-3 cron defense for the
#6836 closure-gate process — silent regressions in its regex / scan /
dedup paths erode the entire defense, so these tests pin the contract.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# The script's filename has a hyphen, so we have to load it via importlib.
_SCRIPT_PATH = Path(__file__).parent / "audit-unwired-trackers.py"
_SPEC = importlib.util.spec_from_file_location("audit_unwired_trackers", _SCRIPT_PATH)
assert _SPEC is not None and _SPEC.loader is not None
audit = importlib.util.module_from_spec(_SPEC)
sys.modules["audit_unwired_trackers"] = audit
_SPEC.loader.exec_module(audit)


# ---------------------------------------------------------------------------
# extract_tracker_refs / ISSUE_REF_RE — #6928 regex coverage
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "doctext,expected",
    [
        # Original 4 shapes (must keep working).
        ('"""Issue #1234: foo."""', [1234]),
        ('"""Topology-Aware Router (#2138)."""', [2138]),
        ("# #5678: heading style\n", [5678]),
        ("See https://github.com/x/y/issues/9999\n", [9999]),
        # New shapes added by #6928.
        ('"""Closes #4321."""', [4321]),
        ('"""Fixes #1111 and Resolves #2222."""', [1111, 2222]),
        ("# Related #3456 and Tracking #7890.\n", [3456, 7890]),
        ("See [#5555](https://github.com/x/y/issues/5555) for details.\n", [5555]),
        # Multiple in same docstring — order preserved, deduped.
        ('"""Issue #100 — Closes #100 (dup) and Fixes #200."""', [100, 200]),
        # Mixed case isn't matched (`closes` lower would not be the convention).
        ('"""closes #999 lowercase."""', []),
    ],
)
def test_extract_tracker_refs_shapes(tmp_path: Path, doctext: str, expected: list[int]) -> None:
    f = tmp_path / "sample.py"
    f.write_text(doctext, encoding="utf-8")
    assert audit.extract_tracker_refs(f) == expected


def test_extract_tracker_refs_only_first_40_lines(tmp_path: Path) -> None:
    """Refs deeper than DOCSTRING_HEAD_LINES are intentionally ignored —
    the audit is a docstring-citation check, not a full-file scan."""
    f = tmp_path / "deep.py"
    f.write_text("\n" * 100 + 'Issue #4242', encoding="utf-8")
    assert audit.extract_tracker_refs(f) == []


def test_extract_tracker_refs_unreadable_file(tmp_path: Path) -> None:
    """OSError / UnicodeDecodeError must return [] not crash the audit."""
    f = tmp_path / "binary.py"
    f.write_bytes(b"\x80\x81\x82\xfe\xff\x00")
    assert audit.extract_tracker_refs(f) == []


# ---------------------------------------------------------------------------
# is_test_path / should_skip_path — boundary cases
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,is_test",
    [
        (Path("autobot-backend/foo_test.py"), True),
        (Path("autobot-backend/foo.test.ts"), True),
        (Path("autobot-backend/tests/test_foo.py"), True),
        (Path("autobot-frontend/src/__tests__/Foo.spec.ts"), True),
        (Path("autobot-backend/foo.py"), False),
        # Edge: 'test' in a non-test segment shouldn't match
        (Path("autobot-backend/contestant.py"), False),
    ],
)
def test_is_test_path(path: Path, is_test: bool) -> None:
    assert audit.is_test_path(path) is is_test


@pytest.mark.parametrize(
    "path,should_skip",
    [
        # Fragments require a leading separator — the audit's intent is to
        # skip paths that *contain* these as directory segments, never as
        # filename prefixes (e.g. a real "build_*.py" production file).
        (Path("/repo/autobot-backend/__pycache__/foo.cpython-310.pyc"), True),
        (Path("/repo/autobot-frontend/node_modules/x/index.ts"), True),
        (Path("/repo/.worktrees/issue-1234/foo.py"), True),
        (Path("/repo/autobot-backend/dist/bundle.js"), True),
        (Path("/repo/autobot-backend/build/out.js"), True),
        (Path("/repo/autobot-backend/migrations/0001_init.py"), True),
        (Path("/repo/autobot-backend/foo.py"), False),
    ],
)
def test_should_skip_path(path: Path, should_skip: bool) -> None:
    assert audit.should_skip_path(path) is should_skip


# ---------------------------------------------------------------------------
# SCAN_DIRS — #6927 expansion
# ---------------------------------------------------------------------------


def test_scan_dirs_includes_slm_and_infrastructure() -> None:
    """#6927: ensure the historically-skipped backends are now scanned."""
    assert "autobot-slm-backend" in audit.SCAN_DIRS
    assert "autobot-infrastructure" in audit.SCAN_DIRS
    assert "autobot-npu-worker" in audit.SCAN_DIRS


# ---------------------------------------------------------------------------
# grep_count_production_callers — ambiguous-stem skip + dedup
# ---------------------------------------------------------------------------


def test_grep_count_skips_ambiguous_stem(tmp_path: Path) -> None:
    """Module names like `utils`, `__init__`, `types` are too noisy to grep
    reliably — must short-circuit to -1 (skip) before invoking grep."""
    fake_self = tmp_path / "utils.py"
    fake_self.write_text("", encoding="utf-8")
    assert audit.grep_count_production_callers("utils", fake_self) == -1
    assert audit.grep_count_production_callers("__init__", fake_self) == -1
    assert audit.grep_count_production_callers("types", fake_self) == -1


def test_grep_count_excludes_self_and_test_paths() -> None:
    """The grep result must not count the module's own file or test files."""
    fake_stdout = (
        f"{audit.REPO_ROOT}/autobot-backend/foo.py:10:from foo import bar\n"  # self
        f"{audit.REPO_ROOT}/autobot-backend/foo_test.py:5:from foo import bar\n"  # test
        f"{audit.REPO_ROOT}/autobot-backend/tests/test_foo.py:5:from foo import bar\n"  # test
        f"{audit.REPO_ROOT}/autobot-backend/__pycache__/foo.cpython-310.pyc:0:cached\n"  # pyc
        f"{audit.REPO_ROOT}/autobot-backend/real_caller.py:42:from foo import bar\n"  # real
    )
    fake_run = MagicMock(returncode=0, stdout=fake_stdout, stderr="")
    self_path = audit.REPO_ROOT / "autobot-backend/foo.py"
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.grep_count_production_callers("foo", self_path) == 1


def test_grep_count_handles_grep_error() -> None:
    """grep returncode > 1 means an error — return -1 (skip) not 0."""
    fake_run = MagicMock(returncode=2, stdout="", stderr="grep: I/O error")
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.grep_count_production_callers("foo", Path("/dev/null")) == -1


def test_grep_count_handles_timeout() -> None:
    """subprocess.TimeoutExpired must return -1, not crash."""
    import subprocess as _sp

    def _raise(*_a, **_kw):
        raise _sp.TimeoutExpired(cmd="grep", timeout=60)

    with patch.object(audit.subprocess, "run", side_effect=_raise):
        assert audit.grep_count_production_callers("foo", Path("/dev/null")) == -1


# ---------------------------------------------------------------------------
# fetch_closed_tracker_set — gh JSON parsing + error path
# ---------------------------------------------------------------------------


def test_fetch_closed_tracker_set_parses_gh_output() -> None:
    fake_run = MagicMock(
        returncode=0,
        stdout=json.dumps([{"number": 1}, {"number": 2}, {"number": 3}]),
        stderr="",
    )
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.fetch_closed_tracker_set() == {1, 2, 3}


def test_fetch_closed_tracker_set_gh_unavailable() -> None:
    """gh missing or non-zero exit must degrade gracefully to empty set."""
    with patch.object(audit.subprocess, "run", side_effect=FileNotFoundError("gh")):
        assert audit.fetch_closed_tracker_set() == set()


def test_fetch_closed_tracker_set_invalid_json() -> None:
    fake_run = MagicMock(returncode=0, stdout="<<not json>>", stderr="")
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.fetch_closed_tracker_set() == set()


# ---------------------------------------------------------------------------
# existing_audit_issues_by_tracker — title-prefix dedup
# ---------------------------------------------------------------------------


def test_existing_audit_issues_extracts_tracker_numbers() -> None:
    fake_run = MagicMock(
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "number": 9000,
                    "title": "discovery(unwired-tracker): wire in foo (tracker #1234 closed prematurely)",
                },
                {
                    "number": 9001,
                    "title": "discovery(unwired-tracker): wire in bar (tracker #5678 closed prematurely)",
                },
                # No tracker number → must not crash, just skipped
                {"number": 9002, "title": "unrelated issue title"},
            ]
        ),
        stderr="",
    )
    with patch.object(audit.subprocess, "run", return_value=fake_run):
        assert audit.existing_audit_issues_by_tracker() == {1234, 5678}


def test_existing_audit_issues_gh_failure() -> None:
    """gh failures must return empty set (open-mode default — file new ones)."""
    with patch.object(audit.subprocess, "run", side_effect=FileNotFoundError("gh")):
        assert audit.existing_audit_issues_by_tracker() == set()


# ---------------------------------------------------------------------------
# render_human / render_json — output shape contracts
# ---------------------------------------------------------------------------


def test_render_human_no_findings() -> None:
    out = audit.render_human([])
    assert "✅" in out
    assert "No unwired-tracker findings" in out


def test_render_human_with_findings() -> None:
    findings = [
        audit.Finding(file="autobot-backend/foo.py", tracker=42, tracker_state="CLOSED", production_callers=0),
    ]
    out = audit.render_human(findings)
    assert "❌" in out
    assert "autobot-backend/foo.py" in out
    assert "#42" in out


def test_render_json_round_trips() -> None:
    findings = [
        audit.Finding(file="x.py", tracker=1, tracker_state="CLOSED", production_callers=0),
    ]
    parsed = json.loads(audit.render_json(findings))
    assert parsed == [{"file": "x.py", "tracker": 1, "tracker_state": "CLOSED", "production_callers": 0}]
