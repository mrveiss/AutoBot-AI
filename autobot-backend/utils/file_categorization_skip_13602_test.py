# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`is_skipped_path` decides what an analytics scan can see (#13602).

Adding `.worktrees` to SKIP_DIRS is only safe because this function relativises
first. Testing `SKIP_DIRS & set(path.parts)` on an absolute path asks whether a
skip name appears ANYWHERE in it — including in the scan root — and CI and
development both run from inside a worktree. Get this wrong and a scan reports
an empty codebase: no error, no log, just zero results.
"""

from pathlib import Path

import pytest

from utils.file_categorization import SKIP_DIRS, is_skipped_path


class TestRootRelativity:
    def test_the_root_s_own_ancestry_is_irrelevant(self, tmp_path):
        root = tmp_path / ".worktrees" / "issue-13602"
        assert not is_skipped_path(root / "pkg" / "mod.py", root)

    def test_a_skip_dir_nested_under_the_root_is_still_skipped(self, tmp_path):
        root = tmp_path / ".worktrees" / "issue-13602"
        assert is_skipped_path(root / ".worktrees" / "inner" / "mod.py", root)
        assert is_skipped_path(root / "node_modules" / "x" / "mod.js", root)

    def test_both_worktree_layouts_are_covered(self, tmp_path):
        """`.worktrees/` and `.claude/worktrees/` held 96% of the files."""
        assert is_skipped_path(tmp_path / ".worktrees" / "a" / "m.py", tmp_path)
        assert is_skipped_path(tmp_path / ".claude" / "worktrees" / "a" / "m.py", tmp_path)


class TestUnplaceablePaths:
    def test_a_path_outside_the_root_is_not_part_of_the_scan(self, tmp_path):
        """The fallback. Consulting SKIP_DIRS against an absolute path here
        would test the ROOT's ancestry — the exact bug this function removes —
        and would admit a symlink escape as scannable."""
        root = tmp_path / "project"
        root.mkdir()
        assert is_skipped_path(Path("/etc/passwd"), root)

    def test_a_symlink_escape_is_not_admitted(self, tmp_path):
        root = tmp_path / "project"
        (root / "pkg").mkdir(parents=True)
        outside = tmp_path / "elsewhere"
        outside.mkdir()
        (outside / "secret.py").write_text("x = 1\n", encoding="utf-8")
        link = root / "pkg" / "link.py"
        try:
            link.symlink_to(outside / "secret.py")
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable on this platform")

        assert is_skipped_path(link, root)

    def test_a_symlinked_root_still_resolves_its_own_files(self, tmp_path):
        """The direction that must keep working — over-eager skipping here is
        how a scan silently reports nothing."""
        real = tmp_path / "real"
        (real / "pkg").mkdir(parents=True)
        (real / "pkg" / "mod.py").write_text("x = 1\n", encoding="utf-8")
        link_root = tmp_path / "linked"
        try:
            link_root.symlink_to(real, target_is_directory=True)
        except (OSError, NotImplementedError):
            pytest.skip("symlinks unavailable on this platform")

        assert not is_skipped_path(real / "pkg" / "mod.py", link_root)


class TestTheSkipListItself:
    def test_the_worktree_names_are_present(self):
        """Their absence is what made every walk scan the repo ~26 times over,
        while the detector's docstring claimed they were pruned."""
        assert ".worktrees" in SKIP_DIRS
        assert "worktrees" in SKIP_DIRS
