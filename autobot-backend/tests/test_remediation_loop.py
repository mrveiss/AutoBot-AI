# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""
Tests for scripts/test_first_remediation.py — covers the limit-detection
and safety-guard logic without requiring GitHub or a live Claude session.
"""

# Import the module under test
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts"))
import test_first_remediation as tfr

# ---------------------------------------------------------------------------
# Destructive command guard
# ---------------------------------------------------------------------------


class TestBlockedCommands:
    def test_rm_rf_is_blocked(self):
        assert tfr._is_destructive("rm -rf /some/path")

    def test_rsync_delete_is_blocked(self):
        assert tfr._is_destructive("rsync --delete -avz /src/ /dst/")

    def test_git_reset_hard_is_blocked(self):
        assert tfr._is_destructive("git reset --hard HEAD~1")

    def test_git_clean_fd_is_blocked(self):
        assert tfr._is_destructive("git clean -fd")

    def test_safe_rm_not_blocked(self):
        assert not tfr._is_destructive("rm somefile.txt")

    def test_git_status_not_blocked(self):
        assert not tfr._is_destructive("git status")

    def test_rsync_without_delete_not_blocked(self):
        assert not tfr._is_destructive("rsync -avz /src/ /dst/")

    def test_pytest_not_blocked(self):
        assert not tfr._is_destructive("python3 -m pytest -x")


# ---------------------------------------------------------------------------
# run_pytest helper
# ---------------------------------------------------------------------------


class TestRunPytest:
    def test_returns_true_on_zero_exit(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="1 passed", stderr="")
            passed, output = tfr.run_pytest(tmp_path)
        assert passed is True
        assert "1 passed" in output

    def test_returns_false_on_nonzero_exit(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1, stdout="FAILED", stderr="AssertionError")
            passed, output = tfr.run_pytest(tmp_path)
        assert passed is False
        assert "FAILED" in output

    def test_passes_test_path_when_given(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            tfr.run_pytest(tmp_path, "tests/test_foo.py")
            cmd = mock_run.call_args[0][0]
        assert "tests/test_foo.py" in cmd

    def test_omits_test_path_when_not_given(self, tmp_path):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            tfr.run_pytest(tmp_path)
            cmd = mock_run.call_args[0][0]
        assert not any(c.endswith(".py") for c in cmd if "pytest" not in c)


# ---------------------------------------------------------------------------
# RemediationResult
# ---------------------------------------------------------------------------


class TestRemediationResult:
    def test_success_result(self):
        r = tfr.RemediationResult(
            issue_number=42, success=True, iterations=2, pr_url="https://github.com/mrveiss/AutoBot-AI/pull/99"
        )
        assert r.success
        assert r.iterations == 2
        assert r.pr_url is not None
        assert r.failure_report is None

    def test_failure_result_has_report(self):
        r = tfr.RemediationResult(issue_number=42, success=False, iterations=5, failure_report="Exhausted attempts")
        assert not r.success
        assert "Exhausted" in r.failure_report

    def test_notes_default_to_empty_list(self):
        r = tfr.RemediationResult(issue_number=1, success=False, iterations=0)
        assert r.notes == []


# ---------------------------------------------------------------------------
# dry_run path
# ---------------------------------------------------------------------------


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_returns_without_creating_worktree(self, capsys):
        issue = {"number": 123, "title": "test bug", "body": "details", "labels": []}
        with patch.object(tfr, "create_worktree") as mock_wt:
            result = await tfr.remediate_issue(issue, dry_run=True)
        mock_wt.assert_not_called()
        assert result.success is False
        assert any("dry-run" in n for n in result.notes)

    @pytest.mark.asyncio
    async def test_dry_run_prints_plan(self, capsys):
        issue = {"number": 456, "title": "another bug", "body": "", "labels": []}
        await tfr.remediate_issue(issue, dry_run=True)
        captured = capsys.readouterr()
        assert "dry-run" in captured.out
        assert "456" in captured.out
