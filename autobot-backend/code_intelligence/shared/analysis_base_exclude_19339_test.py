# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""BaseCodeAnalyzer._should_exclude matches canonical dirs below the scan root (#19339)."""

from pathlib import Path

from code_intelligence.shared.analysis_base import DEFAULT_EXCLUDE_PATTERNS, BaseCodeAnalyzer


def _analyzer() -> BaseCodeAnalyzer:
    analyzer = BaseCodeAnalyzer.__new__(BaseCodeAnalyzer)
    analyzer.exclude_patterns = list(DEFAULT_EXCLUDE_PATTERNS)
    return analyzer


def test_a_root_level_canonical_dir_is_excluded(tmp_path: Path) -> None:
    assert _analyzer()._should_exclude(tmp_path / "node_modules" / "x.py", tmp_path)


def test_github_dirs_stay_excluded_as_the_old_git_substring_did(tmp_path: Path) -> None:
    assert _analyzer()._should_exclude(tmp_path / ".github" / "x.py", tmp_path)


def test_a_scan_rooted_inside_a_worktree_keeps_its_own_files(tmp_path: Path) -> None:
    root = tmp_path / ".worktrees" / "wt-1"
    analyzer = _analyzer()
    assert not analyzer._should_exclude(root / "pkg" / "x.py", root)
    assert analyzer._should_exclude(root / ".worktrees" / "inner" / "x.py", root)


def test_a_name_that_merely_contains_a_skip_dir_is_not_excluded(tmp_path: Path) -> None:
    assert not _analyzer()._should_exclude(tmp_path / "object_model" / "binary_io.py", tmp_path)
