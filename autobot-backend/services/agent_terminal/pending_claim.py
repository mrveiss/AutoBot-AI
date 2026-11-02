# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One pending approval per terminal session, across workers (#20059).

A session's state reaches Redis only after the queue write, and each uvicorn worker keeps its own copy,
so the in-process check from #19951 cannot see another worker's approval. A yes to the first card would
then run the second command. The claim is taken in Redis before anything is written.

A claim starts on a short TTL, so a worker dying before it persists frees the session by itself. Persisting
the pending approval lifts it to the session's own TTL. Deciding releases it.

If a release is lost, the claim outlives its approval. A claim past the short TTL always had its approval
persisted, so one whose persisted session no longer shows that approval is taken over.
"""

from __future__ import annotations

import json

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_utils import delete_if_value, expire_if_value
from constants.ttl_constants import TTL_5_MINUTES

from .redis_usability import usable_redis

logger = get_logger(__name__)

CLAIM_WRITE_TTL = TTL_5_MINUTES


def _claim_key(session_id: str) -> str:
    return f"agent_terminal:pending_claim:{session_id}"


async def _is_abandoned(redis, session_id: str, holder: str) -> bool:
    """True if the claim outlived the write window and the persisted session no longer holds its approval."""
    if await redis.ttl(_claim_key(session_id)) <= CLAIM_WRITE_TTL:
        return False
    raw = await redis.get(f"agent_terminal:session:{session_id}")
    pending = json.loads(raw).get("pending_approval") if raw else None
    return (pending or {}).get("command_id") != holder


async def claim_pending_slot(redis, session_id: str, command_id: str) -> bool:
    """Take the session's slot for *command_id*; ``False`` if another command holds it.

    Raises on a Redis error, so the caller can refuse: holding a command back is the safe outcome here.
    """
    key = _claim_key(session_id)
    if await redis.set(key, command_id, nx=True, ex=CLAIM_WRITE_TTL):
        return True
    holder = await redis.get(key)
    if holder is None:
        return bool(await redis.set(key, command_id, nx=True, ex=CLAIM_WRITE_TTL))
    holder = holder.decode("utf-8") if isinstance(holder, bytes) else holder
    if not await _is_abandoned(redis, session_id, holder):
        return False
    logger.warning("Taking over the abandoned approval claim of session %s", session_id)
    await delete_if_value(redis, key, holder)
    return bool(await redis.set(key, command_id, nx=True, ex=CLAIM_WRITE_TTL))


async def hold_pending_slot(redis, session_id: str, command_id: str | None, ttl: int) -> None:
    """Keep *command_id*'s claim alive for *ttl* seconds, now its approval is persisted.

    An approval restored from chat history has no command id, so it has no claim to keep.
    """
    if not command_id:
        return
    await expire_if_value(redis, _claim_key(session_id), command_id, ttl * 1000)


async def release_pending_slot(redis, session_id: str, command_id: str | None) -> None:
    """Free the slot if *command_id* holds it. A failure is logged: the TTL and the takeover still free it."""
    if not command_id or not usable_redis(redis):
        return
    try:
        await delete_if_value(redis, _claim_key(session_id), command_id)
    except Exception as exc:  # noqa: BLE001 - the decision has landed; a lost release must not undo it
        logger.error("Could not release the approval claim of session %s: %s", session_id, exc)


async def drop_pending_slot(redis, session_id: str) -> None:
    """Free the slot of a session being closed, whichever command holds it."""
    await redis.delete(_claim_key(session_id))
