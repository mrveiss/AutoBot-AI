# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The LLM-context view of a chat session, projected from chat_sessions (#18293).

``chat_sessions`` (``chat:session:{id}`` + the session file) is the one system
of record for conversation turns (``autobot_shared/store_authority.py``). The
LLM context is a *projection* of it: the most recent completed exchanges as
``{user, assistant}`` pairs. Nothing here writes; the projection is recomputed
from :meth:`ChatHistoryManager.load_session` whenever it is needed, so it can
never become a second original.

A pair is one user message and the prose replies that followed it, up to the
next user message. Only prose counts as a reply -- the completed LLM response,
a ``respond``-tool reply, or a terminal interpretation -- which is what the
retired transcript file held. Tool output, approvals and slash-command echoes
are visible in the GUI but were never LLM context, and are not here either.
A user message with no prose reply (a failed turn, or the turn in flight) is
not a completed exchange and is left out; the in-flight turn is re-registered
by ``ConversationHandlerMixin._register_user_message_in_history``.
"""

from typing import Any, Dict, List, Tuple

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

#: How many completed exchanges the LLM sees. Matches the in-process window
#: ``ConversationHandlerMixin._update_conversation_history`` keeps, and the
#: last-10 bound the retired transcript loader applied.
LLM_CONTEXT_TURN_LIMIT = 10

#: ``messageType`` values whose assistant text is a prose reply.
_PROSE_REPLY_TYPES = frozenset({"response", "llm_response", "default", "terminal_interpretation"})


def _is_prose_reply(message: Dict[str, Any]) -> bool:
    """True for an assistant entry whose text is a reply the LLM gave."""
    if message.get("sender") != "assistant" or not (message.get("text") or "").strip():
        return False
    metadata = message.get("metadata")
    if isinstance(metadata, dict) and metadata.get("message_type") == "llm_response":
        return True
    return message.get("messageType") in _PROSE_REPLY_TYPES


def _close_pair(pairs: List[Tuple[int, Dict[str, str]]], start: int, user: str | None, replies: List[str]) -> None:
    """Append the exchange being collected (it began at message index *start*), if it is a completed one."""
    if user and replies:
        pairs.append((start, {"user": user, "assistant": "\n\n".join(replies)}))


def project_indexed_pairs(messages: List[Dict[str, Any]], start: int = 0) -> List[Tuple[int, Dict[str, str]]]:
    """Every completed exchange that begins at or after message index *start*, as (index of its user message, pair).

    Pure. An exchange begins at a user message and ends at the next one, so projecting from
    the index of a user message gives exactly the pairs a projection of the whole list gives
    from that point on: a caller that stored the index of the last exchange it folded reads
    only the messages after it. A *start* inside an exchange begins at the next user message.
    """
    pairs: List[Tuple[int, Dict[str, str]]] = []
    user: str | None = None
    user_at = start
    replies: List[str] = []
    for index in range(max(0, start), len(messages)):
        message = messages[index]
        if not isinstance(message, dict):
            continue
        if message.get("sender") == "user":
            _close_pair(pairs, user_at, user, replies)
            text = message.get("text") or ""
            user, user_at, replies = (text if text.strip() else None), index, []
        elif user and _is_prose_reply(message):
            replies.append(message["text"].strip())
    _close_pair(pairs, user_at, user, replies)
    return pairs


def project_turn_pairs(messages: List[Dict[str, Any]], limit: int = LLM_CONTEXT_TURN_LIMIT) -> List[Dict[str, str]]:
    """The last *limit* completed ``{user, assistant}`` exchanges in *messages*.

    Pure: plain dicts in, plain dicts out. *messages* is what
    ``ChatHistoryManager.load_session`` returns, oldest first.
    """
    pairs = [pair for _, pair in project_indexed_pairs(messages)]
    return pairs[-limit:] if limit > 0 else []


async def load_session_messages(session_id: str) -> List[Dict[str, Any]] | None:
    """The raw messages of *session_id* from chat_sessions, the system of record; None if unreadable.

    The store keeps a session as one document (Redis cache first, else the session file), so
    this is one read and parse whatever is projected from it afterwards; a caller that wants
    only the tail projects from a stored message index (``project_indexed_pairs``) instead of
    reading the document twice. The one reader ``load_turn_pairs`` and the rolling summary share.
    """
    from chat_history import ChatHistoryManager

    try:
        return await ChatHistoryManager().load_session(session_id)
    except (PermissionError, ValueError, OSError) as exc:
        logger.error("Cannot read chat session %s for LLM context: %s", session_id, exc)
        return None


async def load_turn_pairs(session_id: str, limit: int = LLM_CONTEXT_TURN_LIMIT) -> List[Dict[str, str]] | None:
    """The last *limit* completed exchanges of *session_id* read from chat_sessions, the system of record.

    None (an unreadable session) is kept apart from ``[]`` (a session with no
    completed turns) so the first is logged as the error it is.
    """
    messages = await load_session_messages(session_id)
    return None if messages is None else project_turn_pairs(messages, limit)
