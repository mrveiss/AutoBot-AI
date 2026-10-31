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

from typing import Any, Dict, List

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


def _close_pair(pairs: List[Dict[str, str]], user: str | None, replies: List[str]) -> None:
    """Append the exchange being collected, if it is a completed one."""
    if user and replies:
        pairs.append({"user": user, "assistant": "\n\n".join(replies)})


def project_turn_pairs(messages: List[Dict[str, Any]], limit: int = LLM_CONTEXT_TURN_LIMIT) -> List[Dict[str, str]]:
    """The last *limit* completed ``{user, assistant}`` exchanges in *messages*.

    Pure: plain dicts in, plain dicts out. *messages* is what
    ``ChatHistoryManager.load_session`` returns, oldest first.
    """
    pairs: List[Dict[str, str]] = []
    user: str | None = None
    replies: List[str] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("sender") == "user":
            _close_pair(pairs, user, replies)
            text = message.get("text") or ""
            user, replies = (text if text.strip() else None), []
        elif user and _is_prose_reply(message):
            replies.append(message["text"].strip())
    _close_pair(pairs, user, replies)
    return pairs[-limit:] if limit > 0 else []
