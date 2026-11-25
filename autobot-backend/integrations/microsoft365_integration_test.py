# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit Tests — Microsoft365Integration (Issue #9041)

Tests are isolated: all HTTP calls are patched so no real network traffic occurs.
Tests cover Calendar, Outlook, and Teams operations via Microsoft Graph API.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
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


def _mock_client(status: int, body: dict | None = None):
    """Build a mock ``HTTPClientManager`` whose ``tracked_request()`` yields a
    response mimicking the given status/body.

    Issue #12979: ``_make_graph_request`` routes through the shared pool's
    ``get_http_client().tracked_request(method, url, **kwargs)`` rather than
    constructing its own ``aiohttp.ClientSession`` — the ``async with`` here
    is entered/exited by ``tracked_request()`` on the real client, so the
    mock only needs to reproduce ``__aenter__``/``__aexit__`` on the value
    returned directly by a patched ``get_http_client()``.
    """
    resp = AsyncMock()
    resp.status = status
    if body is not None:
        resp.json = AsyncMock(return_value=body)
    else:
        # For 204 No Content responses
        resp.json = AsyncMock(side_effect=Exception("No content"))

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=resp)
    cm.__aexit__ = AsyncMock(return_value=False)

    mock_client = MagicMock()
    mock_client.tracked_request = MagicMock(return_value=cm)
    return mock_client


@pytest.mark.asyncio
class TestMicrosoft365Integration:
    """Tests for Microsoft365Integration."""

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_test_connection_success(self, mock_get_client):
        """Returns CONNECTED on HTTP 200, probing a mail endpoint the Mail.* grant covers (not /me)."""
        mock_get_client.return_value = _mock_client(200, {"value": []})
        integration = Microsoft365Integration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.CONNECTED
        call = mock_get_client.return_value.tracked_request.call_args
        assert call.args[1].endswith("/me/mailFolders")
        assert call.kwargs["params"] == {"$top": 1}

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_test_connection_unauthorized(self, mock_get_client):
        """Returns UNAUTHORIZED status on HTTP 401."""
        mock_get_client.return_value = _mock_client(
            401,
            {"error": {"message": "Invalid token"}},
        )
        integration = Microsoft365Integration(_make_config())
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.UNAUTHORIZED
        assert "expired or invalid" in health.message

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_test_connection_no_token(self, mock_get_client):
        """Returns ERROR status when token is missing."""
        integration = Microsoft365Integration(_make_config(token=None))
        health = await integration.test_connection()

        assert health.status == IntegrationStatus.ERROR
        assert "not configured" in health.message

    # ------------------------------------------------------------------
    # Calendar operations
    # ------------------------------------------------------------------

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_list_calendar_events(self, mock_get_client):
        """Successfully lists calendar events."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_create_calendar_event(self, mock_get_client):
        """Successfully creates a calendar event."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_delete_calendar_event(self, mock_get_client):
        """Successfully deletes a calendar event."""
        mock_get_client.return_value = _mock_client(204)
        integration = Microsoft365Integration(_make_config())
        result = await integration.execute_action(
            "delete_calendar_event",
            {"event_id": "event-1"},
        )

        assert result["success"] is True

    # ------------------------------------------------------------------
    # Outlook email operations
    # ------------------------------------------------------------------

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_list_messages(self, mock_get_client):
        """Successfully lists inbox messages."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_send_email(self, mock_get_client):
        """Successfully sends an email."""
        mock_get_client.return_value = _mock_client(202, {})
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

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_send_teams_message(self, mock_get_client):
        """Successfully sends a Teams channel message."""
        mock_get_client.return_value = _mock_client(
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

    @patch("integrations.microsoft365_integration.get_http_client")
    async def test_list_teams(self, mock_get_client):
        """Successfully lists joined teams."""
        mock_get_client.return_value = _mock_client(
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action,params",
    [("list_messages", {}), ("search_messages", {"query": "x"}), ("list_folders", {})],
)
@patch("integrations.microsoft365_integration.get_http_client")
async def test_read_action_transport_failure_is_an_error_not_an_empty_body(mock_get_client, action, params):
    """A Graph transport failure (status 0) must not read as an empty mailbox."""
    mock_get_client.return_value.tracked_request.side_effect = aiohttp.ClientError("unreachable")
    result = await Microsoft365Integration(_make_config()).execute_action(action, params)
    assert result["status_code"] == 0 and "unreachable" in result["error"]
    assert "value" not in result


@pytest.mark.asyncio
@patch("integrations.microsoft365_integration.get_http_client")
async def test_read_action_http_error_carries_status(mock_get_client):
    mock_get_client.return_value = _mock_client(503, {"error": {"message": "busy"}})
    result = await Microsoft365Integration(_make_config()).execute_action("list_folders", {})
    assert result == {"error": "busy", "status_code": 503}
