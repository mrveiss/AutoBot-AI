# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Atomic task-claim service via Redis SET NX EX (GH#6468).

Eliminates double-pickup races in distributed agent fleets.  A single
Redis round-trip atomically grants or denies the claim; the TTL auto-frees
a claim when the agent dies.

Key layout:
    task:claim:{task_id}  ->  agent_id string, TTL = claim_ttl_seconds

Claim lifecycle:
  1. claim_task()    -- SET NX EX; returns True only to the first caller.
  2. renew_claim()   -- Lua EXPIRE guard; keeps TTL alive while agent works.
  3. release_claim() -- Lua DEL-if-owner; prevents stealing the delete.

The in-memory dicts in DistributedAgentManager remain as an observability
cache, not the source of truth for claim ownership.
"""

from __future__ import annotations

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from services.audit.audit import AuditCategory, AuditEvent, emit

logger = get_logger(__name__)

_CLAIM_KEY_TPL = "task:claim:{task_id}"
_DEFAULT_TTL = 300  # seconds — covers a full heartbeat run with margin

# Lua: release only if the caller still owns the key.
_RELEASE_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
else
    return 0
end
"""

# Lua: extend TTL only if the caller still owns the key.
_RENEW_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
else
    return 0
end
"""


def _key(task_id: str) -> str:
    return _CLAIM_KEY_TPL.format(task_id=task_id)


async def claim_task(task_id: str, agent_id: str, ttl: int = _DEFAULT_TTL) -> bool:
    """Atomically claim task_id for agent_id.

    Uses SET NX EX — only one agent can win for a given task_id.  Returns
    True when the claim was granted, False when already owned by another agent.
    Redis unavailability is treated as granted (fail-open) so a Redis outage
    does not block all work.
    """
    redis = await get_async_redis_client()
    if redis is None:
        logger.warning(
            "task_claim: Redis unavailable — allowing claim task=%s agent=%s (fail-open)",
            task_id,
            agent_id,
        )
        _emit_audit("task.claim", agent_id, task_id, outcome="redis_unavailable")
        return True
    try:
        result = await redis.set(_key(task_id), agent_id, nx=True, ex=ttl)
        granted = result is not None
        outcome = "granted" if granted else "denied"
        logger.debug("task_claim: task=%s agent=%s %s", task_id, agent_id, outcome)
        _emit_audit("task.claim", agent_id, task_id, outcome=outcome)
        return granted
    except Exception:
        logger.warning(
            "task_claim: Redis error during claim task=%s agent=%s — fail-open",
            task_id,
            agent_id,
            exc_info=True,
        )
        _emit_audit("task.claim", agent_id, task_id, outcome="redis_error")
        return True


async def renew_claim(task_id: str, agent_id: str, ttl: int = _DEFAULT_TTL) -> bool:
    """Extend TTL on an existing claim owned by agent_id.

    Returns True when the renewal succeeded, False when the key is gone or
    owned by a different agent (claim was stolen or expired).
    """
    redis = await get_async_redis_client()
    if redis is None:
        return True  # fail-open
    try:
        script = redis.register_script(_RENEW_LUA)
        result = await script(keys=[_key(task_id)], args=[agent_id, str(ttl)])
        renewed = bool(result)
        if not renewed:
            logger.warning(
                "task_claim: renew failed (claim lost?) task=%s agent=%s",
                task_id,
                agent_id,
            )
        _emit_audit("task.renew", agent_id, task_id, outcome="ok" if renewed else "lost")
        return renewed
    except Exception:
        logger.warning(
            "task_claim: Redis error during renew task=%s agent=%s",
            task_id,
            agent_id,
            exc_info=True,
        )
        return True  # fail-open


async def release_claim(task_id: str, agent_id: str) -> bool:
    """Release the claim on task_id if still owned by agent_id.

    Returns True when the key was deleted, False when not owned (already
    expired or stolen).
    """
    redis = await get_async_redis_client()
    if redis is None:
        return True  # fail-open
    try:
        script = redis.register_script(_RELEASE_LUA)
        result = await script(keys=[_key(task_id)], args=[agent_id])
        released = bool(result)
        logger.debug(
            "task_claim: release task=%s agent=%s released=%s",
            task_id,
            agent_id,
            released,
        )
        _emit_audit("task.release", agent_id, task_id, outcome="released" if released else "not_owned")
        return released
    except Exception:
        logger.warning(
            "task_claim: Redis error during release task=%s agent=%s",
            task_id,
            agent_id,
            exc_info=True,
        )
        return True  # fail-open


async def is_claim_alive(task_id: str) -> bool:
    """Return True when the Redis claim key for task_id still exists.

    Used by stale-task detection: if the key is gone its TTL has expired,
    meaning the agent died and the task is free to be reassigned.
    """
    redis = await get_async_redis_client()
    if redis is None:
        return True  # fail-open: assume alive when Redis is down
    try:
        return bool(await redis.exists(_key(task_id)))
    except Exception:
        logger.debug(
            "task_claim: Redis error checking claim existence for task=%s",
            task_id,
            exc_info=True,
        )
        return True  # fail-open


def _emit_audit(action: str, agent_id: str, task_id: str, outcome: str = "ok") -> None:
    emit(
        AuditEvent(
            category=AuditCategory.GOVERNANCE,
            action=action,
            actor_id=agent_id,
            resource_type="task",
            resource_id=task_id,
            outcome=outcome,
        )
    )
