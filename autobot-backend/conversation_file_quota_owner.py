# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who pays the conversation-file quota for a file an agent writes (#20678, maintainer option B).

``uploaded_by`` records who WROTE a file (a user, or an agent's name); ``quota_owner`` records who it is
CHARGED to. Before #20678 an agent's file was charged to the agent's name, so every user's ``scribe`` shared
one quota and one user's agent could lock out all the others.

Existing rows are not rewritten here: a row with no ``quota_owner`` is charged to its ``uploaded_by`` as
before (``conversation_file_quota._CHARGED``). Moving old agent-charged rows to a human owner is a data
change an agent only proposes, through the #17038 approval queue.
"""

from __future__ import annotations

from fastapi import Request

from security.session_posture import read_owner

#: The ownerless-write rule, stated once. An agent write has no human owner of its own (the writer is an
#: agent name, or the MCP tool's generic "agent"), so it is charged to the CONVERSATION OWNER. When the
#: conversation records no owner (a legacy session), it is charged to the authenticated human who made
#: the call, so an agent write is never charged to an agent name or to the shared NULL bucket.
OWNERLESS_AGENT_WRITE_RULE = "conversation_owner"


async def resolve_agent_quota_owner(request: Request, session_id: str, user_data: dict) -> str | None:
    """The human an agent-written file in *session_id* is charged to (``OWNERLESS_AGENT_WRITE_RULE``).

    The conversation owner as recorded; failing to read it denies (``read_owner``), it never falls through
    to the caller. Only a conversation that records no owner is charged to the calling user.
    """
    caller = user_data.get("username")
    return await read_owner(session_id, request, caller) or caller


async def mcp_quota_owner(request: Request, session_id: str, user_data: dict, tool_name: str) -> str | None:
    """Who pays for an MCP tool call: the owner for ``session_write_file``, nobody for tools that store nothing."""
    if tool_name != "session_write_file":
        return None
    return await resolve_agent_quota_owner(request, session_id, user_data)
