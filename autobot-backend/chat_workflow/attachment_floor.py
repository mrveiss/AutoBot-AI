# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A chat that used an attachment keeps asking before every tool call (#20195).

Model output derived from an attached file sits in the chat's history, and ends up in later prompts, so the turn
that carried the file is not the only one holding untrusted text. The server records, per chat, that an
attachment turn ran; every later turn is stamped ``ATTACHMENT_CHAT_KEY`` from that record, never from the client,
and the stamp stays true after the file is soft-deleted (the record is about the chat's history, not the file).

* The fact lives in the chat's session record (system of record ``chat_sessions``) and in an untimed Redis key,
  a copy that ``allkeys-lru`` may evict. The chat counts as having used one if EITHER says so, or if it has any
  file association row (a deleted file's too). A fact that cannot be READ counts as set: the turn asks.
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
_SESSION_FLAG = "attachment_used"  # in the session record's metadata: the durable fact


class _Record(AsyncRedisClientMixin):
    _redis_database = "knowledge"


_record = _Record()


async def _session_marked(session_id: str) -> bool:
    """Whether the chat's own session record says an attachment turn ran. A missing session reads False."""
    from chat_history import ChatHistoryManager

    session = await ChatHistoryManager().load_full_session(session_id)
    return bool(((session or {}).get("metadata") or {}).get(_SESSION_FLAG))


async def _mark_session(session_id: str) -> bool:
    """Write the flag into the session record (the chat's system of record). False when there is no session yet."""
    from chat_history import ChatHistoryManager

    return bool(await ChatHistoryManager().update_session_metadata(session_id, {_SESSION_FLAG: True}))


async def _has_file_rows(session_id: str) -> bool:
    """Whether the chat has, or ever had, a file association row (a deleted file still counts). Raises if unreadable."""
    from conversation_file_manager import get_conversation_file_manager

    return await (await get_conversation_file_manager()).session_has_file_rows(session_id)


async def mark_chat(session_id: str) -> None:
    """Record that an attachment turn ran in *session_id*, in the session record and in Redis.

    The session record persists; the Redis key is a fast copy that ``allkeys-lru`` may evict. A Redis write
    failure raises: the turn must not go on unmarked. A session with no record yet is marked on a later read.
    """
    redis = await _record._get_redis()
    await redis.set(_RECORD_KEY.format(session_id=session_id), "1")  # no expiry: it is about the chat's history
    try:
        if not await _mark_session(session_id):
            logger.info("Chat %s... has no session record yet; the Redis record stands until it does", session_id[:8])
    except Exception as exc:  # noqa: BLE001 -- the Redis record was written; the next read retries this write
        logger.warning("Attachment flag not written to session %s...: %s", session_id[:8], type(exc).__name__)


async def _used_by_durable_state(session_id: str) -> bool:
    return await _session_marked(session_id) or await _has_file_rows(session_id)


async def chat_used_attachment(session_id: str) -> bool:
    """Whether *session_id* ever ran an attachment turn: the Redis record OR the durable state (#20195).

    Durable state is the session record's flag or any file association row, deleted or not. A Redis key that was
    evicted therefore changes nothing; a Redis hit with no session flag writes the flag. Anything unreadable is
    True (fail toward asking).
    """
    try:
        redis = await _record._get_redis()
        if await redis.get(_RECORD_KEY.format(session_id=session_id)) is not None:
            if not await _session_marked(session_id):
                await _mark_session(session_id)  # the session record exists now (or still not: Redis stands)
            return True
        return await _used_by_durable_state(session_id)
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
