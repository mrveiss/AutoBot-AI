# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for autobot_shared.repo_path.to_repo_relative (#11182)."""

from __future__ import annotations

from autobot_shared.repo_path import to_repo_relative


class TestToRepoRelative:
    """Tests for to_repo_relative()."""

    def test_production_code_source_absolute_path(self) -> None:
        """Absolute prod path under code_source/ is stripped to repo-relative."""
        result = to_repo_relative(
            "/opt/autobot/code_source/autobot-backend/services/x.py"
        )
        assert result == "autobot-backend/services/x.py"

    def test_already_relative_path_returned_unchanged(self) -> None:
        """A path without a leading slash is returned as-is."""
        result = to_repo_relative("autobot-backend/services/x.py")
        assert result == "autobot-backend/services/x.py"

    def test_dot_slash_prefix_canonicalised(self) -> None:
        """A "./"-prefixed relative path is canonicalised so it joins with the
        code_source-stripped form (#11182 join-key equality)."""
        assert to_repo_relative("./autobot-backend/services/x.py") == "autobot-backend/services/x.py"
        # Equal to the production absolute form after normalization.
        assert to_repo_relative("./autobot-backend/services/x.py") == to_repo_relative(
            "/opt/autobot/code_source/autobot-backend/services/x.py"
        )

    def test_stdlib_path_returns_none(self) -> None:
        """A stdlib path is out-of-repo and must return None."""
        result = to_repo_relative("/usr/lib/python3.10/json/__init__.py")
        assert result is None

    def test_site_packages_returns_none(self) -> None:
        """A site-packages path is third-party and must return None."""
        result = to_repo_relative(
            "/usr/local/lib/python3.11/site-packages/fastapi/routing.py"
        )
        assert result is None

    def test_venv_path_returns_none(self) -> None:
        """A path inside a .venv is out-of-repo and must return None."""
        result = to_repo_relative(
            "/home/user/project/.venv/lib/python3.11/site-packages/starlette/apps.py"
        )
        assert result is None

    def test_windows_backslash_separator_normalised(self) -> None:
        """Backslash separators are converted to forward slashes before matching."""
        result = to_repo_relative(
            "autobot-backend\\services\\failure_pattern_detector.py"
        )
        assert result == "autobot-backend/services/failure_pattern_detector.py"

    def test_code_source_with_nested_segments(self) -> None:
        """code_source/ anchor works even when prefix contains multiple path components."""
        result = to_repo_relative(
            "/srv/deploy/release/code_source/autobot_shared/repo_path.py"
        )
        assert result == "autobot_shared/repo_path.py"

    def test_empty_string_returns_none(self) -> None:
        """Empty string must return None, not raise."""
        assert to_repo_relative("") is None

    def test_absolute_path_without_anchor_returns_none(self) -> None:
        """An absolute path with no code_source/ segment and no out-of-repo marker
        still returns None — we cannot safely derive a repo root from it."""
        result = to_repo_relative("/some/unknown/absolute/path.py")
        assert result is None

    def test_dist_packages_returns_none(self) -> None:
        """dist-packages is treated as out-of-repo."""
        result = to_repo_relative("/usr/lib/python3/dist-packages/pkg/mod.py")
        assert result is None
