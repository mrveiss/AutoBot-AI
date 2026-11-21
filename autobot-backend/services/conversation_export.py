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
import uuid
from typing import Any, Dict, List, Tuple

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import utc_timestamp
from chat_history.session_file import session_file_exists
from chat_history.session_lease import session_lease
from security.session_owner_errors import SessionOwnerUnreadable
from security.session_owner_index import index_owner_or_unmark
from security.session_ownership import SessionOwnershipValidator, build_owner_metadata
from security.session_posture import deny_unreadable_owner

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


async def _sessions_to_export(chat_history_manager, username: str | None, all_users: bool, company=None) -> list:
    """The caller's own sessions through the canonical listing (#21666), narrowed to *company* (#21997).

    Every user's only when *all_users*, which is not company-scoped: it is the administrator's whole-instance export.

    *all_users* is the instance-wide export: the caller (the route) has already required an administrator.
    """
    if all_users:
        return await chat_history_manager.list_sessions()
    from api.chat_sessions import list_user_sessions  # noqa: PLC0415 -- api imports this module's siblings

    return await list_user_sessions(chat_history_manager, username, company)


async def export_all_conversations_json(
    chat_history_manager, username: str | None = None, *, all_users: bool = False, company=None
) -> str | None:
    """
    Export the caller's conversations as a bulk JSON archive (#21666).

    Without *all_users* only sessions *username* owns are exported; a principal with no username
    exports none. *all_users* exports every conversation on the instance and is admin-only.

    Returns serialised JSON string, or None on error.
    """
    try:
        sessions = await _sessions_to_export(chat_history_manager, username, all_users, company)
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
    """True when the session already exists in storage.

    Fails closed: a storage error propagates, because "could not tell" must never read as "no such
    session" when the answer decides whether an import may write into someone else's conversation.
    """
    # The stored record decides, not its message count: an owned session with no messages still exists (#21668).
    return await session_file_exists(chat_history_manager, session_id)


_FRESH_ID_ATTEMPTS = 3


async def _fresh_session_id(chat_history_manager) -> str:
    """A server-generated id for an import that may not use the requested one (#21731).

    Random (uuid4), never derived from the requested id or the clock, so two imports cannot share one.
    Create-only: an id that already has a stored record is never returned, so a save cannot merge into it.
    """
    for _ in range(_FRESH_ID_ATTEMPTS):
        candidate = str(uuid.uuid4())
        if not await _session_exists(chat_history_manager, candidate):
            return candidate
    raise RuntimeError("could not allocate an unused session id for the import")


# ---------------------------------------------------------------------------
# Public import function
# ---------------------------------------------------------------------------


async def import_conversation(
    chat_history_manager,
    document: Dict[str, Any],
    on_conflict: str = "skip",
    user_data: Dict[str, Any] | None = None,
    company_metadata: Dict[str, Any] | None = None,
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
        company_metadata: the active company's ``{"company_id": ...}``, stamped on a new chat (#21997).
        on_conflict: One of "skip", "replace", or "rename".
            - "skip"    — return without saving when session_id already exists.
            - "replace" — overwrite the existing session.
            - "rename"  — save under a new server-generated session_id.

    Returns:
        Dict with keys: success, session_id, conflict, message.
    """
    valid, err = _validate_import_document(document)
    if not valid:
        return {"success": False, "session_id": None, "conflict": False, "message": err}
    # The existence and ownership checks and the save are one step under the session's lease (#20908).
    async with session_lease(document["session_id"], "import"):
        return await _import_under_lease(chat_history_manager, document, on_conflict, user_data, company_metadata)


def _conflict_result(session_id: str, message: str) -> Dict[str, Any]:
    return {
        "success": False,
        "session_id": session_id,
        "conflict": True,
        "message": message,
    }


async def _owner_refusal(
    chat_history_manager,
    session_id: str,
    user_data: Dict[str, Any] | None,
    exists: bool = True,
):
    """``(refusal, existing_owner)``: a refusal result when the importer may not write into the existing
    session, else None; and the owner the session records.

    The owner is looked up whether or not the session exists, so a free id and a foreign one cost the
    same (#21731). #14026: an import carrying a known session_id could write into another user's
    conversation. An owner that cannot be read is refused, never treated as "unowned" (#14033). A session
    with no owner is never claimed by an import (#21668, THREAT_MODEL section 2); an admin is refused
    with a conflict because its owner is assigned only through the approval queue (#17038). A session
    another user owns (or a non-admin finds ownerless) is not refused: the caller imports under a fresh
    id (#21731).
    """
    importer = (user_data or {}).get("username")
    try:
        existing_owner = await chat_history_manager.get_session_owner(session_id)
    except SessionOwnerUnreadable:
        raise deny_unreadable_owner(session_id, importer) from None  # as a read denies (#14033)
    if exists and existing_owner is None and is_admin_role((user_data or {}).get("role")):
        logger.error(
            "Import refused: session %s has no owner and an import does not claim one",
            session_id[:8],
        )
        return (
            _conflict_result(
                session_id,
                f"Session {session_id!r} has no owner; its owner is assigned through the approval queue",
            ),
            existing_owner,
        )
    return None, existing_owner


async def _import_under_lease(
    chat_history_manager,
    document: Dict[str, Any],
    on_conflict: str,
    user_data: Dict[str, Any] | None,
    company_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Resolve the conflict policy against the stored session, then save; the caller holds the lease.

    #21731: only the session's own owner imports onto the requested id. Every other import (id free,
    id foreign, id ownerless for a non-admin) takes a fresh server-generated id and the answer a new
    session gets, so the response never says whether the id exists or who owns it.
    """
    session_id: str = document["session_id"]
    importer = (user_data or {}).get("username")
    exists = await _session_exists(chat_history_manager, session_id)
    refusal, existing_owner = await _owner_refusal(chat_history_manager, session_id, user_data, exists)
    if refusal is not None:
        return refusal
    if not (exists and existing_owner is not None and existing_owner == importer):
        session_id, exists = await _fresh_session_id(chat_history_manager), False
        logger.info("Import saved under a fresh id %s", session_id)
    elif on_conflict == "rename":
        session_id = await _fresh_session_id(chat_history_manager)
        logger.info("Import renamed to %s due to conflict", session_id)
    elif on_conflict == "skip":
        logger.info("Import skipped: session %s already exists", session_id)
        return _conflict_result(session_id, f"Session {session_id!r} already exists (on_conflict=skip)")
    # #21664: index a new session or one the importer already owns (an ownerless one is refused above, #21668)
    index = not exists or on_conflict == "rename" or existing_owner == importer
    return await _save_import(
        chat_history_manager,
        document,
        session_id,
        exists,
        on_conflict,
        user_data,
        index,
        company_metadata,
    )


def _import_metadata(user_data, company_metadata, replaces: bool) -> Dict[str, Any] | None:
    """The owner record, plus the active company on a NEW chat; replacing one's own chat does not re-tag it (#21997)."""
    return {**build_owner_metadata(user_data), **({} if replaces else company_metadata or {})} or None


async def _save_import(
    chat_history_manager,
    document: Dict[str, Any],
    session_id: str,
    exists: bool,
    on_conflict: str,
    user_data: Dict[str, Any] | None,
    index: bool = False,
    company_metadata: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Save the imported messages under *session_id*, stamped with the importer as owner (#14026).

    With *index*, the importer's owner index also takes the session (#21664).
    """
    messages: List[Dict[str, Any]] = document.get("messages", [])
    await chat_history_manager.save_session(
        session_id=session_id,
        messages=messages,
        name=document.get("name", ""),
        metadata=_import_metadata(user_data, company_metadata, exists and on_conflict == "replace"),
        replace=exists and on_conflict == "replace",  # the explicit replace; a snapshot never drops messages (#20862)
    )
    logger.info("Imported conversation %s (%d messages)", session_id, len(messages))
    if index and (importer := (user_data or {}).get("username")):
        await _index_import_owner(session_id, importer)
    return {
        "success": True,
        "session_id": session_id,
        "conflict": exists,
        "message": f"Imported {len(messages)} messages into session {session_id!r}",
    }


async def _owner_validator() -> SessionOwnershipValidator:
    """The session-ownership validator over the main Redis database."""
    from autobot_shared.redis_client import get_redis_client

    return SessionOwnershipValidator(await get_redis_client(async_client=True, database="main"))


async def _index_import_owner(session_id: str, importer: str) -> None:
    """Index the import for its importer, or unmark their owner index (#21664). The save already landed."""
    try:
        await index_owner_or_unmark(await _owner_validator(), session_id, importer)
    except Exception as e:  # no store to index into or to unmark: the marker's TTL bounds the gap
        logger.error(
            "Imported session %s is not in %s's owner index: %s",
            session_id,
            importer,
            e,
        )


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
