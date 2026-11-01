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
from typing import Any, List, NamedTuple, Set, Tuple

from sqlalchemy import bindparam, select, text

from autobot_shared.env_utils import env_float_clamped
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.enums import LLCAgentStatus, RoutineStatus
from ..models.routine import LLCRoutine
from ..services.controls_service import NEVER_SCHEDULED_STATUSES
from .heartbeat_scheduler import _SCHEDULE_KEY, _next_fire
from .schedule_members import ROUTINE_MEMBER_PREFIX

logger = get_logger(__name__)

#: Seconds between reconciles; the longest a lost member stays lost.
SCHEDULE_RECONCILE_INTERVAL_SECONDS = env_float_clamped(
    "AUTOBOT_LLC_SCHEDULE_RECONCILE_INTERVAL_SECONDS", 60.0, min_v=30.0, positive_finite=True
)
_ROUTINE_PAGE = 1000
#: Off the schedule on purpose. ``on_leave`` and ``offboarding`` are NOT here: nothing in the
#: code stops the poller waking such an agent, and a reconcile stricter than the poller would
#: leave a member absent that the poller still fires once it is present.
_OFF_STATUSES = tuple(sorted(NEVER_SCHEDULED_STATUSES | {LLCAgentStatus.PAUSED.value}))
_BAD_CRON_CAP = 1000
_reported_bad_crons: Set[Tuple[str, str]] = set()


class _Wanted(NamedTuple):
    """One member the set should hold, and the Redis pause flags that keep it off."""

    member: str
    kind: str
    cron: str
    pause_keys: Tuple[str, ...]


def _pause_keys(agent_id: Any, company_id: Any) -> Tuple[str, ...]:
    keys = []
    if agent_id:
        keys.append(f"llc:agent:{agent_id}:paused")
    if company_id:
        keys.append(f"llc:company:{company_id}:paused")
    return tuple(keys)


async def _enabled_agents() -> List[_Wanted]:
    """Heartbeat-enabled agents with a non-blank cron, excluding off statuses."""
    factory = get_async_session_factory()
    async with factory() as session:
        result = await session.execute(
            text(
                "SELECT aon.agent_id, aon.heartbeat_cron, aon.company_id FROM agent_org_nodes aon"
                " WHERE aon.heartbeat_enabled = true AND btrim(coalesce(aon.heartbeat_cron, '')) <> ''"
                " AND (aon.status IS NULL OR aon.status NOT IN :off) ORDER BY aon.agent_id"
            ).bindparams(bindparam("off", expanding=True)),
            {"off": list(_OFF_STATUSES)},
        )
        return [
            _Wanted(r["agent_id"], "agent", r["heartbeat_cron"], _pause_keys(r["agent_id"], r["company_id"]))
            for r in result.mappings().all()
        ]


async def _active_routines() -> List[_Wanted]:
    """ACTIVE routines with a non-blank cron, read in id order so paging cannot skip any."""
    wanted: List[_Wanted] = []
    factory = get_async_session_factory()
    async with factory() as session:
        offset = 0
        while True:
            stmt = select(LLCRoutine).where(LLCRoutine.status == RoutineStatus.ACTIVE)
            rows = list(
                (await session.execute(stmt.order_by(LLCRoutine.id).limit(_ROUTINE_PAGE).offset(offset))).scalars()
            )
            wanted += [
                _Wanted(
                    f"{ROUTINE_MEMBER_PREFIX}{r.id}",
                    "routine",
                    r.cron_schedule,
                    _pause_keys(r.assignee_agent_id, r.company_id),
                )
                for r in rows
                if (r.cron_schedule or "").strip()
            ]
            if len(rows) < _ROUTINE_PAGE:
                return wanted
            offset += _ROUTINE_PAGE


async def _present_members(redis: Any) -> Set[str]:
    """Every member of the schedule set, in one read."""
    return {m.decode() if isinstance(m, bytes) else m for m in await redis.zrange(_SCHEDULE_KEY, 0, -1)}


async def _flagged_off(redis: Any, absent: List[_Wanted]) -> Set[str]:
    """Members of *absent* with a pause flag up, from one pipelined round trip of EXISTS."""
    checks = [(w.member, key) for w in absent for key in w.pause_keys]
    if not checks:
        return set()
    pipe = redis.pipeline(transaction=False)
    for _, key in checks:
        pipe.exists(key)
    results = await pipe.execute()
    return {member for (member, _), hit in zip(checks, results) if hit}


def _next_or_report(item: _Wanted) -> float | None:
    """The next fire time, or None after reporting an unusable cron once per member and value."""
    try:
        return _next_fire(item.cron, datetime.now(tz=timezone.utc).timestamp())
    except Exception as exc:  # croniter raises several unrelated types for a bad cron
        seen = (item.member, item.cron)
        if seen in _reported_bad_crons:
            logger.debug("Schedule reconcile: %s %s still has an unusable cron", item.kind, item.member)
        else:
            if len(_reported_bad_crons) >= _BAD_CRON_CAP:
                _reported_bad_crons.clear()
            _reported_bad_crons.add(seen)
            logger.error("Schedule reconcile could not restore %s %s: %s", item.kind, item.member, exc)
        return None


async def restore_lost_schedule_members(redis: Any) -> List[str]:
    """Re-add every enabled agent and active routine missing from the set; return those restored.

    One read of the set finds who is absent; only those are checked for a pause flag and
    added with NX, so a present member is never touched.
    """
    present = await _present_members(redis)
    absent = [w for w in await _enabled_agents() + await _active_routines() if w.member not in present]
    off = await _flagged_off(redis, absent)
    restored: List[str] = []
    for item in absent:
        next_ts = None if item.member in off else _next_or_report(item)
        if next_ts is not None and await redis.zadd(_SCHEDULE_KEY, {item.member: next_ts}, nx=True):
            logger.warning("Schedule reconcile restored %s %s (next fire %.0f)", item.kind, item.member, next_ts)
            restored.append(item.member)
    return restored


async def reconcile_loop(interval: float = SCHEDULE_RECONCILE_INTERVAL_SECONDS) -> None:
    """Reconcile every *interval* seconds until cancelled; one failed pass does not end the loop.

    The first pass waits one interval: the loop starts while the schedulers are still seeding the
    set, and a pass that beat them would log their own seeding as a restoration (#20232).
    """
    while True:
        await asyncio.sleep(interval)
        try:
            redis = await get_async_redis_client()
            if redis is None:
                logger.error("Schedule reconcile skipped: Redis unavailable")
            else:
                await restore_lost_schedule_members(redis)
        except Exception:
            logger.exception("Schedule reconcile pass failed")
