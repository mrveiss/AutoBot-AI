# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Put one agent on the heartbeat schedule the moment its heartbeat is enabled (#15907).

``LLCHeartbeatScheduler._repopulate_schedule`` reads ``heartbeat_enabled = true``
agents only at ``start()``. An agent switched on afterwards -- a hire sent with
``heartbeat_enabled=true``, or the owner waking a CEO from its page -- was never
added to the sorted set until the next process restart: the flag said yes and
the schedule the poll loop reads said nothing.

Switching **off** needs no counterpart here. The poll loop resolves a due agent
with ``require_enabled=True`` and removes it from the set when that finds no
row, so a disabled agent drops out at its next fire time without ever running.

Call this only after the transaction that set the flag has committed: the poll
loop re-reads the row, and an uncommitted ``true`` reads as ``false`` there.
"""

from datetime import datetime, timezone

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

from .heartbeat_scheduler import _SCHEDULE_KEY, _next_fire

logger = get_logger(__name__)


async def schedule_heartbeat(agent_id: str, cron_expr: str) -> bool:
    """Add *agent_id* to the heartbeat schedule at its next cron fire time.

    Returns True when the agent was scheduled. A missing Redis or an unusable
    cron is logged and returns False, never raised: the database flag is the
    authority, and the scheduler's next ``start()`` repopulates from it.
    """
    redis = await get_async_redis_client()
    if redis is None:
        logger.error("Redis unavailable: agent %s is heartbeat-enabled but not scheduled until restart", agent_id)
        return False
    try:
        next_ts = _next_fire(cron_expr, datetime.now(tz=timezone.utc).timestamp())
    except Exception as exc:  # croniter raises several unrelated types for a bad cron
        logger.error("Cron %r unusable for agent %s: %s", cron_expr, agent_id, exc)
        return False
    # NX: an agent already on the schedule keeps its score (a rate-limit backoff included).
    await redis.zadd(_SCHEDULE_KEY, {agent_id: next_ts}, nx=True)
    logger.info("Heartbeat scheduled agent=%s next=%.0f", agent_id, next_ts)
    return True
