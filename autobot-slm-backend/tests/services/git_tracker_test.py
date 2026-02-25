# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for GitTracker service (Issue #741).
"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# Import git_tracker module directly without triggering services/__init__.py
git_tracker_path = Path(__file__).parent.parent.parent / "services" / "git_tracker.py"
spec = __import__("importlib.util").util.spec_from_file_location(
    "git_tracker", git_tracker_path
)
git_tracker = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(git_tracker)
GitTracker = git_tracker.GitTracker


class TestGitTracker:
    """Tests for GitTracker service."""

    def test_git_tracker_initialization(self):
        """Test GitTracker can be initialized with repo path."""
        tracker = GitTracker(repo_path="/path/to/repo")
        assert tracker.repo_path == "/path/to/repo"
        assert tracker.latest_commit is None

    @pytest.mark.asyncio
    async def test_get_local_commit_hash(self):
        """Test getting current commit hash from local repo."""
        tracker = GitTracker(repo_path="/home/kali/Desktop/AutoBot")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"abc123def456\n", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            commit = await tracker.get_local_commit()
            assert commit == "abc123def456"

    @pytest.mark.asyncio
    async def test_fetch_from_remote(self):
        """Test fetching updates from remote."""
        tracker = GitTracker(repo_path="/home/kali/Desktop/AutoBot")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            success = await tracker.fetch_remote()
            assert success is True

    @pytest.mark.asyncio
    async def test_get_remote_commit_hash(self):
        """Test getting latest commit hash from remote."""
        tracker = GitTracker(repo_path="/home/kali/Desktop/AutoBot")

        with patch("asyncio.create_subprocess_exec") as mock_exec:
            mock_process = AsyncMock()
            mock_process.communicate = AsyncMock(return_value=(b"def789ghi012\n", b""))
            mock_process.returncode = 0
            mock_exec.return_value = mock_process

            commit = await tracker.get_remote_commit(branch="main")
            assert commit == "def789ghi012"

    @pytest.mark.asyncio
    async def test_check_for_updates_no_update(self):
        """Test check_for_updates when already up to date."""
        tracker = GitTracker(repo_path="/home/kali/Desktop/AutoBot")

        with patch.object(tracker, "get_local_commit", return_value="abc123"):
            with patch.object(tracker, "fetch_remote", return_value=True):
                with patch.object(tracker, "get_remote_commit", return_value="abc123"):
                    result = await tracker.check_for_updates()

                    assert result["has_update"] is False
                    assert result["local_commit"] == "abc123"
                    assert result["remote_commit"] == "abc123"

    @pytest.mark.asyncio
    async def test_check_for_updates_update_available(self):
        """Test check_for_updates when update is available."""
        tracker = GitTracker(repo_path="/home/kali/Desktop/AutoBot")

        with patch.object(tracker, "get_local_commit", return_value="abc123"):
            with patch.object(tracker, "fetch_remote", return_value=True):
                with patch.object(tracker, "get_remote_commit", return_value="def456"):
                    result = await tracker.check_for_updates()

                    assert result["has_update"] is True
                    assert result["local_commit"] == "abc123"
                    assert result["remote_commit"] == "def456"
