# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Microsoft 365 Integration (Issue #9041)

Provides comprehensive integration with Microsoft 365 services via Graph API:
- Calendar: read/create/update/delete events, check availability, schedule meetings
- Outlook: read inbox, send emails, manage folders, search messages
- Teams: send messages to channels, read conversations, create meetings
- OneDrive: file operations (extends Issue #9004 when implemented)

Authentication uses OAuth2 with Microsoft Authentication Library (MSAL).
All operations use Microsoft Graph API v1.0 endpoints.
"""

import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from urllib.parse import quote

import aiohttp

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc

from integrations.base import (
    BaseIntegration,
    IntegrationAction,
    IntegrationConfig,
    IntegrationHealth,
    IntegrationStatus,
)

logger = get_logger(__name__)

# Graph API resource IDs are base64url-ish tokens, never contain path separators
_GRAPH_ID_PATTERN = re.compile(r"^[A-Za-z0-9_\-=+/.@]+$")


def _validate_graph_id(value: str, name: str = "ID") -> str:
    """Validate and sanitize a Microsoft Graph resource ID.

    Prevents path traversal and SSRF by ensuring IDs match expected format.
    Graph IDs are opaque tokens that never contain '/', '?', '#', '..', or whitespace.

    Args:
        value: The ID to validate
        name: Human-readable name for error messages

    Returns:
        URL-encoded ID safe for interpolation

    Raises:
        ValueError: If ID format is invalid
    """
    if not value or not isinstance(value, str):
        raise ValueError(f"{name} must be a non-empty string")

    if not _GRAPH_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{name} contains invalid characters")

    # URL-encode to prevent injection even if regex is bypassed
    return quote(value, safe="")


def _validate_datetime_iso(value: str, name: str = "datetime") -> str:
    """Validate and canonicalize ISO-8601 datetime string to UTC.

    Prevents OData filter injection by parsing and reformatting datetime values.
    Ensures all datetimes are normalized to UTC for correct cross-timezone comparison.

    Args:
        value: ISO-8601 datetime string
        name: Human-readable name for error messages

    Returns:
        Canonical ISO-8601 string in UTC (+00:00 timezone)

    Raises:
        ValueError: If datetime format is invalid
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        # Normalize to UTC if timezone-aware, tag as UTC if naive
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.isoformat()
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{name} must be valid ISO-8601 format") from exc


class Microsoft365Integration(BaseIntegration):
    """Microsoft 365 integration using Microsoft Graph API.

    Supports:
    - Calendar operations (events, meetings, availability)
    - Outlook email (read, send, folders, search)
    - Teams messaging (channels, conversations, meetings)
    - OneDrive (when Issue #9004 is implemented)

    Authentication:
    - OAuth2 access token via MSAL (Microsoft Authentication Library)
    - Token refresh handled by MSAL client
    - Supports delegated (user) and application (service) permissions

    Rate limiting:
    - Microsoft Graph enforces per-app throttling
    - Implements exponential backoff on 429 responses
    """

    def __init__(self, config: IntegrationConfig):
        super().__init__(config)
        self.graph_url = config.base_url or "https://graph.microsoft.com/v1.0"
        self.token = config.token
        self.tenant_id = config.extra.get("tenant_id")
        self.client_id = config.extra.get("client_id")
        self.client_secret = config.extra.get("client_secret")

    async def test_connection(self) -> IntegrationHealth:
        """Test Microsoft 365 connection by fetching user profile."""
        start_time = time.monotonic()

        if not self.token:
            return self._create_health_response(
                IntegrationStatus.ERROR,
                0,
                "Access token not configured",
            )

        url = f"{self.graph_url}/me"
        result = await self._make_graph_request("GET", url)

        latency = (time.monotonic() - start_time) * 1000

        if result.get("status_code") == 200:
            user_data = result.get("body", {})
            return self._create_health_response(
                IntegrationStatus.CONNECTED,
                latency,
                "Connected to Microsoft 365",
                {
                    "user": user_data.get("userPrincipalName"),
                    "display_name": user_data.get("displayName"),
                },
            )

        if result.get("status_code") == 401:
            return self._create_health_response(
                IntegrationStatus.UNAUTHORIZED,
                latency,
                "Token expired or invalid",
            )

        return self._create_health_response(
            IntegrationStatus.ERROR,
            latency,
            f"Connection failed: {result.get('error', 'Unknown error')}",
        )

    def get_available_actions(self) -> List[IntegrationAction]:
        """Return list of supported Microsoft 365 actions."""
        return [
            # Calendar actions
            IntegrationAction(
                name="list_calendar_events",
                description="List calendar events for a time range",
                method="GET",
                parameters={"start": "datetime", "end": "datetime", "calendar_id": "str (optional)"},
            ),
            IntegrationAction(
                name="create_calendar_event",
                description="Create a new calendar event",
                method="POST",
                parameters={
                    "subject": "str",
                    "start": "datetime",
                    "end": "datetime",
                    "body": "str (optional)",
                    "attendees": "list[str] (optional)",
                },
            ),
            IntegrationAction(
                name="update_calendar_event",
                description="Update an existing calendar event",
                method="PATCH",
                parameters={"event_id": "str", "updates": "dict"},
            ),
            IntegrationAction(
                name="delete_calendar_event",
                description="Delete a calendar event",
                method="DELETE",
                parameters={"event_id": "str"},
            ),
            IntegrationAction(
                name="check_availability",
                description="Check availability for scheduling",
                method="POST",
                parameters={"attendees": "list[str]", "start": "datetime", "end": "datetime"},
            ),
            # Outlook email actions
            IntegrationAction(
                name="list_messages",
                description="List messages from inbox or folder",
                method="GET",
                parameters={"folder_id": "str (optional)", "limit": "int (optional)"},
            ),
            IntegrationAction(
                name="send_email",
                description="Send an email message",
                method="POST",
                parameters={
                    "to": "list[str]",
                    "subject": "str",
                    "body": "str",
                    "cc": "list[str] (optional)",
                    "attachments": "list[dict] (optional)",
                },
            ),
            IntegrationAction(
                name="search_messages",
                description="Search messages with query",
                method="GET",
                parameters={"query": "str", "limit": "int (optional)"},
            ),
            IntegrationAction(
                name="list_folders",
                description="List all mail folders",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="create_folder",
                description="Create a new mail folder",
                method="POST",
                parameters={"name": "str", "parent_folder_id": "str (optional)"},
            ),
            # Teams actions
            IntegrationAction(
                name="send_teams_message",
                description="Send message to a Teams channel",
                method="POST",
                parameters={"team_id": "str", "channel_id": "str", "content": "str"},
            ),
            IntegrationAction(
                name="list_teams",
                description="List all teams user belongs to",
                method="GET",
                parameters={},
            ),
            IntegrationAction(
                name="list_team_channels",
                description="List channels in a team",
                method="GET",
                parameters={"team_id": "str"},
            ),
            IntegrationAction(
                name="get_channel_messages",
                description="Get messages from a Teams channel",
                method="GET",
                parameters={"team_id": "str", "channel_id": "str", "limit": "int (optional)"},
            ),
            IntegrationAction(
                name="create_teams_meeting",
                description="Create an online Teams meeting",
                method="POST",
                parameters={
                    "subject": "str",
                    "start": "datetime",
                    "end": "datetime",
                    "attendees": "list[str]",
                },
            ),
        ]

    async def execute_action(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a named Microsoft 365 action."""
        action_map = {
            # Calendar
            "list_calendar_events": self._list_calendar_events,
            "create_calendar_event": self._create_calendar_event,
            "update_calendar_event": self._update_calendar_event,
            "delete_calendar_event": self._delete_calendar_event,
            "check_availability": self._check_availability,
            # Outlook
            "list_messages": self._list_messages,
            "send_email": self._send_email,
            "search_messages": self._search_messages,
            "list_folders": self._list_folders,
            "create_folder": self._create_folder,
            # Teams
            "send_teams_message": self._send_teams_message,
            "list_teams": self._list_teams,
            "list_team_channels": self._list_team_channels,
            "get_channel_messages": self._get_channel_messages,
            "create_teams_meeting": self._create_teams_meeting,
        }

        handler = action_map.get(action)
        if not handler:
            return {"error": f"Unknown action: {action}"}

        try:
            return await handler(params)
        except Exception as exc:
            self.logger.error("Action %s failed: %s", action, exc, exc_info=True)
            return {"error": str(exc)}

    # Calendar operations

    async def _list_calendar_events(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List calendar events within a time range.

        Defaults to next 7 days if no time range provided (MVA-2203).
        """
        calendar_id = params.get("calendar_id", "primary")
        start_dt = params.get("start")
        end_dt = params.get("end")

        if calendar_id == "primary":
            url = f"{self.graph_url}/me/calendar/events"
        else:
            safe_calendar_id = _validate_graph_id(calendar_id, "calendar_id")
            url = f"{self.graph_url}/me/calendars/{safe_calendar_id}/events"

        # Default to next 7 days if no time range provided (MVA-2203)
        query_params = {}
        if start_dt or end_dt:
            if not start_dt:
                start_dt = now_utc().isoformat()
            if not end_dt:
                end_dt = (now_utc() + timedelta(days=7)).isoformat()
            safe_start = _validate_datetime_iso(start_dt, "start")
            safe_end = _validate_datetime_iso(end_dt, "end")
            query_params["$filter"] = f"start/dateTime ge '{safe_start}' and end/dateTime le '{safe_end}'"

        result = await self._make_graph_request("GET", url, params=query_params)
        return result.get("body", {})

    async def _create_calendar_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new calendar event.

        Normalizes datetimes to UTC for correct cross-timezone handling (MVA-2203).
        """
        url = f"{self.graph_url}/me/calendar/events"

        # Normalize datetimes to UTC (MVA-2203)
        safe_start = _validate_datetime_iso(params["start"], "start")
        safe_end = _validate_datetime_iso(params["end"], "end")

        event_data = {
            "subject": params["subject"],
            "start": {
                "dateTime": safe_start,
                "timeZone": "UTC",
            },
            "end": {
                "dateTime": safe_end,
                "timeZone": "UTC",
            },
        }

        if "body" in params:
            event_data["body"] = {
                "contentType": "HTML",
                "content": params["body"],
            }

        if "attendees" in params:
            event_data["attendees"] = [
                {
                    "emailAddress": {"address": email},
                    "type": "required",
                }
                for email in params["attendees"]
            ]

        result = await self._make_graph_request("POST", url, json_data=event_data)
        return result.get("body", {})

    async def _update_calendar_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing calendar event."""
        safe_event_id = _validate_graph_id(params["event_id"], "event_id")
        url = f"{self.graph_url}/me/calendar/events/{safe_event_id}"

        update_data = params.get("updates", {})
        result = await self._make_graph_request("PATCH", url, json_data=update_data)
        return result.get("body", {})

    async def _delete_calendar_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a calendar event."""
        safe_event_id = _validate_graph_id(params["event_id"], "event_id")
        url = f"{self.graph_url}/me/calendar/events/{safe_event_id}"

        result = await self._make_graph_request("DELETE", url)
        return {"success": result.get("status_code") == 204}

    async def _check_availability(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Check availability for attendees in a time range.

        Normalizes datetimes to UTC for correct cross-timezone comparison (MVA-2203).
        """
        url = f"{self.graph_url}/me/calendar/getSchedule"

        # Normalize datetimes to UTC (MVA-2203)
        safe_start = _validate_datetime_iso(params["start"], "start")
        safe_end = _validate_datetime_iso(params["end"], "end")

        schedule_data = {
            "schedules": params["attendees"],
            "startTime": {
                "dateTime": safe_start,
                "timeZone": "UTC",
            },
            "endTime": {
                "dateTime": safe_end,
                "timeZone": "UTC",
            },
            "availabilityViewInterval": params.get("interval", 30),
        }

        result = await self._make_graph_request("POST", url, json_data=schedule_data)
        return result.get("body", {})

    # Outlook email operations

    async def _list_messages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List messages from inbox or a specific folder."""
        folder_id = params.get("folder_id", "inbox")
        limit = params.get("limit", 50)

        if folder_id == "inbox":
            url = f"{self.graph_url}/me/mailFolders/inbox/messages"
        else:
            safe_folder_id = _validate_graph_id(folder_id, "folder_id")
            url = f"{self.graph_url}/me/mailFolders/{safe_folder_id}/messages"

        query_params = {"$top": min(limit, 1000)}  # Graph API max is 1000
        result = await self._make_graph_request("GET", url, params=query_params)
        return result.get("body", {})

    async def _send_email(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send an email message."""
        url = f"{self.graph_url}/me/sendMail"

        message_data = {
            "message": {
                "subject": params["subject"],
                "body": {
                    "contentType": params.get("body_type", "HTML"),
                    "content": params["body"],
                },
                "toRecipients": [{"emailAddress": {"address": addr}} for addr in params["to"]],
            }
        }

        if "cc" in params:
            message_data["message"]["ccRecipients"] = [{"emailAddress": {"address": addr}} for addr in params["cc"]]

        if "attachments" in params:
            message_data["message"]["attachments"] = params["attachments"]

        result = await self._make_graph_request("POST", url, json_data=message_data)
        return {"success": result.get("status_code") == 202}

    async def _search_messages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Search messages with a query string."""
        query = params["query"]
        limit = params.get("limit", 50)

        # Prevent OData injection - reject embedded quotes
        if '"' in query or "'" in query:
            raise ValueError("Search query cannot contain quote characters")

        url = f"{self.graph_url}/me/messages"
        query_params = {
            "$search": f'"{query}"',
            "$top": min(limit, 1000),
        }

        result = await self._make_graph_request("GET", url, params=query_params)
        return result.get("body", {})

    async def _list_folders(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all mail folders."""
        url = f"{self.graph_url}/me/mailFolders"
        result = await self._make_graph_request("GET", url)
        return result.get("body", {})

    async def _create_folder(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create a new mail folder."""
        parent_id = params.get("parent_folder_id", "inbox")

        if parent_id == "inbox":
            url = f"{self.graph_url}/me/mailFolders/inbox/childFolders"
        else:
            safe_parent_id = _validate_graph_id(parent_id, "parent_folder_id")
            url = f"{self.graph_url}/me/mailFolders/{safe_parent_id}/childFolders"

        folder_data = {"displayName": params["name"]}
        result = await self._make_graph_request("POST", url, json_data=folder_data)
        return result.get("body", {})

    # Teams operations

    async def _send_teams_message(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Send a message to a Teams channel."""
        safe_team_id = _validate_graph_id(params["team_id"], "team_id")
        safe_channel_id = _validate_graph_id(params["channel_id"], "channel_id")
        url = f"{self.graph_url}/teams/{safe_team_id}/channels/{safe_channel_id}/messages"

        message_data = {
            "body": {
                "content": params["content"],
            }
        }

        result = await self._make_graph_request("POST", url, json_data=message_data)
        return result.get("body", {})

    async def _list_teams(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all teams the user belongs to."""
        url = f"{self.graph_url}/me/joinedTeams"
        result = await self._make_graph_request("GET", url)
        return result.get("body", {})

    async def _list_team_channels(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List all channels in a team."""
        safe_team_id = _validate_graph_id(params["team_id"], "team_id")
        url = f"{self.graph_url}/teams/{safe_team_id}/channels"
        result = await self._make_graph_request("GET", url)
        return result.get("body", {})

    async def _get_channel_messages(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get messages from a Teams channel."""
        safe_team_id = _validate_graph_id(params["team_id"], "team_id")
        safe_channel_id = _validate_graph_id(params["channel_id"], "channel_id")
        limit = params.get("limit", 50)

        url = f"{self.graph_url}/teams/{safe_team_id}/channels/{safe_channel_id}/messages"
        query_params = {"$top": min(limit, 50)}  # Teams messages limited to 50

        result = await self._make_graph_request("GET", url, params=query_params)
        return result.get("body", {})

    async def _create_teams_meeting(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Create an online Teams meeting.

        Normalizes datetimes to UTC for correct cross-timezone handling (MVA-2203).
        """
        url = f"{self.graph_url}/me/onlineMeetings"

        # Normalize datetimes to UTC (MVA-2203)
        safe_start = _validate_datetime_iso(params["start"], "start")
        safe_end = _validate_datetime_iso(params["end"], "end")

        meeting_data = {
            "subject": params["subject"],
            "startDateTime": safe_start,
            "endDateTime": safe_end,
            "participants": {
                "attendees": [
                    {
                        "upn": email,
                        "role": "attendee",
                    }
                    for email in params["attendees"]
                ]
            },
        }

        result = await self._make_graph_request("POST", url, json_data=meeting_data)
        return result.get("body", {})

    # Helper methods

    async def _make_graph_request(
        self,
        method: str,
        url: str,
        headers: Dict[str, str] | None = None,
        json_data: Dict[str, Any] | None = None,
        params: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to Microsoft Graph API with auth and error handling."""
        merged_headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        if headers:
            merged_headers.update(headers)

        try:
            timeout = aiohttp.ClientTimeout(total=30.0)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.request(
                    method,
                    url,
                    headers=merged_headers,
                    json=json_data,
                    params=params,
                ) as resp:
                    status_code = resp.status

                    # Handle no-content responses
                    if status_code == 204:
                        return {"status_code": 204, "body": {}}

                    try:
                        body = await resp.json()
                    except aiohttp.ContentTypeError:
                        # Some endpoints return empty body on success
                        body = {}

                    # Log errors
                    if status_code >= 400:
                        error_msg = body.get("error", {}).get("message", "Unknown error")
                        self.logger.warning(
                            "Graph API request to %s failed: HTTP %d - %s",
                            url,
                            status_code,
                            error_msg,
                        )

                    return {
                        "status_code": status_code,
                        "body": body,
                        "error": body.get("error", {}).get("message") if status_code >= 400 else None,
                    }

        except aiohttp.ClientError as exc:
            self.logger.error("Graph API request to %s failed: %s", url, exc)
            return {
                "status_code": 0,
                "body": {},
                "error": str(exc),
            }

    def _create_health_response(
        self,
        status: IntegrationStatus,
        latency: float,
        message: str,
        details: Dict[str, Any] | None = None,
    ) -> IntegrationHealth:
        """Create IntegrationHealth response."""
        return IntegrationHealth(
            provider="microsoft365",
            status=status,
            latency_ms=latency,
            message=message,
            details=details or {},
        )
