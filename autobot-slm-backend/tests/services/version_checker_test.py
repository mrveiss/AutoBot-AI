# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Tests for Background Version Checker (Issue #741).
"""

import asyncio
import contextlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from autobot_shared.eventually import eventually
from autobot_shared.time_utils import utc_timestamp

# Import git_tracker module directly
git_tracker_path = Path(__file__).parent.parent.parent / "services" / "git_tracker.py"
spec = __import__("importlib.util").util.spec_from_file_location("git_tracker", git_tracker_path)
git_tracker_module = __import__("importlib.util").util.module_from_spec(spec)
spec.loader.exec_module(git_tracker_module)


async def _run_loop_until(condition, loop=None) -> None:
    """Run the version-check loop until *condition()* holds, then stop it (#16009).

    Waits on what each test asserts instead of sleeping a fixed 0.2-0.3 s: a busy
    runner makes this slower, never red, and a loop that dies surfaces its own
    exception through ``eventually(watch=...)`` instead of a short call count.
    """
    task = asyncio.create_task((loop or git_tracker_module.version_check_task)(interval=0.1))
    try:
        await eventually(condition, watch=task)
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


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

    @pytest.fixture(autouse=True)
    def _local_checkout(self, tmp_path, monkeypatch):
        """Give the loop a real git working tree to track.

        version_check_task skips its entire body when the active CodeSource
        path has no .git directory (#9716). These tests never established that
        precondition, so they fell through to DEFAULT_REPO_PATH and read the
        host's own deployed checkout: green on a developer box that has one,
        red on a CI runner that does not (#13162).
        """
        code_source = tmp_path / "code_source"
        (code_source / ".git").mkdir(parents=True)

        async def _active_config():
            return str(code_source), "Dev_new_gui"

        monkeypatch.setattr(git_tracker_module, "_get_active_code_source_config", _active_config)
        monkeypatch.setattr(git_tracker_module, "_missing_repo_warned", False)
        return code_source

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
                            "last_fetch": utc_timestamp(),
                        }
                    )
                    mock_get_tracker.return_value = mock_tracker

                    # Mock db_service.session as async context manager
                    mock_db_session = AsyncMock()
                    mock_session_ctx = AsyncMock()
                    mock_session_ctx.__aenter__.return_value = mock_db_session
                    mock_session_ctx.__aexit__.return_value = None
                    mock_db_service.session.return_value = mock_session_ctx

                    await _run_loop_until(lambda: mock_tracker.check_for_updates.await_count >= 1)

                    # Verify check_for_updates was called
                    mock_tracker.check_for_updates.assert_called()

    @pytest.mark.asyncio
    async def test_task_updates_setting_on_success(self):
        """Test that version_check_task updates setting when remote commit is available."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            with patch.object(git_tracker_module, "update_latest_version_setting") as mock_update:
                with patch.object(git_tracker_module, "db_service") as mock_db_service:
                    mock_tracker = MagicMock()
                    mock_tracker.check_for_updates = AsyncMock(
                        return_value={
                            "has_update": False,
                            "local_commit": "abc123",
                            "remote_commit": "abc123",
                            "last_fetch": utc_timestamp(),
                        }
                    )
                    mock_get_tracker.return_value = mock_tracker

                    # Mock db_service session as async context manager
                    mock_db_session = AsyncMock()
                    mock_session_ctx = AsyncMock()
                    mock_session_ctx.__aenter__.return_value = mock_db_session
                    mock_session_ctx.__aexit__.return_value = None
                    mock_db_service.session.return_value = mock_session_ctx

                    await _run_loop_until(lambda: mock_update.called)

                    # Verify update_latest_version_setting was called
                    mock_update.assert_called_with(mock_db_session, "abc123")

    @pytest.mark.asyncio
    async def test_task_handles_no_remote_commit(self):
        """Test that version_check_task handles gracefully when remote commit is None."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            with patch.object(git_tracker_module, "update_latest_version_setting") as mock_update:
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

                # Two checks: the first iteration ran to completion, so the no-update
                # assertion below is about a finished branch, not an interrupted one.
                await _run_loop_until(lambda: mock_tracker.check_for_updates.await_count >= 2)

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
                        "last_fetch": utc_timestamp(),
                    },
                ]
            )
            mock_get_tracker.return_value = mock_tracker

            await _run_loop_until(lambda: mock_tracker.check_for_updates.await_count >= 2)

            # Verify it tried multiple times despite exception
            assert mock_tracker.check_for_updates.call_count >= 2

    @pytest.mark.asyncio
    async def test_a_loop_that_lets_the_exception_escape_fails_the_wait(self):
        """#16009 AC2 stand-in: were the loop's ``except`` to re-raise, the first
        ``check_for_updates`` failure would end the task. The wait must then fail
        with that failure -- not pass on a short count, and not merely time out."""
        check = AsyncMock(side_effect=Exception("Git fetch failed"))

        async def loop_without_except(interval: float) -> None:
            while True:
                await check()
                await asyncio.sleep(interval)

        with pytest.raises(Exception, match="Git fetch failed"):
            await _run_loop_until(lambda: check.await_count >= 2, loop=loop_without_except)

    @pytest.mark.asyncio
    async def test_task_logs_update_available(self):
        """Test that version_check_task logs when updates are detected."""
        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            with patch.object(git_tracker_module, "logger") as mock_logger:
                with patch.object(git_tracker_module, "update_latest_version_setting"):
                    with patch.object(git_tracker_module, "db_service") as mock_db_service:
                        mock_tracker = MagicMock()
                        mock_tracker.check_for_updates = AsyncMock(
                            return_value={
                                "has_update": True,
                                "local_commit": "abc123",
                                "remote_commit": "def456",
                                "last_fetch": utc_timestamp(),
                            }
                        )
                        mock_get_tracker.return_value = mock_tracker

                        # Mock db_service
                        mock_db_session = AsyncMock()
                        mock_session_ctx = AsyncMock()
                        mock_session_ctx.__aenter__.return_value = mock_db_session
                        mock_session_ctx.__aexit__.return_value = None
                        mock_db_service.session.return_value = mock_session_ctx

                        await _run_loop_until(
                            lambda: any("Update available" in str(c) for c in mock_logger.info.call_args_list)
                        )

                        # Verify info log was called about update
                        info_calls = [str(call) for call in mock_logger.info.call_args_list]
                        assert any("Update available" in call for call in info_calls)

    @pytest.mark.asyncio
    async def test_task_skips_when_no_local_checkout(self, tmp_path, monkeypatch):
        """No .git under the active CodeSource path → no git work at all (#9716).

        Pins the gate that made every other test in this class depend on the
        host filesystem (#13162): deployments without a local checkout must not
        build a tracker or shell out to git on every interval.
        """
        no_checkout = tmp_path / "no_checkout"
        no_checkout.mkdir()

        async def _active_config():
            return str(no_checkout), "Dev_new_gui"

        monkeypatch.setattr(git_tracker_module, "_get_active_code_source_config", _active_config)

        with patch.object(git_tracker_module, "get_git_tracker") as mock_get_tracker:
            task = asyncio.create_task(git_tracker_module.version_check_task(interval=0.1))
            await asyncio.sleep(0.2)
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        mock_get_tracker.assert_not_called()


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
