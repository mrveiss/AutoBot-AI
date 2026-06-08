# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Unit tests for background audit daemon tasks (GH#7356).

Focus: the dedupe-against-existing-issues logic must not spam GitHub with
duplicate issues when an audit task runs multiple times without new findings.
"""

from unittest.mock import MagicMock, patch

from workers.audit_tasks import (
    _dead_code_fingerprint,
    _dedupe_and_file,
    _find_test_file,
    audit_claims,
    audit_dead_code,
    audit_testgaps,
)

# ---------------------------------------------------------------------------
# _dedupe_and_file — shared dedup helper
# ---------------------------------------------------------------------------


class TestDedupeAndFile:
    def test_files_only_new_findings(self):
        existing = {"discovery: old issue"}
        findings = [
            {"title": "discovery: old issue", "body": "body1"},
            {"title": "discovery: new issue", "body": "body2"},
        ]
        with patch("workers.audit_tasks._file_issue", return_value=True) as mock_file:
            filed = _dedupe_and_file(findings, existing, "enhancement")

        assert filed == 1
        mock_file.assert_called_once_with("discovery: new issue", "body2", "enhancement")

    def test_no_filing_when_all_duplicates(self):
        existing = {"discovery: gap A", "discovery: gap B"}
        findings = [
            {"title": "discovery: gap A", "body": "body"},
            {"title": "discovery: gap B", "body": "body"},
        ]
        with patch("workers.audit_tasks._file_issue") as mock_file:
            filed = _dedupe_and_file(findings, existing, "enhancement")

        assert filed == 0
        mock_file.assert_not_called()

    def test_updates_existing_titles_set_to_prevent_double_filing(self):
        existing = set()
        findings = [
            {"title": "discovery: gap X", "body": "body"},
            {"title": "discovery: gap X", "body": "body"},  # exact duplicate in batch
        ]
        with patch("workers.audit_tasks._file_issue", return_value=True):
            filed = _dedupe_and_file(findings, existing, "enhancement")

        assert filed == 1  # second identical title skipped because first added it to set

    def test_zero_findings_files_nothing(self):
        with patch("workers.audit_tasks._file_issue") as mock_file:
            filed = _dedupe_and_file([], set(), "enhancement")

        assert filed == 0
        mock_file.assert_not_called()


# ---------------------------------------------------------------------------
# _dead_code_fingerprint
# ---------------------------------------------------------------------------


class TestDeadCodeFingerprint:
    def test_strips_confidence_suffix(self):
        line = "autobot-backend/foo.py:42: unused function 'bar' (80% confidence)"
        fp = _dead_code_fingerprint(line)
        assert "80%" not in fp
        assert "foo.py:42" in fp

    def test_stable_across_confidence_changes(self):
        a = _dead_code_fingerprint("file.py:10: unused function 'x' (80% confidence)")
        b = _dead_code_fingerprint("file.py:10: unused function 'x' (90% confidence)")
        assert a == b


# ---------------------------------------------------------------------------
# _find_test_file
# ---------------------------------------------------------------------------


class TestFindTestFile:
    def test_finds_stem_test_file(self, tmp_path):
        mod = tmp_path / "mymodule.py"
        mod.write_text("def foo(): pass\n")
        test = tmp_path / "mymodule_test.py"
        test.write_text("def test_foo():\n    pass\n")
        assert _find_test_file(mod, tmp_path) == test

    def test_returns_none_when_no_test_file(self, tmp_path):
        mod = tmp_path / "orphan.py"
        mod.write_text("def foo(): pass\n")
        assert _find_test_file(mod, tmp_path) is None

    def test_returns_none_when_test_file_has_no_test_functions(self, tmp_path):
        mod = tmp_path / "empty_tests.py"
        mod.write_text("def foo(): pass\n")
        test = tmp_path / "empty_tests_test.py"
        test.write_text("# placeholder\n")
        assert _find_test_file(mod, tmp_path) is None


# ---------------------------------------------------------------------------
# audit_testgaps — end-to-end idempotency
# ---------------------------------------------------------------------------


class TestAuditTestgaps:
    def _make_task(self):
        """Return bound task mock."""
        task = audit_testgaps
        mock_self = MagicMock()
        mock_self.update_state = MagicMock()
        return task, mock_self

    def test_second_run_with_no_new_modules_files_zero_issues(self, tmp_path):
        mod = tmp_path / "widget.py"
        mod.write_text("def foo(): pass\n")
        # No test file → first run would file an issue

        redis_store = {}

        def fake_redis_get(redis, key):
            return redis_store.get(key)

        def fake_redis_set(redis, key, value, **kw):
            redis_store[key] = value

        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        def fake_list_open(label=None):
            return list(open_issues)

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._redis_get", side_effect=fake_redis_get),
            patch("workers.audit_tasks._redis_set", side_effect=fake_redis_set),
            patch("workers.audit_tasks._changed_python_modules", return_value=[mod]),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._list_open_issues", side_effect=fake_list_open),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            r1 = audit_testgaps.run()
            assert r1["issues_filed"] == 1

            # Second run with same module returned — but issue already open
            r2 = audit_testgaps.run()
            assert r2["issues_filed"] == 0, "second run must not file duplicate issues"

    def test_no_modules_changed_files_nothing(self, tmp_path):
        with (
            patch("workers.audit_tasks._get_redis", return_value=None),
            patch("workers.audit_tasks._redis_get", return_value=None),
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._changed_python_modules", return_value=[]),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._list_open_issues", return_value=[]),
            patch("workers.audit_tasks._file_issue") as mock_file,
        ):
            result = audit_testgaps.run()

        assert result["issues_filed"] == 0
        mock_file.assert_not_called()


# ---------------------------------------------------------------------------
# audit_dead_code — idempotency via inventory diff
# ---------------------------------------------------------------------------


class TestAuditDeadCode:
    def test_second_run_with_same_inventory_files_zero(self, tmp_path):
        finding = "autobot-backend/foo.py:10: unused function 'bar' (80% confidence)"
        inventory = {"audit:dead_code:last_inventory": [_dead_code_fingerprint(finding)]}

        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch(
                "workers.audit_tasks._redis_get",
                side_effect=lambda _, k: inventory.get(k),
            ),
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._run_vulture", return_value=[finding]),
            patch("workers.audit_tasks._list_open_issues", return_value=list(open_issues)),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            result = audit_dead_code.run()

        assert result["new_findings"] == 0
        assert result["issues_filed"] == 0

    def test_new_finding_files_exactly_one_issue(self):
        finding = "autobot-backend/new.py:5: unused variable 'x' (80% confidence)"
        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._redis_get", return_value=[]),  # empty prior inventory
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._run_vulture", return_value=[finding]),
            patch("workers.audit_tasks._list_open_issues", return_value=[]),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            result = audit_dead_code.run()

        assert result["issues_filed"] == 1

    def test_integration_simulate_finding_then_no_new_finding(self):
        """Integration: first run files one issue; second identical run files zero."""
        finding = "autobot-backend/legacy.py:99: unused class 'OldCache' (80% confidence)"
        stored = {}
        open_issues = set()

        def fake_file_issue(title, body, labels=None):
            open_issues.add(title)
            return True

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._redis_get", side_effect=lambda _, k: stored.get(k)),
            patch(
                "workers.audit_tasks._redis_set",
                side_effect=lambda _, k, v, **kw: stored.update({k: v}),
            ),
            patch("workers.audit_tasks._run_vulture", return_value=[finding]),
            patch(
                "workers.audit_tasks._list_open_issues",
                side_effect=lambda **kw: list(open_issues),
            ),
            patch("workers.audit_tasks._file_issue", side_effect=fake_file_issue),
        ):
            r1 = audit_dead_code.run()
            assert r1["issues_filed"] == 1

            r2 = audit_dead_code.run()
            assert r2["issues_filed"] == 0, "second run must not refile the same finding"


# ---------------------------------------------------------------------------
# audit_claims — dedup against existing issues
# ---------------------------------------------------------------------------


class TestAuditClaims:
    def test_previously_filed_unverified_claim_not_refiled(self, tmp_path):
        (tmp_path / "docs").mkdir()
        readme = tmp_path / "README.md"
        readme.write_text("- GET /api/missing-endpoint — serves data\n")

        # Pre-seed Redis as if previous run already recorded this unverified claim
        claim_key = "README.md:1"
        stored = {"audit:claims:last_run:unverified": [claim_key]}
        open_issues = set()

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._redis_get", side_effect=lambda _, k: stored.get(k)),
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._verify_claim", return_value=False),
            patch("workers.audit_tasks._list_open_issues", return_value=list(open_issues)),
            patch("workers.audit_tasks._file_issue") as mock_file,
        ):
            result = audit_claims.run()

        assert result["issues_filed"] == 0
        mock_file.assert_not_called()

    def test_new_unverified_claim_files_issue(self, tmp_path):
        (tmp_path / "docs").mkdir()
        readme = tmp_path / "README.md"
        readme.write_text("- GET /api/ghost — returns data\n")

        with (
            patch("workers.audit_tasks._get_redis", return_value=MagicMock()),
            patch("workers.audit_tasks._redis_get", return_value=[]),  # no prior unverified
            patch("workers.audit_tasks._redis_set"),
            patch("workers.audit_tasks._repo_root", return_value=tmp_path),
            patch("workers.audit_tasks._verify_claim", return_value=False),
            patch("workers.audit_tasks._list_open_issues", return_value=[]),
            patch("workers.audit_tasks._file_issue", return_value=True) as mock_file,
        ):
            result = audit_claims.run()

        assert result["issues_filed"] == 1
        mock_file.assert_called_once()
