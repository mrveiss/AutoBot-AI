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
unavailable the functions DENY (#17060): a store that cannot answer is not
a store that answered "nobody owns this".

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

from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.redis_client import get_async_redis_client, redis_delete, redis_set

logger = logging.getLogger(__name__)

_KEY_TPL = "autobot:task_owner:{task_id}"
_TTL_SECONDS = 86_400  # 24 hours


def _key(task_id: str) -> str:
    return _KEY_TPL.format(task_id=task_id)


#: Sentinel distinguishing "the store could not be reached" from "no owner is
#: recorded". #17060: this is the whole fix. ``redis_get`` returns ``None`` for
#: BOTH -- ``autobot_shared/redis_client.py:471-474`` acquires a client and
#: returns ``None`` when there is none, and ``get_async_redis_client`` itself
#: returns ``None`` when Redis is disabled or the circuit breaker is open. It
#: does not raise. So an outage is indistinguishable from an unowned task at that
#: wrapper, in the direction that GRANTS access -- and an ``except`` block around
#: it never runs, which is how a fail-closed fix and a green test suite coexisted
#: with the vulnerability intact.
_STORE_UNAVAILABLE = object()


async def _owner_of(task_id: str):
    """The recorded owner, ``None`` if unowned, or ``_STORE_UNAVAILABLE``.

    Acquires the client directly rather than going through ``redis_get``, because
    that wrapper collapses "no client" into the same ``None`` as "no such key".
    """
    client = await get_async_redis_client()
    if client is None:
        return _STORE_UNAVAILABLE
    raw = await client.get(_key(task_id))
    if raw is None:
        return None
    return raw.decode("utf-8") if isinstance(raw, bytes) else str(raw)


async def register_task_owner(task_id: str, user_id: str) -> bool:
    """Set owner for task_id if not already owned.  Returns True if this call
    established ownership, False if another owner is already recorded.

    Returns False when the store is unavailable (#17060): a write that did not
    happen is not an established owner, and saying it is was how an unowned task
    got adopted by its next caller.
    """
    try:
        existing = await _owner_of(task_id)
        if existing is _STORE_UNAVAILABLE:
            logger.error("task_owner: could not record owner (task=%s user=%s): store unavailable", task_id, user_id)
            return False
        if existing is not None:
            return existing == user_id
        stored = await redis_set(_key(task_id), user_id, expire=_TTL_SECONDS)
        if not stored:
            # The write did not land, or a concurrent writer took the key between
            # the read above and this set. Re-read: only an owner that matches is
            # this caller's.
            existing = await _owner_of(task_id)
            if existing is _STORE_UNAVAILABLE or existing is None:
                logger.error("task_owner: could not record owner (task=%s user=%s)", task_id, user_id)
                return False
            return existing == user_id
        return True
    except Exception as exc:
        logger.error("task_owner: could not record owner (task=%s user=%s): %s", task_id, user_id, exc)
        return False


async def verify_task_owner(task_id: str, user_id: str, user_role: str = "") -> bool:
    """Return True if user_id owns task_id or is an admin.

    Admin bypass: operators must be able to inspect/unblock stuck tasks. It is
    evaluated BEFORE the store is touched, which is what makes denying everyone
    else on an outage a denial of the hole rather than of the feature.

    Registers ownership on first call (first caller becomes owner) -- #17060's
    second criterion, which cannot ship until something records owners at
    creation; see that issue.
    """
    if is_admin_role(user_role):
        return True
    try:
        existing = await _owner_of(task_id)
        if existing is _STORE_UNAVAILABLE:
            # #17060: DENY. This used to be unreachable -- the outage path
            # returned None from redis_get, landed on "unowned", and granted.
            logger.error(
                "task_owner: DENYING (task=%s user=%s) -- ownership store unavailable",
                task_id,
                user_id,
            )
            return False
        if existing is None:
            await register_task_owner(task_id, user_id)
            return True
        return existing == user_id
    except Exception as exc:
        # A command that failed after a good connection (mid-flight disconnect,
        # OOM, LOADING). Distinct from the unavailable branch above and denied
        # for the same reason.
        logger.error(
            "task_owner: DENYING (task=%s user=%s) -- ownership store error: %s",
            task_id,
            user_id,
            exc,
        )
        return False


async def release_task_owner(task_id: str) -> None:
    """Delete the ownership record when a task completes or is abandoned."""
    try:
        await redis_delete(_key(task_id))
    except Exception as exc:
        logger.warning("task_owner: failed to release ownership (task=%s): %s", task_id, exc)
