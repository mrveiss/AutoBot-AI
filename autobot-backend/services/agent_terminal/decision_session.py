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

import asyncio

from autobot_shared.async_compat import fire_and_forget
from autobot_shared.logging_manager import get_logger
from type_defs.common import Metadata

from .models import AgentTerminalSession
from .session_state import (
    APPROVAL_STATE_UNAVAILABLE,
    ApprovalStateUnavailableError,
    apply_record,
    read_authoritative_record,
    release_decision,
    session_from_record,
)

logger = get_logger(__name__)

#: Waits between attempts to give a failed run's claim back, after Redis refused the first.
_RELEASE_RETRY_DELAYS_SECONDS = (1, 5, 30, 120)

__all__ = ["claim_for_decision", "mark_queued_approved", "release_with_retry", "session_for_decision"]


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
    return await manager._rebuild_session_from_pending_approval(session_id)  # records it before returning it


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


async def release_with_retry(redis, session_id: str, decision_id: str | None, token: str) -> None:
    """Give a failed run's claim back. If Redis refuses, keep the token and retry in the background (#20674).

    The release is token-checked, so a retry cannot free a claim that a later decision took.
    """
    try:
        await release_decision(redis, session_id, decision_id, token)
    except Exception as exc:  # noqa: BLE001 - the claim stays live until a retry lands or its TTL lapses
        logger.error("Could not release the claim of approval %s on session %s: %s", decision_id, session_id, exc)
        fire_and_forget(_retry_release(redis, session_id, decision_id, token), name=f"retry-release-{session_id}")


async def _retry_release(redis, session_id: str, decision_id: str | None, token: str) -> None:
    for delay in _RELEASE_RETRY_DELAYS_SECONDS:
        await asyncio.sleep(delay)
        try:
            await release_decision(redis, session_id, decision_id, token)
            return
        except Exception as exc:  # noqa: BLE001 - try again until the delays run out
            logger.warning("Release of approval %s on session %s still failing: %s", decision_id, session_id, exc)
    logger.error("Approval %s of session %s stays claimed until its claim expires", decision_id, session_id)


async def mark_queued_approved(approval_handler, session_manager, session, command_id, user_id, comment) -> None:
    """Record the approval on the queued command. Nothing has started yet, so a failure or a cancellation
    here gives the decision claim back and the user can approve again (#20674)."""
    try:
        await approval_handler.update_command_queue_status(
            command_id=command_id, approved=True, user_id=user_id, comment=comment
        )
    except BaseException:
        await session_manager.release_after_failed_run(session)
        raise
