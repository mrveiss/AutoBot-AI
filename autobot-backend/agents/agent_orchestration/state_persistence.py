# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Redis-backed persistence for DistributedAgentManager task-assignment metadata.

Implements the write-through cache strategy from issue #6479:
- Reads always come from the in-memory dicts (fast, synchronous).
- Writes go to both the in-memory dict and Redis (fire-and-forget on Redis failure).
- On restart, :func:`load_task_state` rehydrates the in-memory dicts from Redis so
  stale-detection resumes from the original assignment time rather than starting fresh.

Redis key layout (all scoped to a deployment_id to support future multi-replica use):
    task:assignment:{deployment_id}    hash  task_id -> assigned_at ISO string
    task:progress:{deployment_id}      hash  task_id -> last_progress_at ISO string
    task:reassign:{deployment_id}      hash  task_id -> reassignment_count string
"""

from datetime import datetime
from typing import Dict, Optional, Tuple

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

_ASSIGN_KEY = "task:assignment:{deployment_id}"
_PROGRESS_KEY = "task:progress:{deployment_id}"
_REASSIGN_KEY = "task:reassign:{deployment_id}"
_HASH_TTL_SECONDS = 172_800  # 48 h — covers any reasonably long-running task lifecycle


def _assign_key(dep: str) -> str:
    return _ASSIGN_KEY.format(deployment_id=dep)


def _progress_key(dep: str) -> str:
    return _PROGRESS_KEY.format(deployment_id=dep)


def _reassign_key(dep: str) -> str:
    return _REASSIGN_KEY.format(deployment_id=dep)


async def persist_task_assigned(deployment_id: str, task_id: str, assigned_at: datetime) -> None:
    """Write task assigned_at timestamp to Redis. Failures are logged and swallowed."""
    redis = await get_async_redis_client()
    if redis is None:
        return
    try:
        key = _assign_key(deployment_id)
        await redis.hset(key, task_id, assigned_at.isoformat())
        await redis.expire(key, _HASH_TTL_SECONDS)
    except Exception:
        logger.debug("state_persistence: failed to persist assigned_at for %s", task_id, exc_info=True)


async def persist_task_progress(deployment_id: str, task_id: str, progress_at: datetime) -> None:
    """Write task last_progress_at timestamp to Redis. Failures are logged and swallowed."""
    redis = await get_async_redis_client()
    if redis is None:
        return
    try:
        key = _progress_key(deployment_id)
        await redis.hset(key, task_id, progress_at.isoformat())
        await redis.expire(key, _HASH_TTL_SECONDS)
    except Exception:
        logger.debug("state_persistence: failed to persist progress for %s", task_id, exc_info=True)


async def persist_task_reassignment(deployment_id: str, task_id: str, count: int) -> None:
    """Write reassignment count to Redis. Failures are logged and swallowed."""
    redis = await get_async_redis_client()
    if redis is None:
        return
    try:
        key = _reassign_key(deployment_id)
        await redis.hset(key, task_id, str(count))
        await redis.expire(key, _HASH_TTL_SECONDS)
    except Exception:
        logger.debug("state_persistence: failed to persist reassign count for %s", task_id, exc_info=True)


async def delete_task_state(deployment_id: str, task_id: str) -> None:
    """Remove all three hash entries for task_id. Failures are logged and swallowed."""
    redis = await get_async_redis_client()
    if redis is None:
        return
    try:
        await redis.hdel(_assign_key(deployment_id), task_id)
        await redis.hdel(_progress_key(deployment_id), task_id)
        await redis.hdel(_reassign_key(deployment_id), task_id)
    except Exception:
        logger.debug("state_persistence: failed to delete state for %s", task_id, exc_info=True)


async def load_task_state(
    deployment_id: str,
) -> Tuple[Dict[str, datetime], Dict[str, datetime], Dict[str, int]]:
    """Load all three hashes from Redis for rehydration on startup.

    Returns:
        (assigned_at_map, last_progress_map, reassignment_count_map)
        Each map is empty when Redis is unavailable or keys do not exist.
    """
    redis = await get_async_redis_client()
    if redis is None:
        return {}, {}, {}

    assigned: Dict[str, datetime] = {}
    progress: Dict[str, datetime] = {}
    reassign: Dict[str, int] = {}

    try:
        raw_assign = await redis.hgetall(_assign_key(deployment_id))
        for k, v in raw_assign.items():
            tid = k.decode() if isinstance(k, bytes) else k
            try:
                assigned[tid] = datetime.fromisoformat(v.decode() if isinstance(v, bytes) else v)
            except (ValueError, AttributeError):
                logger.warning("state_persistence: bad assigned_at value for task %s", tid)

        raw_progress = await redis.hgetall(_progress_key(deployment_id))
        for k, v in raw_progress.items():
            tid = k.decode() if isinstance(k, bytes) else k
            try:
                progress[tid] = datetime.fromisoformat(v.decode() if isinstance(v, bytes) else v)
            except (ValueError, AttributeError):
                logger.warning("state_persistence: bad progress value for task %s", tid)

        raw_reassign = await redis.hgetall(_reassign_key(deployment_id))
        for k, v in raw_reassign.items():
            tid = k.decode() if isinstance(k, bytes) else k
            try:
                reassign[tid] = int(v.decode() if isinstance(v, bytes) else v)
            except (ValueError, AttributeError):
                logger.warning("state_persistence: bad reassign_count value for task %s", tid)

    except Exception:
        logger.warning("state_persistence: failed to load task state from Redis", exc_info=True)
        return {}, {}, {}

    return assigned, progress, reassign


async def delete_task_timing_state(deployment_id: str, task_id: str) -> None:
    """Remove only the assigned_at and last_progress entries for task_id.

    Used by _reassign_task, which preserves the reassignment count across
    the handoff so it survives the next add_active_task call.
    """
    redis = await get_async_redis_client()
    if redis is None:
        return
    try:
        await redis.hdel(_assign_key(deployment_id), task_id)
        await redis.hdel(_progress_key(deployment_id), task_id)
    except Exception:
        logger.debug("state_persistence: failed to delete timing for %s", task_id, exc_info=True)


async def cleanup_orphaned_task_state(
    deployment_id: str, active_task_ids: set, max_age_seconds: Optional[int] = None
) -> int:
    """Remove Redis hash entries for tasks not in active_task_ids.

    Called during maintenance to evict orphaned state (e.g. tasks closed without
    going through remove_active_task).  Returns the number of entries removed.
    """
    redis = await get_async_redis_client()
    if redis is None:
        return 0

    removed = 0
    try:
        raw_assign = await redis.hgetall(_assign_key(deployment_id))
        stale_ids = []
        for k in raw_assign:
            tid = k.decode() if isinstance(k, bytes) else k
            if tid not in active_task_ids:
                stale_ids.append(tid)

        for tid in stale_ids:
            await redis.hdel(_assign_key(deployment_id), tid)
            await redis.hdel(_progress_key(deployment_id), tid)
            await redis.hdel(_reassign_key(deployment_id), tid)
            removed += 1

    except Exception:
        logger.warning("state_persistence: cleanup_orphaned failed", exc_info=True)

    return removed
