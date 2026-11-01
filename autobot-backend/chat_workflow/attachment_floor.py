# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat that used an attachment keeps asking before every tool call (#20195).

Model output derived from an attached file sits in the chat's history, and ends up in later prompts, so the turn
that carried the file is not the only one holding untrusted text. The server records, per chat, that an
attachment turn ran; every later turn is stamped ``ATTACHMENT_CHAT_KEY`` from that record, never from the client,
and the stamp stays true after the file is deleted (the record is about the chat's history, not the file).

* The fact is one durable row per chat in the conversation files store (``chat_attachment_marks``, concept
  ``chat_attachment_use``, see ``chat_attachment_marks``). It is written BEFORE the turn reads any file and is
  independent of the session record and of file rows, so deleting the file changes nothing. A write that fails
  stops the turn (``AttachmentMarkError``) and nothing is read; a mark that cannot be READ counts as set: ask.
* The admin setting ``chat.auto_approve_attachment_turns`` (off by default, read from the SLM) is stamped as
  ``ATTACHMENT_AUTO_APPROVE_KEY`` and lifts the floor; an unreadable setting leaves it off, so the turn asks.
* A client's own copy of either key is removed before the server writes its own.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.ai_lines import ATTACHMENT_AUTO_APPROVE_KEY, ATTACHMENT_CHAT_KEY
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


class AttachmentMarkError(RuntimeError):
    """The chat's durable attachment mark could not be written, so the turn does not run (and reads no file)."""


async def _manager():
    from conversation_file_manager import get_conversation_file_manager

    return await get_conversation_file_manager()


async def mark_chat(session_id: str) -> None:
    """Record durably that an attachment turn ran in *session_id*; raises ``AttachmentMarkError`` if it cannot."""
    from chat_attachment_marks import write_mark

    try:
        await write_mark(await _manager(), session_id)
    except Exception as exc:  # noqa: BLE001 -- no durable mark, no turn: it would run unmarked after any later loss
        logger.error("Attachment mark not written for chat %s...: %s", session_id[:8], type(exc).__name__)
        raise AttachmentMarkError(
            "This message was not processed: the record that this chat used an attachment could not be saved. "
            "Try again."
        ) from exc


async def chat_used_attachment(session_id: str) -> bool:
    """Whether *session_id* ever ran an attachment turn, from the durable mark. Unreadable is True: ask (#20195)."""
    from chat_attachment_marks import read_mark

    try:
        return await read_mark(await _manager(), session_id)
    except Exception as exc:  # noqa: BLE001 -- fail toward asking
        logger.warning("Attachment mark unreadable for chat %s...: %s", session_id[:8], type(exc).__name__)
        return True


async def stamp_attachment_floor(context: Dict[str, Any] | None, session_id: str) -> Dict[str, Any]:
    """*context* with the server's attachment-floor keys written, and any client-sent copy replaced."""
    from chat_workflow.approval_baseline import attachment_auto_approve_enabled

    merged = {k: v for k, v in (context or {}).items() if k not in (ATTACHMENT_CHAT_KEY, ATTACHMENT_AUTO_APPROVE_KEY)}
    recorded = await chat_used_attachment(session_id)
    if recorded:
        merged[ATTACHMENT_CHAT_KEY] = True
    if (recorded or merged.get("attachments")) and await attachment_auto_approve_enabled():
        merged[ATTACHMENT_AUTO_APPROVE_KEY] = True
    return merged
