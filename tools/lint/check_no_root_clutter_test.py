#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the root-clutter guard (#14216)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_MODULE_PATH = Path(__file__).resolve().parent / "check_no_root_clutter.py"
_spec = importlib.util.spec_from_file_location("check_no_root_clutter", _MODULE_PATH)
assert _spec is not None and _spec.loader is not None
check_no_root_clutter = importlib.util.module_from_spec(_spec)
sys.modules["check_no_root_clutter"] = check_no_root_clutter
_spec.loader.exec_module(check_no_root_clutter)

find_violations = check_no_root_clutter.find_violations
ALLOWED_ROOT_FILES = check_no_root_clutter.ALLOWED_ROOT_FILES


class TestAllowedRootFiles:
    """The allowlisted front-door files must stay clean."""

    @pytest.mark.parametrize("name", sorted(ALLOWED_ROOT_FILES))
    def test_allowlisted_file_is_clean(self, name: str) -> None:
        assert find_violations([name]) == []

    def test_licence_and_notice_are_not_documents(self) -> None:
        """Extension-less root files are out of scope, not violations."""
        assert find_violations(["LICENSE", "NOTICE", "THIRD-PARTY-NOTICES"]) == []

    def test_non_document_root_files_ignored(self) -> None:
        assert find_violations(["Makefile", "main.py", "docker-compose.yml", "install.sh"]) == []


class TestRootClutter:
    """The invariant: an unlisted top-level document is a violation."""

    @pytest.mark.parametrize(
        "name",
        [
            "BUG_SWEEP_REPORT.md",
            "UMBRELLA_PLAN.md",
            "TRIAGE_DELTA_REPORT.md",
            "SESSION_9930_PHASE_C_PREREQ_REPORT_2026_06_26.md",
            "IMPLEMENTATION_REPORT.txt",
            "missing_dep_sites.txt",
            # The invariant is "unlisted", not "matches a known report name" —
            # a document nobody has seen yet must fail just the same.
            "NOTES.md",
            "scratch.txt",
        ],
    )
    def test_unlisted_root_document_is_flagged(self, name: str) -> None:
        violations = find_violations([name])
        assert [path for path, _ in violations] == [name]

    def test_reason_points_at_the_destination(self) -> None:
        (_, reason), = find_violations(["BUG_SWEEP_REPORT.md"])
        assert "docs/reports/" in reason

    def test_uppercase_extension_still_flagged(self) -> None:
        assert [p for p, _ in find_violations(["REPORT.MD"])] == ["REPORT.MD"]

    def test_same_name_in_a_subdirectory_is_clean(self) -> None:
        """Only the front door is in scope — docs/reports/ is the destination."""
        assert find_violations(["docs/reports/BUG_SWEEP_REPORT.md"]) == []
        assert find_violations(["docs/research/some-audit.md"]) == []

    def test_mixed_batch_reports_only_the_offenders(self) -> None:
        paths = ["README.md", "BUG_SWEEP_REPORT.md", "docs/reports/DEDUP_REPORT.md", "UMBRELLA_PLAN.md"]
        assert [p for p, _ in find_violations(paths)] == ["BUG_SWEEP_REPORT.md", "UMBRELLA_PLAN.md"]


class TestMagicMockArtifact:
    """#14217 — a mock repr promoted to a real directory tree must never land."""

    @pytest.mark.parametrize(
        "path",
        [
            "MagicMock",
            "MagicMock/mock.config_manager.get()",
            "MagicMock/mock.settings.backup_dir/124658818721376",
            "MagicMock/mock.unified_config_manager.get().get().get()/139330198930624/file_manager_root",
        ],
    )
    def test_artifact_paths_are_flagged(self, path: str) -> None:
        violations = find_violations([path])
        assert [p for p, _ in violations] == [path]
        assert "#14217" in violations[0][1]

    def test_similarly_named_real_path_is_not_a_false_positive(self) -> None:
        """Prefix matching must respect the path separator."""
        assert find_violations(["MagicMockHelpers/utils.py"]) == []


class TestScanIntegrity:
    """An empty result must not read as a clean result."""

    def test_missing_readme_fails_the_scan(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(check_no_root_clutter, "_tracked_paths", lambda _root: [])
        assert check_no_root_clutter.main([]) == 2

    def test_git_failure_is_not_reported_clean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(_root: Path) -> list[str]:
            raise RuntimeError("git ls-files failed: not a git repository")

        monkeypatch.setattr(check_no_root_clutter, "_tracked_paths", _boom)
        assert check_no_root_clutter.main([]) == 2

    def test_clean_tree_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            check_no_root_clutter,
            "_tracked_paths",
            lambda _root: ["README.md", "docs/reports/BUG_SWEEP_REPORT.md", "main.py"],
        )
        assert check_no_root_clutter.main([]) == 0

    def test_dirty_tree_blocks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            check_no_root_clutter,
            "_tracked_paths",
            lambda _root: ["README.md", "BUG_SWEEP_REPORT.md"],
        )
        assert check_no_root_clutter.main([]) == 1


class TestRepositoryIsClean:
    """The live repository must satisfy its own guard."""

    def test_actual_root_is_clean(self) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        paths = check_no_root_clutter._tracked_paths(repo_root)
        assert "README.md" in paths, "scan did not see the repository"
        assert find_violations(paths) == []
