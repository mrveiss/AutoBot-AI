# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Browser Tracking Integration Tests

Issue #873 - Activity Tracking Integration Hooks (#608 Phase 5)
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from backend.integrations.browser_tracking import (
    track_browser_action,
    track_browser_navigation,
    track_element_click,
    track_form_submission,
)


@pytest.mark.asyncio
class TestBrowserTracking:
    """Test browser activity tracking integration."""

    @patch("integrations.browser_tracking.track_browser_activity")
    async def test_track_browser_action_navigate(self, mock_track_browser):
        """Should track browser navigation."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_browser.return_value = activity_id

        result = await track_browser_action(
            db=mock_db,
            user_id=user_id,
            url="https://example.com",
            action="navigate",
            status_code=200,
        )

        assert result == activity_id
        mock_track_browser.assert_awaited_once()

        # Verify metadata includes status code
        call_kwargs = mock_track_browser.call_args.kwargs
        assert call_kwargs["metadata"]["status_code"] == 200

    @patch("integrations.browser_tracking.track_browser_activity")
    async def test_track_form_submission_with_secrets(self, mock_track_browser):
        """Should track form submission with secret usage."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        secret_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_browser.return_value = activity_id

        result = await track_form_submission(
            db=mock_db,
            user_id=user_id,
            url="https://example.com/login",
            form_selector="#login-form",
            secrets_used=[secret_id],
        )

        assert result == activity_id

        call_kwargs = mock_track_browser.call_args.kwargs
        assert call_kwargs["action"] == "submit"
        assert call_kwargs["selector"] == "#login-form"
        assert secret_id in call_kwargs["secrets_used"]

    @patch("integrations.browser_tracking.track_browser_activity")
    async def test_track_element_click(self, mock_track_browser):
        """Should track element click."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_browser.return_value = activity_id

        result = await track_element_click(
            db=mock_db,
            user_id=user_id,
            url="https://example.com",
            selector="button.submit",
        )

        assert result == activity_id

        call_kwargs = mock_track_browser.call_args.kwargs
        assert call_kwargs["action"] == "click"
        assert call_kwargs["selector"] == "button.submit"

    @patch("integrations.browser_tracking.track_browser_activity")
    async def test_track_navigation_helper(self, mock_track_browser):
        """Should use navigation helper."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_browser.return_value = activity_id

        result = await track_browser_navigation(
            db=mock_db,
            user_id=user_id,
            url="https://example.com/page",
            status_code=200,
        )

        assert result == activity_id

        call_kwargs = mock_track_browser.call_args.kwargs
        assert call_kwargs["action"] == "navigate"
        assert call_kwargs["metadata"]["status_code"] == 200

    @patch("integrations.browser_tracking.track_browser_activity")
    async def test_track_with_redirect(self, mock_track_browser):
        """Should track navigation with redirect."""
        mock_db = AsyncMock()
        user_id = uuid.uuid4()
        activity_id = uuid.uuid4()
        mock_track_browser.return_value = activity_id

        result = await track_browser_action(
            db=mock_db,
            user_id=user_id,
            url="https://example.com/old",
            action="navigate",
            status_code=302,
            redirect_url="https://example.com/new",
        )

        assert result == activity_id

        call_kwargs = mock_track_browser.call_args.kwargs
        assert call_kwargs["metadata"]["redirect_url"] == "https://example.com/new"
