# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Activity Tracker Integration Tests

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)

#16466 retired the terminal/file/browser tests alongside the module code
they exercised (dead: zero callers anywhere in the backend). Only desktop
tracking was ever actually wired (integrations/desktop_tracking.py ->
api/vnc_proxy.py), so only its tests remain.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from utils.activity_tracker import track_desktop_activity


@pytest.mark.asyncio
class TestDesktopActivityTracking:
    """Test desktop activity tracking."""

    async def test_track_mouse_click(self):
        """Should track mouse click action."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()  # AsyncSession.add() is sync (#11954)
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
        mock_db.add = MagicMock()  # AsyncSession.add() is sync (#11954)
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
        mock_db.add = MagicMock()  # AsyncSession.add() is sync (#11954)
        user_id = uuid.uuid4()

        activity_id = await track_desktop_activity(
            db=mock_db,
            user_id=user_id,
            action="screenshot",
            screenshot_path="/tmp/screenshot_123.png",  # nosec B108  # test/controlled code uses tmpdir intentionally
        )

        assert isinstance(activity_id, uuid.UUID)
        activity_model = mock_db.add.call_args[0][0]
        assert (
            "/tmp/screenshot_123.png"
            in activity_model.screenshot_path  # nosec B108  # test/controlled code uses tmpdir intentionally
        )
