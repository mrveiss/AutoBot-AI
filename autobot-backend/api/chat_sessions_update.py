# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Write side of PUT /chat/sessions/{id} (#20928)."""

from api.schemas_chat import SessionUpdate
from chat_history.owner_keys import strip_server_controlled
from exceptions import get_exceptions_lazy


def _update_failed(session_id: str):
    """The 5xx error raised when the store refuses a PUT /chat/sessions write (#20928)."""
    _, InternalError, _, _, _ = get_exceptions_lazy()
    return InternalError(f"Session {session_id} could not be updated")


async def apply_session_update(manager, session_id: str, session_data: SessionUpdate) -> dict:
    """Write the PUT body through the manager's real API and return the stored session (#20928).

    ``title`` is stored as the session ``name``; ``metadata`` is merged so the owner and
    other server-written keys survive; client metadata cannot change the server-controlled
    ownership keys (``strip_server_controlled``, shared with POST /chat/sessions), dropped before the merge.
    A missing session is a 404, a refused write a 5xx.

    The manager has no single locked write that sets the name and merges metadata, so these are
    two writes. Order: metadata FIRST, title SECOND. If the first write fails the session is
    untouched; if the second fails only the (lower-stakes) title is stale. A failure can therefore
    never leave a renamed session carrying stale metadata.
    """
    _, _, ResourceNotFoundError, _, _ = get_exceptions_lazy()
    if await manager.get_session(session_id) is None:
        raise ResourceNotFoundError(f"Session {session_id} not found")
    client_metadata = strip_server_controlled(session_data.metadata)
    if client_metadata and not await manager.update_session_metadata(session_id, client_metadata):
        raise _update_failed(session_id)
    if session_data.title is not None and not await manager.update_session(session_id, {"name": session_data.title}):
        raise _update_failed(session_id)
    stored = await manager.get_session(session_id)
    if stored is None:
        raise ResourceNotFoundError(f"Session {session_id} not found")
    return {
        "id": session_id,
        "title": stored.get("name"),
        "metadata": stored.get("metadata"),
        "created_at": stored.get("created_time") or stored.get("created_at"),
        "last_modified": stored.get("last_modified"),
    }
