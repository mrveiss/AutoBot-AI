# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Desktop Tracking Integration Tests

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.integrations.desktop_tracking import (
    track_desktop_action,
    track_keyboard_input,
    track_mouse_click,
    track_screenshot_capture,
    track_window_focus,
)


@pytest.mark.asyncio
class TestDesktopTracking:
    """Test desktop activity tracking integration."""

    @patch("integrations.desktop_tracking.track_desktop_activity")
    async def test_track_desktop_action_click(self, mock_track_desktop):
        """Should track desktop click action."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_desktop.return_value = activity_id

        result = await track_desktop_action(
            db=mock_db,
            user_id=user_id,
            action="click",
            coordinates=(500, 300),
            window_title="Visual Studio Code",
        )

        assert result == activity_id
        mock_track_desktop.assert_awaited_once()

    @patch("integrations.desktop_tracking.track_desktop_activity")
    async def test_track_mouse_click_helper(self, mock_track_desktop):
        """Should track mouse click using helper."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_desktop.return_value = activity_id

        result = await track_mouse_click(
            db=mock_db,
            user_id=user_id,
            x=500,
            y=300,
            window_title="Terminal",
        )

        assert result == activity_id

        call_kwargs = mock_track_desktop.call_args.kwargs
        assert call_kwargs["action"] == "click"
        assert call_kwargs["coordinates"] == (500, 300)
        assert call_kwargs["window_title"] == "Terminal"

    @patch("integrations.desktop_tracking.track_desktop_activity")
    async def test_track_keyboard_input_helper(self, mock_track_desktop):
        """Should track keyboard input using helper."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_desktop.return_value = activity_id

        result = await track_keyboard_input(
            db=mock_db,
            user_id=user_id,
            text="Hello World",
            window_title="Notepad",
        )

        assert result == activity_id

        call_kwargs = mock_track_desktop.call_args.kwargs
        assert call_kwargs["action"] == "type"
        assert call_kwargs["input_text"] == "Hello World"

    @patch("integrations.desktop_tracking.track_desktop_activity")
    async def test_track_screenshot_capture_helper(self, mock_track_desktop):
        """Should track screenshot capture using helper."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_desktop.return_value = activity_id

        result = await track_screenshot_capture(
            db=mock_db,
            user_id=user_id,
            screenshot_path="/tmp/screenshot.png",
        )

        assert result == activity_id

        call_kwargs = mock_track_desktop.call_args.kwargs
        assert call_kwargs["action"] == "screenshot"
        assert call_kwargs["screenshot_path"] == "/tmp/screenshot.png"

    @patch("integrations.desktop_tracking.track_desktop_activity")
    async def test_track_window_focus_helper(self, mock_track_desktop):
        """Should track window focus using helper."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_desktop.return_value = activity_id

        result = await track_window_focus(
            db=mock_db,
            user_id=user_id,
            window_title="Firefox",
            app_name="firefox",
        )

        assert result == activity_id

        call_kwargs = mock_track_desktop.call_args.kwargs
        assert call_kwargs["action"] == "window_focus"
        assert call_kwargs["window_title"] == "Firefox"
        assert call_kwargs["metadata"]["app"] == "firefox"

    @patch("integrations.desktop_tracking.track_desktop_activity")
    async def test_track_with_session_id(self, mock_track_desktop):
        """Should track desktop action with session context."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        session_id = "chat_abc123"
        activity_id = uuid.uuid4()
        mock_track_desktop.return_value = activity_id

        result = await track_desktop_action(
            db=mock_db,
            user_id=user_id,
            action="click",
            session_id=session_id,
            coordinates=(100, 200),
        )

        assert result == activity_id

        call_kwargs = mock_track_desktop.call_args.kwargs
        assert call_kwargs["session_id"] == session_id
