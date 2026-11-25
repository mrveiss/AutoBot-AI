# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Microsoft 365 action catalog (Issue #13710): the descriptors ``get_available_actions`` returns."""

from typing import List

from integrations.base import IntegrationAction

MICROSOFT365_ACTIONS: List[IntegrationAction] = [
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
        description="List top-level mail folders",
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
