# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Rebuilding a vanished session's pending approval from chat history (#13478), without resurrecting a
decided one (#20674, #21174).

Chat history is a best-effort record. A rebuild restores an approval only when:

* the request belongs to the session being rebuilt (``metadata.terminal_session_id``): a conversation can
  hold requests from several sessions, and one session's decision must never run another's command;
* no ``command_approval_response`` for that session follows it; and
* the durable decided marker (``session_state.decided_marker_exists``) is absent. The marker, not the chat
  message, is the authority: the message is written last and may be lost.

If the marker store cannot be read the approval is not restored (fail closed).
"""

from __future__ import annotations

from typing import Dict, List

from autobot_shared.logging_manager import get_logger

from .models import AgentSessionState, AgentTerminalSession
from .session_state import ApprovalStateUnavailableError, decided_marker_exists, pending_decision_id

logger = get_logger(__name__)

# O(1) lookup optimization constants (Issue #326)
APPROVAL_RESPONSE_KEYWORDS = {"approved", "denied", "executed", "rejected"}

RESTORE_MESSAGE_LIMIT = 50


def _request_session(msg: Dict) -> str | None:
    return (msg.get("metadata") or {}).get("terminal_session_id")


def _find_latest_approval_request(messages: List[Dict], session_id: str) -> Dict | None:
    """The newest ``command_approval_request`` raised by *session_id*; requests of other sessions never match."""
    for msg in reversed(messages):  # Search newest first
        if msg.get("message_type") == "command_approval_request" and _request_session(msg) == session_id:
            return msg
    return None


def _is_approval_already_responded(messages: List[Dict], request_timestamp: float, session_id: str) -> bool:
    """True if a response for *session_id* follows the request; another session's response does not count."""
    for msg in reversed(messages):
        if msg.get("timestamp", 0) <= request_timestamp:
            continue
        other = _request_session(msg)
        if other is not None and other != session_id:
            continue
        content = msg.get("text", "").lower()
        if any(keyword in content for keyword in APPROVAL_RESPONSE_KEYWORDS):
            return True
    return False


def _apply_restored_approval_state(
    session: AgentTerminalSession,
    approval_request: Dict,
    conversation_id: str,
    request_timestamp: float,
) -> None:
    """Apply the request's metadata to *session*, keeping the original command id when the request carries it."""
    metadata = approval_request.get("metadata", {})
    command = metadata.get("command")
    if not command:
        logger.warning("Found approval request but no command in metadata for conversation %s", conversation_id)
        return
    session.pending_approval = {
        "command": command,
        "risk": metadata.get("risk_level", "MEDIUM"),
        "reasons": metadata.get("reasons", []),
        "description": metadata.get("description", ""),
        "terminal_session_id": metadata.get("terminal_session_id"),
        "conversation_id": conversation_id,
        "timestamp": request_timestamp,
    }
    if metadata.get("command_id"):
        session.pending_approval["command_id"] = metadata["command_id"]
    session.state = AgentSessionState.AWAITING_APPROVAL
    logger.info(
        "Restored pending approval for session %s: command=%r, risk=%s",
        session.session_id,
        command,
        metadata.get("risk_level"),
    )


async def _already_decided(redis, session: AgentTerminalSession, decision_id: str | None) -> bool:
    """The durable marker says this approval was claimed; an unreadable marker counts as decided."""
    try:
        return await decided_marker_exists(redis, decision_id)
    except ApprovalStateUnavailableError as exc:
        logger.error("Not restoring an approval for %s, its decided marker is unreadable: %s", session.session_id, exc)
        return True


async def restore_pending_approval(manager, session: AgentTerminalSession, conversation_id: str) -> None:
    """Restore *session*'s own undecided approval from chat history; leave it without one otherwise."""
    if not manager.chat_history_manager:
        return
    try:
        messages = await manager.chat_history_manager.get_session_messages(
            session_id=conversation_id, limit=RESTORE_MESSAGE_LIMIT
        )
        request = _find_latest_approval_request(messages or [], session.session_id)
        if not request:
            logger.debug("No approval request of session %s in conversation %s", session.session_id, conversation_id)
            return
        stamp = request.get("timestamp", 0)
        if _is_approval_already_responded(messages, stamp, session.session_id):
            logger.info("Approval of session %s already responded to, not restoring", session.session_id)
            return
        before = session.state
        _apply_restored_approval_state(session, request, conversation_id, stamp)
        if session.has_pending_approval() and await _already_decided(
            manager.redis_client, session, pending_decision_id(session.pending_approval)
        ):
            session.pending_approval, session.state = None, before
    except Exception as e:  # noqa: BLE001 - a failed restore leaves no decidable approval
        logger.error("Failed to restore pending approval from chat history: %s", e, exc_info=True)
        session.pending_approval = None
