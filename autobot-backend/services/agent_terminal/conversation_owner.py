# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Who owns the conversation that drives an agent-terminal session (#17053).

Sessions the chat workflow creates carry no caller, so their owner is resolved
the way the chat ownership gate resolves a conversation's: the session file's
owner (the record of truth, THREAT_MODEL.md section 2), else the grant the gate
writes -- to Redis only -- when it hands a never-owned conversation to its first
caller (legacy_migration), which the message now being processed has just
passed. None, from either an absent owner or a failed read, leaves the session
admin-only.
"""

from typing import Any, Optional

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


async def conversation_owner(chat_history_manager: Any, conversation_id: Optional[str]) -> Optional[str]:
    """The conversation's owner username, or None."""
    if not conversation_id:
        return None
    return await _durable_owner(chat_history_manager, conversation_id) or await _granted_owner(conversation_id)


async def _durable_owner(chat_history_manager: Any, conversation_id: str) -> Optional[str]:
    """The owner recorded in the chat session file, or None."""
    if not chat_history_manager:
        return None
    try:
        owner = await chat_history_manager.get_session_owner(conversation_id)
    except Exception as exc:
        logger.warning("Could not read the owner of conversation %s: %s", conversation_id[:8], exc)
        return None
    return owner if isinstance(owner, str) and owner else None


async def _granted_owner(conversation_id: str) -> Optional[str]:
    """The owner the chat ownership gate recorded in Redis, or None."""
    from autobot_shared.redis_client import get_redis_client  # noqa: PLC0415 -- read at call time
    from security.session_ownership import SessionOwnershipValidator  # noqa: PLC0415 -- avoids an import cycle

    try:
        redis = await get_redis_client(async_client=True, database="main")
        owner = await SessionOwnershipValidator(redis).get_session_owner(conversation_id) if redis else None
    except Exception as exc:
        logger.warning("Could not read the granted owner of conversation %s: %s", conversation_id[:8], exc)
        return None
    return owner if isinstance(owner, str) and owner else None
