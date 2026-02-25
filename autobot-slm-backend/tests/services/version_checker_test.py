# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Tests for Background Version Checker (Issue #741).
"""

import asyncio
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Import git_tracker module directly
git_tracker_path = Path(__file__).parent.parent.parent / "services" / "git_tracker.py"
spec = __import__("importlib.util").util.spec_from_file_location(
    "git_tracker", git_tracker_path
)
git_tracker_module = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(git_tracker_module)


class TestUpdateLatestVersionSetting:
    """Tests for update_latest_version_setting function."""

    @pytest.mark.asyncio
    async def test_update_creates_new_setting(self):
        """Test that update_latest_version_setting creates new setting if not exists."""
        # Mock database session
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # No existing setting
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Import the function from the module
        update_fn = git_tracker_module.update_latest_version_setting

        await update_fn(mock_db, "abc123def456")

        # Verify db.add was called with a Setting object
        assert mock_db.add.called
        # Verify commit was called
        assert mock_db.commit.called

    @pytest.mark.asyncio
    async def test_update_modifies_existing_setting(self):
        """Test that update_latest_version_setting updates existing setting."""
        # Mock database session with existing setting
        mock_db = AsyncMock()
        mock_setting = MagicMock()
        mock_setting.value = "old_hash"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_setting
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Import the function
        update_fn = git_tracker_module.update_latest_version_setting

        await update_fn(mock_db, "new_hash")

        # Verify setting value was updated
        assert mock_setting.value == "new_hash"
        # Verify commit was called
        assert mock_db.commit.called


class TestVersionCheckTask:
    """Tests for version_check_task background task."""

    @pytest.mark.asyncio
    async def test_task_calls_check_for_updates(self):
        """Test that version_check_task calls GitTracker.check_for_updates."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            with patch.object(git_tracker_module, "update_latest_version_setting"):
                with patch.object(git_tracker_module, "db_service") as mock_db_service:
                    mock_tracker = MagicMock()
                    mock_tracker.check_for_updates = AsyncMock(
                        return_value={
                            "has_update": False,
                            "local_commit": "abc123",
                            "remote_commit": "abc123",
                            "last_fetch": datetime.utcnow().isoformat(),
                        }
                    )
                    mock_get_tracker.return_value = mock_tracker

                    # Mock db_service.session as async context manager
                    mock_db_session = AsyncMock()
                    mock_session_ctx = AsyncMock()
                    mock_session_ctx.__aenter__.return_value = mock_db_session
                    mock_session_ctx.__aexit__.return_value = None
                    mock_db_service.session.return_value = mock_session_ctx

                    # Run task once
                    task = asyncio.create_task(
                        git_tracker_module.version_check_task(interval=0.1)
                    )
                    await asyncio.sleep(0.2)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                    # Verify check_for_updates was called
                    mock_tracker.check_for_updates.assert_called()

    @pytest.mark.asyncio
    async def test_task_updates_setting_on_success(self):
        """Test that version_check_task updates setting when remote commit is available."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            with patch.object(
                git_tracker_module, "update_latest_version_setting"
            ) as mock_update:
                with patch.object(git_tracker_module, "db_service") as mock_db_service:
                    mock_tracker = MagicMock()
                    mock_tracker.check_for_updates = AsyncMock(
                        return_value={
                            "has_update": False,
                            "local_commit": "abc123",
                            "remote_commit": "abc123",
                            "last_fetch": datetime.utcnow().isoformat(),
                        }
                    )
                    mock_get_tracker.return_value = mock_tracker

                    # Mock db_service session as async context manager
                    mock_db_session = AsyncMock()
                    mock_session_ctx = AsyncMock()
                    mock_session_ctx.__aenter__.return_value = mock_db_session
                    mock_session_ctx.__aexit__.return_value = None
                    mock_db_service.session.return_value = mock_session_ctx

                    # Run task once
                    task = asyncio.create_task(
                        git_tracker_module.version_check_task(interval=0.1)
                    )
                    await asyncio.sleep(0.2)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass

                    # Verify update_latest_version_setting was called
                    mock_update.assert_called_with(mock_db_session, "abc123")

    @pytest.mark.asyncio
    async def test_task_handles_no_remote_commit(self):
        """Test that version_check_task handles gracefully when remote commit is None."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            with patch.object(
                git_tracker_module, "update_latest_version_setting"
            ) as mock_update:
                mock_tracker = MagicMock()
                mock_tracker.check_for_updates = AsyncMock(
                    return_value={
                        "has_update": False,
                        "local_commit": None,
                        "remote_commit": None,
                        "last_fetch": None,
                    }
                )
                mock_get_tracker.return_value = mock_tracker

                # Run task once
                task = asyncio.create_task(
                    git_tracker_module.version_check_task(interval=0.1)
                )
                await asyncio.sleep(0.2)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

                # Verify check_for_updates was called
                mock_tracker.check_for_updates.assert_called()
                # Verify update was NOT called (remote commit was None)
                mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_handles_exception(self):
        """Test that version_check_task handles exceptions gracefully and continues running."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            mock_tracker = MagicMock()
            # First call raises exception, second call succeeds
            mock_tracker.check_for_updates = AsyncMock(
                side_effect=[
                    Exception("Git fetch failed"),
                    {
                        "has_update": False,
                        "local_commit": "abc123",
                        "remote_commit": "abc123",
                        "last_fetch": datetime.utcnow().isoformat(),
                    },
                ]
            )
            mock_get_tracker.return_value = mock_tracker

            # Run task for a bit
            task = asyncio.create_task(
                git_tracker_module.version_check_task(interval=0.1)
            )
            await asyncio.sleep(0.3)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

            # Verify it tried multiple times despite exception
            assert mock_tracker.check_for_updates.call_count >= 2

    @pytest.mark.asyncio
    async def test_task_logs_update_available(self):
        """Test that version_check_task logs when updates are detected."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            with patch.object(git_tracker_module, "logger") as mock_logger:
                with patch.object(git_tracker_module, "update_latest_version_setting"):
                    with patch.object(
                        git_tracker_module, "db_service"
                    ) as mock_db_service:
                        mock_tracker = MagicMock()
                        mock_tracker.check_for_updates = AsyncMock(
                            return_value={
                                "has_update": True,
                                "local_commit": "abc123",
                                "remote_commit": "def456",
                                "last_fetch": datetime.utcnow().isoformat(),
                            }
                        )
                        mock_get_tracker.return_value = mock_tracker

                        # Mock db_service
                        mock_db_session = AsyncMock()
                        mock_session_ctx = AsyncMock()
                        mock_session_ctx.__aenter__.return_value = mock_db_session
                        mock_session_ctx.__aexit__.return_value = None
                        mock_db_service.session.return_value = mock_session_ctx

                        # Run task once
                        task = asyncio.create_task(
                            git_tracker_module.version_check_task(interval=0.1)
                        )
                        await asyncio.sleep(0.2)
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass

                        # Verify info log was called about update
                        info_calls = [
                            str(call) for call in mock_logger.info.call_args_list
                        ]
                        assert any("Update available" in call for call in info_calls)


class TestStartVersionChecker:
    """Tests for start_version_checker function."""

    @pytest.mark.asyncio
    async def test_start_returns_task(self):
        """Test that start_version_checker returns an asyncio Task."""
        start_fn = git_tracker_module.start_version_checker
        task = start_fn(interval=0.1)

        assert isinstance(task, asyncio.Task)
        # Clean up
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_start_accepts_custom_params(self):
        """Test that start_version_checker accepts custom interval parameter.

        Issue #1185: repo_path removed — config now comes from CodeSource DB.
        """
        start_fn = git_tracker_module.start_version_checker

        custom_interval = 600
        task = start_fn(interval=custom_interval)

        assert isinstance(task, asyncio.Task)
        # Clean up
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
