# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat that used an attachment keeps asking before every tool call (#20195).

Model output derived from an attached file sits in the chat's history, and ends up in later prompts, so the turn
that carried the file is not the only one holding untrusted text. The server records, durably and per chat, that an
attachment turn ran; every later turn is stamped ``ATTACHMENT_CHAT_KEY`` from that record, never from the client,
and the stamp stays true after the file is soft-deleted (the record is about the chat's history, not the file).

* The record has no expiry. A record that cannot be READ counts as set: the turn asks.
* The admin setting ``chat.auto_approve_attachment_turns`` (off by default, read from the SLM) is stamped as
  ``ATTACHMENT_AUTO_APPROVE_KEY`` and lifts the floor; an unreadable setting leaves it off, so the turn asks.
* A client's own copy of either key is removed before the server writes its own.
"""

from __future__ import annotations

from typing import Any, Dict

from autobot_shared.ai_lines import ATTACHMENT_AUTO_APPROVE_KEY, ATTACHMENT_CHAT_KEY
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_mixin import AsyncRedisClientMixin

logger = get_logger(__name__)

_RECORD_KEY = "autobot:session:{session_id}:attachment_used"


class _Record(AsyncRedisClientMixin):
    _redis_database = "knowledge"


_record = _Record()


async def mark_chat(session_id: str) -> None:
    """Record that an attachment turn ran in *session_id*. A write failure raises: the turn must not go on unmarked."""
    redis = await _record._get_redis()
    await redis.set(_RECORD_KEY.format(session_id=session_id), "1")  # no expiry: it is about the chat's history


async def chat_used_attachment(session_id: str) -> bool:
    """Whether *session_id* ever ran an attachment turn. An unreadable record is True (fail toward asking)."""
    try:
        redis = await _record._get_redis()
        return await redis.get(_RECORD_KEY.format(session_id=session_id)) is not None
    except Exception as exc:  # noqa: BLE001 -- fail toward asking
        logger.warning("Attachment record unreadable for chat %s...: %s", session_id[:8], type(exc).__name__)
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
