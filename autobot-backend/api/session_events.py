# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Session and chat channel publishing (#14820).

Session state used to live in the browser: the frontend minted session ids,
appended messages locally and persisted to ``localStorage``.  Two clients on one
account therefore held two independent truths that could never converge — no
amount of reliable event delivery fixes that, because each client *is* its own
source of truth.

The fix is to make the backend authoritative and let clients render from it.
The REST surface in ``api/chat_sessions.py`` already serves the snapshot; what
was missing was telling everyone *else* when it changed.  Every mutation
published here goes out durably, so a client that was disconnected can replay it
rather than silently diverging (#14818).

Channels:
    ``session:{session_id}``  — session lifecycle (created, updated, deleted)
    ``chat:{session_id}``     — conversation contents (messages appended)

Publishing must never break the request that triggered it: a failure to notify
observers is not a reason to fail the write that already succeeded.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.logging_manager import get_logger
from events.bus import PersistStrategy, publish_event

logger = get_logger(__name__)

# Event type names carried on the session/chat channels.  Kept display-oriented
# and backend-agnostic: a client renders from these without knowing which store
# produced them.
SESSION_CREATED = "session.created"
SESSION_UPDATED = "session.updated"
SESSION_DELETED = "session.deleted"
CHAT_MESSAGE_ADDED = "chat.message_added"
CHAT_CLEARED = "chat.cleared"


def session_channel(session_id: str) -> str:
    """Channel carrying lifecycle events for one session."""
    return f"session:{session_id}"


def chat_channel(session_id: str) -> str:
    """Channel carrying conversation contents for one session."""
    return f"chat:{session_id}"


async def _publish(channel: str, event_type: str, payload: Dict[str, Any]) -> None:
    """Publish durably, swallowing failures.

    Durable because a client that reconnects must be able to replay what it
    missed; swallowing because the caller's write has already committed and
    failing it now would be worse than a missed notification.
    """
    try:
        await publish_event(channel, event_type, payload, persist=PersistStrategy.REDIS)
    except Exception as exc:
        logger.warning("Failed to publish %s on %s: %s", event_type, channel, exc)


async def publish_session_created(session_id: str, session: Dict[str, Any]) -> None:
    """Announce a new session so other clients can add it to their list."""
    await _publish(
        session_channel(session_id),
        SESSION_CREATED,
        {"session_id": session_id, "session": session},
    )


async def publish_session_updated(session_id: str, changes: Dict[str, Any]) -> None:
    """Announce changed session fields (title, metadata, ...)."""
    await _publish(
        session_channel(session_id),
        SESSION_UPDATED,
        {"session_id": session_id, "changes": changes},
    )


async def publish_session_deleted(session_id: str) -> None:
    """Announce a deleted session so other clients drop it from their list."""
    await _publish(
        session_channel(session_id),
        SESSION_DELETED,
        {"session_id": session_id},
    )


async def publish_chat_message(session_id: str, message: Dict[str, Any]) -> None:
    """Announce one appended message to everyone watching the conversation."""
    await _publish(
        chat_channel(session_id),
        CHAT_MESSAGE_ADDED,
        {"session_id": session_id, "message": message},
    )


async def publish_chat_cleared(session_id: str) -> None:
    """Announce that a conversation's contents were reset."""
    await _publish(
        chat_channel(session_id),
        CHAT_CLEARED,
        {"session_id": session_id},
    )
