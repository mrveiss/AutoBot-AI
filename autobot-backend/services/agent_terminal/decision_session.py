# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The session a decision acts on: read from Redis, never from a worker's cache (#20674).

``SessionManager.get_session`` may serve the cached copy when Redis fails; that is right for display and
wrong for an approval, where a stale ``pending_approval`` could be approved again. This is the read an
approve or deny uses. Redis down, or the record missing, raises ``ApprovalStateUnavailableError``.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from type_defs.common import Metadata

from .models import AgentTerminalSession
from .session_state import (
    APPROVAL_STATE_UNAVAILABLE,
    ApprovalStateUnavailableError,
    apply_record,
    read_authoritative_record,
    session_from_record,
)

logger = get_logger(__name__)

__all__ = ["claim_for_decision", "session_for_decision"]


async def session_for_decision(manager, session_id: str) -> AgentTerminalSession | None:
    """The session brought up to date with its Redis record; ``None`` if no such session exists.

    Raises ``ApprovalStateUnavailableError`` when Redis cannot confirm the record, or has none while
    this worker still holds a copy.
    """
    data = await read_authoritative_record(manager.redis_client, session_id)
    async with manager._sessions_lock:
        cached = manager.sessions.get(session_id)
    if data is None:
        return await _rebuilt_for_decision(manager, session_id, cached)
    if cached:
        apply_record(cached, data)
        return cached
    async with manager._sessions_lock:
        return manager.sessions.setdefault(session_id, session_from_record(data))


async def _rebuilt_for_decision(manager, session_id: str, cached) -> AgentTerminalSession | None:
    """No record. A cached copy is no authority; a session rebuilt from chat history (#13478) gets a record."""
    if cached:
        raise ApprovalStateUnavailableError(f"session {session_id} has no record in Redis")
    session = await manager._rebuild_session_from_pending_approval(session_id)
    if session is None:
        return None
    if not await manager._persist_session(session):
        async with manager._sessions_lock:
            manager.sessions.pop(session_id, None)
        raise ApprovalStateUnavailableError(f"could not record the rebuilt session {session_id}")
    return session


async def claim_for_decision(manager, session_id: str) -> tuple[AgentTerminalSession | None, Metadata | None]:
    """The session and the one decision claim on its pending approval, or the refusal to return (#20674).

    Reads Redis, not the cache, and fails closed: if the approval's state cannot be confirmed nothing is
    decided and nothing runs.
    """
    try:
        session = await session_for_decision(manager, session_id)
        if not session:
            return None, {"status": "error", "error": "Session not found"}
        if not session.has_pending_approval() or not await manager.claim_decision(session):
            return None, {"status": "error", "error": "No pending approval"}
    except ApprovalStateUnavailableError as exc:
        logger.error("Approval on session %s refused, its state is unconfirmed: %s", session_id, exc)
        return None, {"status": "error", "error": APPROVAL_STATE_UNAVAILABLE}
    return session, None
