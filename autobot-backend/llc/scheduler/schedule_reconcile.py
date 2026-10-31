# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Put back any heartbeat agent or routine that fell off ``llc:heartbeat:schedule`` (#20117).

The set is seeded once, at startup. Every poller claims a member with ``ZREM`` and
re-adds it afterwards, so a failure in between (a Redis error inside the requeue, a
cancellation, a missing croniter, a scheduler that never started) leaves the member
gone until the next restart, with nothing in the log. Ownership of *who may claim
which member* stays in ``schedule_members``; this module only answers "who should be
in the set" and adds the absent ones.

Two rules keep it from fighting the pollers:

* **Add with NX.** A member already present keeps its score, so a reconcile never
  moves a fire time, a rate-limit backoff included.
* **Only the enabled.** A paused or terminated agent, a disabled heartbeat and a
  routine that is not ACTIVE are deliberately off the schedule and stay off.
"""

import asyncio
from datetime import datetime, timezone
from typing import Any, List, Tuple

from sqlalchemy import bindparam, text

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.enums import LLCAgentStatus, RoutineStatus
from .heartbeat_scheduler import _SCHEDULE_KEY, _next_fire
from .schedule_members import ROUTINE_MEMBER_PREFIX

logger = get_logger(__name__)

#: Seconds between reconciles; the longest a lost member stays lost.
SCHEDULE_RECONCILE_INTERVAL_SECONDS = env_float_clamped(
    "AUTOBOT_LLC_SCHEDULE_RECONCILE_INTERVAL_SECONDS", 60.0, min_v=5.0, positive_finite=True
)
_ROUTINE_LIMIT = 10000  # same page the startup load reads
_OFF_STATUSES = (LLCAgentStatus.PAUSED.value, LLCAgentStatus.TERMINATED.value)

#: ``(member, kind, cron)`` -- what the set should hold.
_Wanted = Tuple[str, str, str]


async def _enabled_agents() -> List[_Wanted]:
    """Heartbeat-enabled agents with a cron, excluding paused and terminated ones."""
    factory = get_async_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                "SELECT aon.agent_id, aon.heartbeat_cron FROM agent_org_nodes aon"
                " WHERE aon.heartbeat_enabled = true AND aon.heartbeat_cron IS NOT NULL"
                " AND (aon.status IS NULL OR aon.status NOT IN :off)"
            ).bindparams(bindparam("off", expanding=True)),
            {"off": list(_OFF_STATUSES)},
        )
        return [(row["agent_id"], "agent", row["heartbeat_cron"]) for row in result.mappings().all()]


async def _active_routines() -> List[_Wanted]:
    """ACTIVE routines, as ``routine:<uuid>`` members."""
    from ..services.routine_service import RoutineService

    factory = get_async_session_factory()
    async with factory() as session:
        rows = await RoutineService().list(session, status=RoutineStatus.ACTIVE, limit=_ROUTINE_LIMIT)
    return [(f"{ROUTINE_MEMBER_PREFIX}{r.id}", "routine", r.cron_schedule) for r in rows]


async def _agent_flagged_off(redis: Any, member: str, kind: str) -> bool:
    """Whether the pause flag (set on pause and on terminate) is up for this agent."""
    return kind == "agent" and bool(await redis.exists(f"llc:agent:{member}:paused"))


async def _restore_member(redis: Any, wanted: _Wanted) -> bool:
    """Add one absent member at its next fire time; True when it was missing."""
    member, kind, cron = wanted
    if await _agent_flagged_off(redis, member, kind):
        return False
    next_ts = _next_fire(cron, datetime.now(tz=timezone.utc).timestamp())
    added = await redis.zadd(_SCHEDULE_KEY, {member: next_ts}, nx=True)
    if added:
        logger.warning("Schedule reconcile restored %s %s (next fire %.0f)", kind, member, next_ts)
    return bool(added)


async def reconcile_schedule(redis: Any) -> List[str]:
    """Re-add every enabled agent and active routine missing from the set; return those restored.

    A member whose cron cannot be read is logged and skipped, never allowed to stop the rest.
    """
    wanted = await _enabled_agents() + await _active_routines()
    restored: List[str] = []
    for item in wanted:
        try:
            if await _restore_member(redis, item):
                restored.append(item[0])
        except Exception as exc:  # croniter raises several unrelated types for a bad cron
            logger.error("Schedule reconcile could not restore %s %s: %s", item[1], item[0], exc)
    return restored


async def reconcile_loop(interval: float = SCHEDULE_RECONCILE_INTERVAL_SECONDS) -> None:
    """Reconcile every *interval* seconds until cancelled; one failed pass does not end the loop."""
    while True:
        try:
            redis = await get_async_redis_client()
            if redis is None:
                logger.error("Schedule reconcile skipped: Redis unavailable")
            else:
                await reconcile_schedule(redis)
        except Exception:
            logger.exception("Schedule reconcile pass failed")
        await asyncio.sleep(interval)
