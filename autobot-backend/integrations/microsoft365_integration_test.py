# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Unit Tests — Microsoft365Integration (Issue #9041)

Tests are isolated: all aiohttp calls are patched so no real network traffic occurs.
Tests cover Calendar, Outlook, and Teams operations via Microsoft Graph API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from integrations.base import IntegrationConfig, IntegrationStatus
from integrations.microsoft365_integration import Microsoft365Integration


def _make_config(**kwargs) -> IntegrationConfig:
    """Create test IntegrationConfig with Microsoft 365 defaults."""
    defaults = dict(
        name="Test M365",
        provider="microsoft365",
        token="mock123",
        base_url="https://graph.microsoft.com/v1.0",
    )
    defaults.update(kwargs)
    return IntegrationConfig(**defaults)


def _mock_session(status: int, body: dict | None = None):
    """Build a nested mock that mimics aiohttp.ClientSession context manager."""
    resp = AsyncMock()
    resp.status = status
    if body is not None:
        resp.json = AsyncMock(return_value=body)
    else:
        # For 204 No Content responses
        resp.json = AsyncMock(side_effect=Exception("No content"))

    cm_inner = AsyncMock()
    cm_inner.__aenter__ = AsyncMock(return_value=resp)
    cm_inner.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.request = MagicMock(return_value=cm_inner)

    cm_outer = MagicMock()
    cm_outer.__aenter__ = AsyncMock(return_value=mock_session)
    cm_outer.__aexit__ = AsyncMock(return_value=False)
    return cm_outer


@pytest.mark.asyncio
class TestMicrosoft365Integration:
    """Tests for Microsoft365Integration."""

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------

    @patch("aiohttp.ClientSession")
    async def test_test_connection_success(self, mock_session_cls):
        """Returns CONNECTED status on HTTP 200 from /me."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "userPrincipalName": "testuser@example.com",
                "displayName": "Test User",
                "id": "user-uuid",
            },
        )
        integration = Microsoft365Integration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.CONNECTED
        assert health.details["user"] == "testuser@example.com"
        assert health.details["display_name"] == "Test User"

    @patch("aiohttp.ClientSession")
    async def test_test_connection_unauthorized(self, mock_session_cls):
        """Returns UNAUTHORIZED status on HTTP 401."""
        mock_session_cls.return_value = _mock_session(
            401,
            {"error": {"message": "Invalid token"}},
        )
        integration = Microsoft365Integration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.UNAUTHORIZED
        assert "expired or invalid" in health.message

    @patch("aiohttp.ClientSession")
    async def test_test_connection_no_token(self, mock_session_cls):
        """Returns ERROR status when token is missing."""
        integration = Microsoft365Integration(_make_config(token=None))
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.ERROR
        assert "not configured" in health.message

    # ------------------------------------------------------------------
    # Calendar operations
    # ------------------------------------------------------------------

    @patch("aiohttp.ClientSession")
    async def test_list_calendar_events(self, mock_session_cls):
        """Successfully lists calendar events."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "value": [
                    {
                        "id": "event-1",
                        "subject": "Team Meeting",
                        "start": {"dateTime": "2026-06-01T10:00:00Z"},
                        "end": {"dateTime": "2026-06-01T11:00:00Z"},
                    }
                ]
            },
        )
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action(
            "list_calendar_events",
            {"start": "2026-06-01T00:00:00Z", "end": "2026-06-02T00:00:00Z"},
        )

        assert "value" in result
        assert len(result["value"]) == 1
        assert result["value"][0]["subject"] == "Team Meeting"

    @patch("aiohttp.ClientSession")
    async def test_create_calendar_event(self, mock_session_cls):
        """Successfully creates a calendar event."""
        mock_session_cls.return_value = _mock_session(
            201,
            {
                "id": "new-event-id",
                "subject": "New Meeting",
            },
        )
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action(
            "create_calendar_event",
            {
                "subject": "New Meeting",
                "start": "2026-06-01T14:00:00Z",
                "end": "2026-06-01T15:00:00Z",
                "attendees": ["attendee@example.com"],
            },
        )

        assert result["id"] == "new-event-id"
        assert result["subject"] == "New Meeting"

    @patch("aiohttp.ClientSession")
    async def test_delete_calendar_event(self, mock_session_cls):
        """Successfully deletes a calendar event."""
        mock_session_cls.return_value = _mock_session(204)
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action(
            "delete_calendar_event",
            {"event_id": "event-1"},
        )

        assert result["success"] is True

    # ------------------------------------------------------------------
    # Outlook email operations
    # ------------------------------------------------------------------

    @patch("aiohttp.ClientSession")
    async def test_list_messages(self, mock_session_cls):
        """Successfully lists inbox messages."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "value": [
                    {
                        "id": "msg-1",
                        "subject": "Test Email",
                        "from": {"emailAddress": {"address": "sender@example.com"}},
                    }
                ]
            },
        )
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action(
            "list_messages",
            {"limit": 50},
        )

        assert len(result["value"]) == 1
        assert result["value"][0]["subject"] == "Test Email"

    @patch("aiohttp.ClientSession")
    async def test_send_email(self, mock_session_cls):
        """Successfully sends an email."""
        mock_session_cls.return_value = _mock_session(202, {})
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action(
            "send_email",
            {
                "to": ["recipient@example.com"],
                "subject": "Test Subject",
                "body": "Test body content",
            },
        )

        assert result["success"] is True

    # ------------------------------------------------------------------
    # Teams operations
    # ------------------------------------------------------------------

    @patch("aiohttp.ClientSession")
    async def test_send_teams_message(self, mock_session_cls):
        """Successfully sends a Teams channel message."""
        mock_session_cls.return_value = _mock_session(
            201,
            {
                "id": "msg-id",
                "body": {"content": "Hello team"},
            },
        )
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action(
            "send_teams_message",
            {
                "team_id": "team-1",
                "channel_id": "channel-1",
                "content": "Hello team",
            },
        )

        assert result["id"] == "msg-id"

    @patch("aiohttp.ClientSession")
    async def test_list_teams(self, mock_session_cls):
        """Successfully lists joined teams."""
        mock_session_cls.return_value = _mock_session(
            200,
            {
                "value": [
                    {"id": "team-1", "displayName": "Engineering"},
                    {"id": "team-2", "displayName": "Marketing"},
                ]
            },
        )
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action("list_teams", {})

        assert len(result["value"]) == 2
        assert result["value"][0]["displayName"] == "Engineering"

    # ------------------------------------------------------------------
    # Error handling and metadata
    # ------------------------------------------------------------------

    async def test_execute_action_unknown(self):
        """Returns error dict for unknown action names."""
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action("invalid_action", {})
        assert "error" in result
        assert "Unknown action" in result["error"]

    def test_get_available_actions(self):
        """Returns all supported actions with proper metadata."""
        integration = Microsoft365Integration(_make_config())
        actions = integration.get_available_actions()

        action_names = [a.name for a in actions]

        # Calendar actions
        assert "list_calendar_events" in action_names
        assert "create_calendar_event" in action_names
        assert "delete_calendar_event" in action_names

        # Outlook actions
        assert "list_messages" in action_names
        assert "send_email" in action_names

        # Teams actions
        assert "send_teams_message" in action_names
        assert "list_teams" in action_names

        # Verify action structure
        create_event_action = next(a for a in actions if a.name == "create_calendar_event")
        assert create_event_action.method == "POST"
        assert "subject" in create_event_action.parameters
