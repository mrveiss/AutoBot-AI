# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Task owner registry — Redis-backed task_id → user_id mapping (#10553).

Prevents IDOR on task-mutation endpoints (/steer, /answer) by recording the
first user to touch a task and rejecting subsequent callers with a different
user_id.

Key layout:
    autobot:task_owner:{task_id}  ->  user_id string, TTL = 24 h

The owner is registered atomically using SET NX (first writer wins) so a race
between two concurrent first-touches cannot split ownership.  If Redis is
unavailable the function degrades gracefully (logs a warning, allows the call)
rather than blocking all task interaction.

Limitations / known gap:
  - Task ownership is recorded on first steer/answer, not on task creation.
    If a task_id is guessed by an adversary who steers it before the real
    owner does, they become the owner.  A future improvement: record ownership
    when run_task() is called from the chat API and the user context is known.
  - admin-role users bypass the owner check so operators can inspect / unblock
    tasks without knowing the original owner.
"""

from __future__ import annotations

import logging

from autobot_shared.redis_client import redis_delete, redis_get, redis_set

logger = logging.getLogger(__name__)

_KEY_TPL = "autobot:task_owner:{task_id}"
_TTL_SECONDS = 86_400  # 24 hours


def _key(task_id: str) -> str:
    return _KEY_TPL.format(task_id=task_id)


async def register_task_owner(task_id: str, user_id: str) -> bool:
    """Set owner for task_id if not already owned.  Returns True if this call
    established ownership (SET NX), False if another owner is already recorded.
    On Redis error returns True (fail-open, gap logged).
    """
    try:
        client_key = _key(task_id)
        existing = await redis_get(client_key)
        if existing is not None:
            existing_str = existing.decode("utf-8") if isinstance(existing, bytes) else str(existing)
            return existing_str == user_id
        # SET NX — only first writer wins the race.
        stored = await redis_set(client_key, user_id, expire=_TTL_SECONDS)
        if not stored:
            # Key was set by a concurrent writer between our GET and SET; read it back.
            existing = await redis_get(client_key)
            if existing is not None:
                existing_str = existing.decode("utf-8") if isinstance(existing, bytes) else str(existing)
                return existing_str == user_id
        return True
    except Exception as exc:
        logger.warning("task_owner: Redis unavailable — ownership check skipped (task=%s): %s", task_id, exc)
        return True  # fail-open: block Redis outage from halting all tasks


async def verify_task_owner(task_id: str, user_id: str, user_role: str = "") -> bool:
    """Return True if user_id owns task_id or is an admin.

    Admin bypass: operators must be able to inspect/unblock stuck tasks.
    Registers ownership on first call (first caller becomes owner).
    """
    if user_role == "admin":
        return True
    try:
        client_key = _key(task_id)
        existing = await redis_get(client_key)
        if existing is None:
            # Not yet owned — register this caller as the owner.
            await register_task_owner(task_id, user_id)
            return True
        existing_str = existing.decode("utf-8") if isinstance(existing, bytes) else str(existing)
        return existing_str == user_id
    except Exception as exc:
        logger.warning("task_owner: Redis unavailable — ownership check skipped (task=%s): %s", task_id, exc)
        return True  # fail-open


async def release_task_owner(task_id: str) -> None:
    """Delete the ownership record when a task completes or is abandoned."""
    try:
        await redis_delete(_key(task_id))
    except Exception as exc:
        logger.warning("task_owner: failed to release ownership (task=%s): %s", task_id, exc)
