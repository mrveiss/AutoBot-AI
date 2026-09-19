# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Conversation Export and Import Service (#1808)

Provides export and import operations for chat conversations:
- Export single conversation as enriched JSON (with metadata, token info, model)
- Export single conversation as human-readable Markdown
- Bulk export all conversations as a JSON archive
- Import AutoBot JSON format with duplicate detection by session_id
"""

import json
import time
from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from security.session_owner_errors import SessionOwnerUnreadable
from security.session_ownership import build_owner_metadata

logger = get_logger(__name__)

# Format identifier embedded in every exported archive
AUTOBOT_EXPORT_FORMAT = "autobot-conversation-v1"


# ---------------------------------------------------------------------------
# Internal helpers — message formatting
# ---------------------------------------------------------------------------


def _render_message_markdown(msg: Dict[str, Any], index: int) -> str:
    """Render a single message as a Markdown block."""
    sender = msg.get("sender") or msg.get("role", "unknown")
    timestamp = msg.get("timestamp", "")
    text = msg.get("text") or msg.get("content", "")
    header = f"### Message {index + 1} — {sender}"
    if timestamp:
        header += f" ({timestamp})"
    return f"{header}\n\n{text}"


def _render_session_metadata_markdown(session_id: str, chat_data: Dict[str, Any]) -> List[str]:
    """Build Markdown header lines from session metadata."""
    lines = [
        f"# Conversation Export: {session_id}",
        "",
        f"**Session ID:** {session_id}",
        f"**Name:** {chat_data.get('name', '')}",
        f"**Created:** {chat_data.get('created_time', chat_data.get('createdTime', ''))}",
        f"**Last Modified:** {chat_data.get('last_modified', chat_data.get('lastModified', ''))}",
        f"**Message Count:** {len(chat_data.get('messages', []))}",
        "",
        "---",
        "",
    ]
    return lines


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def _build_json_envelope(session_id: str, chat_data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap raw session data in the versioned AutoBot JSON export envelope."""
    return {
        "format": AUTOBOT_EXPORT_FORMAT,
        "exported_at": utc_timestamp(),
        "session_id": session_id,
        "name": chat_data.get("name", ""),
        "created_time": chat_data.get("created_time", chat_data.get("createdTime", "")),
        "last_modified": chat_data.get("last_modified", chat_data.get("lastModified", "")),
        "metadata": chat_data.get("metadata", {}),
        "messages": chat_data.get("messages", []),
        "message_count": len(chat_data.get("messages", [])),
    }


def _build_bulk_envelope(sessions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrap multiple session envelopes in a bulk archive envelope."""
    return {
        "format": f"{AUTOBOT_EXPORT_FORMAT}-bulk",
        "exported_at": utc_timestamp(),
        "conversation_count": len(sessions),
        "conversations": sessions,
    }


# ---------------------------------------------------------------------------
# Public export functions
# ---------------------------------------------------------------------------


async def export_conversation_json(chat_history_manager, session_id: str) -> str | None:
    """
    Export a single conversation as enriched AutoBot JSON.

    Returns serialised JSON string, or None on error.
    """
    try:
        chat_data = await _load_full_session_data(chat_history_manager, session_id)
        if chat_data is None:
            return None
        envelope = _build_json_envelope(session_id, chat_data)
        return json.dumps(envelope, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error("Failed to export session %s as JSON: %s", session_id, exc)
        return None


async def export_conversation_markdown(chat_history_manager, session_id: str) -> str | None:
    """
    Export a single conversation as human-readable Markdown.

    Returns Markdown string, or None on error.
    """
    try:
        chat_data = await _load_full_session_data(chat_history_manager, session_id)
        if chat_data is None:
            return None
        lines = _render_session_metadata_markdown(session_id, chat_data)
        for i, msg in enumerate(chat_data.get("messages", [])):
            lines.append(_render_message_markdown(msg, i))
            lines.append("")
        return "\n".join(lines)
    except Exception as exc:
        logger.error("Failed to export session %s as Markdown: %s", session_id, exc)
        return None


async def export_all_conversations_json(chat_history_manager) -> str | None:
    """
    Export all conversations as a bulk JSON archive.

    Returns serialised JSON string, or None on error.
    """
    try:
        sessions = await chat_history_manager.list_sessions()
        envelopes = []
        for session_info in sessions:
            session_id = session_info.get("chatId") or session_info.get("id", "")
            if not session_id:
                continue
            chat_data = await _load_full_session_data(chat_history_manager, session_id)
            if chat_data is not None:
                envelopes.append(_build_json_envelope(session_id, chat_data))
        archive = _build_bulk_envelope(envelopes)
        return json.dumps(archive, indent=2, ensure_ascii=False)
    except Exception as exc:
        logger.error("Failed to bulk export conversations: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Import helpers
# ---------------------------------------------------------------------------


def _validate_import_document(document: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Validate an import document.

    Returns (is_valid, error_message).  error_message is empty on success.
    """
    fmt = document.get("format", "")
    if not fmt.startswith("autobot-conversation-v"):
        return False, f"Unrecognised format: {fmt!r}"
    if "session_id" not in document:
        return False, "Missing required field: session_id"
    if "messages" not in document:
        return False, "Missing required field: messages"
    return True, ""


async def _session_exists(chat_history_manager, session_id: str) -> bool:
    """Return True when the session already exists in storage."""
    try:
        messages = await chat_history_manager.load_session(session_id)
        return len(messages) > 0
    except Exception:
        return False


def _apply_suffix_to_session_id(session_id: str, suffix: str) -> str:
    """Return a new session_id with the given suffix appended."""
    return f"{session_id}-{suffix}"


# ---------------------------------------------------------------------------
# Public import function
# ---------------------------------------------------------------------------


# Distinct from None: ownership could not be read, which must never be treated
# as "unowned" when deciding whether an overwrite is allowed (#14033).
_UNREADABLE_OWNER = object()


async def import_conversation(
    chat_history_manager,
    document: Dict[str, Any],
    on_conflict: str = "skip",
    user_data: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Import a conversation from an AutoBot JSON export document.

    Args:
        chat_history_manager: Chat history manager instance.
        document: Parsed export document (must conform to AUTOBOT_EXPORT_FORMAT).
        user_data: The importing user, stamped as the session owner (#14026).
            Without it an import created an ownerless session, and callers that
            read "no owner" as "legacy, allow access" made it readable by
            anyone.
        on_conflict: One of "skip", "replace", or "rename".
            - "skip"    — return without saving when session_id already exists.
            - "replace" — overwrite the existing session.
            - "rename"  — save under a new session_id with an "-imported" suffix.

    Returns:
        Dict with keys: success, session_id, conflict, message.
    """
    valid, err = _validate_import_document(document)
    if not valid:
        return {"success": False, "session_id": None, "conflict": False, "message": err}

    session_id: str = document["session_id"]
    messages: List[Dict[str, Any]] = document.get("messages", [])
    name: str = document.get("name", "")

    exists = await _session_exists(chat_history_manager, session_id)

    if exists:
        if on_conflict == "skip":
            logger.info("Import skipped: session %s already exists", session_id)
            return {
                "success": False,
                "session_id": session_id,
                "conflict": True,
                "message": f"Session {session_id!r} already exists (on_conflict=skip)",
            }
        if on_conflict == "replace":
            # #14026: "replace" overwrote whatever was already at this
            # session_id with no ownership check at all, so an import carrying a
            # known session_id could destroy another user's conversation.
            try:
                existing_owner = await chat_history_manager.get_session_owner(session_id)
            except SessionOwnerUnreadable:
                existing_owner = _UNREADABLE_OWNER

            importer = (user_data or {}).get("username")
            if existing_owner is _UNREADABLE_OWNER or (existing_owner is not None and existing_owner != importer):
                logger.warning(
                    "Import refused: %s may not replace session %s",
                    importer or "<anonymous>",
                    session_id,
                )
                return {
                    "success": False,
                    "session_id": session_id,
                    "conflict": True,
                    "message": f"Session {session_id!r} belongs to another user",
                }

        if on_conflict == "rename":
            suffix = str(int(time.time()))
            session_id = _apply_suffix_to_session_id(session_id, f"imported-{suffix}")
            logger.info("Import renamed to %s due to conflict", session_id)

    # #14026: stamp ownership through the canonical builder, so an imported
    # session carries the same owner fields as one created by POST /chat/sessions.
    owner_metadata = build_owner_metadata(user_data)

    await chat_history_manager.save_session(
        session_id=session_id,
        messages=messages,
        name=name,
        metadata=owner_metadata or None,
    )
    logger.info("Imported conversation %s (%d messages)", session_id, len(messages))
    return {
        "success": True,
        "session_id": session_id,
        "conflict": exists,
        "message": f"Imported {len(messages)} messages into session {session_id!r}",
    }


# ---------------------------------------------------------------------------
# Internal utility
# ---------------------------------------------------------------------------


async def _load_full_session_data(chat_history_manager, session_id: str) -> Dict[str, Any] | None:
    """
    Load the full session data dict (not just the messages list).

    Delegates to the public :meth:`ChatHistoryManager.load_full_session` API
    so that this service has no dependency on internal implementation details.
    Returns None when the session does not exist or loading fails.
    """
    try:
        return await chat_history_manager.load_full_session(session_id)
    except Exception as exc:
        logger.error("Error loading full session data for %s: %s", session_id, exc)
        return None
