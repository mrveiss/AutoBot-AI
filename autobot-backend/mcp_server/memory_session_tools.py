# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``memory.session_list`` / ``memory.session_read`` MCP tools (#11137).

Both read the VerbatimStore under the authenticated principal (``current_owner().user_id``) and
fail closed without one (``OwnerScopeRequired`` -> 403-class), exactly like the memory-graph
tools. Unlike ``memory.verbatim_search`` -- which still passes ``UNSCOPED_ALL_USERS`` -- there is
no unscoped path here. The tool schemas live in this module (merged into the server's table) to
keep ``autobot_server`` under its size ceiling.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field

from mcp_server.principal import current_owner
from memory.verbatim_sessions import SESSION_LIST_DEFAULT_LIMIT

SESSION_TOOLS: Dict[str, Dict[str, Any]] = {
    "memory.verbatim_search": {
        "description": "Search verbatim conversation chunks stored in the VerbatimStore.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
                "session_filter": {
                    "type": "string",
                    "description": "Optional session_id to restrict results",
                },
            },
            "required": ["query"],
        },
    },
    "memory.session_list": {
        "description": "List the caller's own stored sessions (id, chunk count, first/last timestamp), newest first.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "default": SESSION_LIST_DEFAULT_LIMIT,
                    "description": "Maximum number of sessions to return",
                },
            },
        },
    },
    "memory.session_read": {
        "description": (
            "Read one of the caller's own stored sessions, in turn order. " "Another owner's session is not found."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {"session_id": {"type": "string", "description": "Session id from memory.session_list"}},
            "required": ["session_id"],
        },
    },
}


class _SessionListArgs(BaseModel):
    limit: int = Field(SESSION_LIST_DEFAULT_LIMIT, ge=1, le=10_000)


class _SessionReadArgs(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=200)


class MemorySessionToolsMixin:
    """Owner-scoped session tools; mixed into ``AutoBotMCPServer``."""

    async def _memory_session_list(self, limit: int = SESSION_LIST_DEFAULT_LIMIT) -> Any:
        from memory.verbatim_sessions import list_sessions
        from memory.verbatim_store import VerbatimStore

        args = _SessionListArgs(limit=limit)
        owner = current_owner()  # fails closed without an authenticated principal
        sessions, truncated = await list_sessions(VerbatimStore(), owner.user_id, args.limit)
        return {"sessions": sessions, "count": len(sessions), "truncated": truncated}

    async def _memory_session_read(self, session_id: str) -> Any:
        from memory.verbatim_sessions import read_session
        from memory.verbatim_store import VerbatimStore

        args = _SessionReadArgs(session_id=session_id)
        owner = current_owner()
        chunks, truncated = await read_session(VerbatimStore(), owner.user_id, args.session_id)
        if not chunks:
            return {"error": "Session not found", "session_id": args.session_id}
        return {"session_id": args.session_id, "chunks": chunks, "count": len(chunks), "truncated": truncated}
