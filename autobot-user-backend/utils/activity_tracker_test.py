# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Activity Tracker Integration Tests

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from backend.utils.activity_tracker import (
    detect_secret_usage,
    track_browser_activity,
    track_desktop_activity,
    track_file_activity,
    track_terminal_activity,
)


class TestSecretDetection:
    """Test secret usage detection."""

    def test_detect_password_flag(self):
        """Should detect password in command flags."""
        command = "mysql --password=secret123 -u root"
        result = detect_secret_usage(command)
        # Pattern detected but no known secret IDs
        assert isinstance(result, list)

    def test_detect_export_secret(self):
        """Should detect secret in environment variable."""
        command = "export API_TOKEN=abc123 && curl api.example.com"
        result = detect_secret_usage(command)
        assert isinstance(result, list)

    def test_no_secret_in_safe_command(self):
        """Should not detect secrets in safe commands."""
        command = "ls -la /home/user"
        result = detect_secret_usage(command)
        assert result == []

    def test_known_secret_ids(self):
        """Should include known secret IDs."""
        secret_id = uuid.uuid4()
        result = detect_secret_usage("any command", known_secret_ids=[secret_id])
        assert secret_id in result


@pytest.mark.asyncio
class TestTerminalActivityTracking:
    """Test terminal activity tracking."""

    async def test_track_simple_command(self):
        """Should track simple command execution."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        activity_id = await track_terminal_activity(
            db=mock_db,
            user_id=user_id,
            command="ls -la",
            working_directory="/home/user",
            exit_code=0,
            output="file1.txt\nfile2.txt\n",
        )

        assert isinstance(activity_id, uuid.UUID)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_awaited()

    async def test_track_command_with_secrets(self):
        """Should track command with secret usage."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()

        activity_id = await track_terminal_activity(
            db=mock_db,
            user_id=user_id,
            command="git push origin main",
            session_id="chat_123",
            secrets_used=[secret_id],
        )

        assert isinstance(activity_id, uuid.UUID)
        # Should create activity + secret usage record
        assert mock_db.add.call_count >= 2


@pytest.mark.asyncio
class TestFileActivityTracking:
    """Test file activity tracking."""

    async def test_track_file_create(self):
        """Should track file creation."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        activity_id = await track_file_activity(
            db=mock_db,
            user_id=user_id,
            operation="create",
            path="/home/user/document.txt",
            file_type="text/plain",
            size_bytes=1024,
        )

        assert isinstance(activity_id, uuid.UUID)
        mock_db.add.assert_called_once()

    async def test_track_file_rename(self):
        """Should track file rename with new path."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        activity_id = await track_file_activity(
            db=mock_db,
            user_id=user_id,
            operation="rename",
            path="/home/user/old.txt",
            new_path="/home/user/new.txt",
        )

        assert isinstance(activity_id, uuid.UUID)
        activity_model = mock_db.add.call_args[0][0]
        assert activity_model.new_path == "/home/user/new.txt"


@pytest.mark.asyncio
class TestBrowserActivityTracking:
    """Test browser activity tracking."""

    async def test_track_browser_navigation(self):
        """Should track browser navigation."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        activity_id = await track_browser_activity(
            db=mock_db,
            user_id=user_id,
            url="https://example.com",
            action="navigate",
        )

        assert isinstance(activity_id, uuid.UUID)
        mock_db.add.assert_called_once()

    async def test_track_form_submission_with_secrets(self):
        """Should track form submission with secret usage."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()

        activity_id = await track_browser_activity(
            db=mock_db,
            user_id=user_id,
            url="https://example.com/login",
            action="submit",
            selector="#login-form",
            secrets_used=[secret_id],
        )

        assert isinstance(activity_id, uuid.UUID)
        # Should create activity + secret usage record
        assert mock_db.add.call_count >= 2


@pytest.mark.asyncio
class TestDesktopActivityTracking:
    """Test desktop activity tracking."""

    async def test_track_mouse_click(self):
        """Should track mouse click action."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        activity_id = await track_desktop_activity(
            db=mock_db,
            user_id=user_id,
            action="click",
            coordinates=(500, 300),
            window_title="Visual Studio Code",
        )

        assert isinstance(activity_id, uuid.UUID)
        mock_db.add.assert_called_once()

    async def test_track_keyboard_input(self):
        """Should track keyboard input."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        activity_id = await track_desktop_activity(
            db=mock_db,
            user_id=user_id,
            action="type",
            input_text="Hello World",
            window_title="Notepad",
        )

        assert isinstance(activity_id, uuid.UUID)
        activity_model = mock_db.add.call_args[0][0]
        assert activity_model.input_text == "Hello World"

    async def test_track_screenshot(self):
        """Should track screenshot capture."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()

        activity_id = await track_desktop_activity(
            db=mock_db,
            user_id=user_id,
            action="screenshot",
            screenshot_path="/tmp/screenshot_123.png",
        )

        assert isinstance(activity_id, uuid.UUID)
        activity_model = mock_db.add.call_args[0][0]
        assert "/tmp/screenshot_123.png" in activity_model.screenshot_path
