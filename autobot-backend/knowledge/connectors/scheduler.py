# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Connector Scheduler — multi-worker safe (Issue #6556)

Schedule definitions are persisted to Redis so they survive worker restarts.
A single elected "leader" worker runs the asyncio sync tasks; all workers
answer is_running() consistently via Redis.

Leader election: Redis SETNX with a TTL lease.  On leader death the TTL
expires and another worker claims leadership within LEADER_POLL_S seconds,
then rehydrates all schedules from Redis automatically.
"""

import asyncio
import json
import re
import time
from typing import Dict

from autobot_shared.leader_lease import LeaderLease
from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Schedule parsing
# ---------------------------------------------------------------------------

_NAMED_SCHEDULES: Dict[str, int] = {
    "@minutely": 60,
    "@hourly": 3600,
    "@daily": 86400,
    "@weekly": 604800,
}


def _parse_interval_seconds(schedule: str) -> int | None:
    """Return the repeat interval in seconds for a simple schedule string.

    Supported formats:
        ``@minutely``  -> 60 s
        ``@hourly``    -> 3600 s
        ``@daily``     -> 86400 s
        ``@weekly``    -> 604800 s
        ``*/N``        -> N minutes (e.g. ``*/15`` -> 900 s)
        ``N``          -> N minutes (plain integer string)

    Returns None for unrecognised schedules.
    """
    schedule = schedule.strip().lower()

    if schedule in _NAMED_SCHEDULES:
        return _NAMED_SCHEDULES[schedule]

    # */N  or  */N * * * *  (first field only)
    m = re.match(r"^\*/(\d+)", schedule)
    if m:
        minutes = int(m.group(1))
        return max(minutes, 1) * 60

    # plain integer = minutes
    if re.match(r"^\d+$", schedule):
        return max(int(schedule), 1) * 60

    return None


# ---------------------------------------------------------------------------
# Redis key constants
# ---------------------------------------------------------------------------

_SCHEDULE_PREFIX = "connector:schedule:"
_LEADER_KEY = "connector:scheduler:leader"


def _decode(val: object) -> str:
    """Decode bytes to str; pass-through str."""
    return val.decode() if isinstance(val, bytes) else val  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class ConnectorScheduler:
    """Multi-worker-safe connector scheduler backed by Redis.

    Schedule definitions live in Redis (``connector:schedule:{id}``).
    One elected leader worker runs the asyncio tasks.  All workers read
    Redis for a consistent ``is_running()`` answer.
    """

    def __init__(self) -> None:
        self._tasks: Dict[str, asyncio.Task] = {}
        # GH#12835: leader election lives in autobot_shared.leader_lease, shared
        # with skill_distillation_scheduler. Only the key and database are ours.
        self._lease = LeaderLease(key=_LEADER_KEY, database="knowledge", label="Connector scheduler")
        self._leader_task: asyncio.Task | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start(self, connector_id: str, schedule: str) -> bool:
        """Persist schedule to Redis and start a local task when leader.

        Non-leader workers persist the schedule; the leader picks it up on
        its next reconciliation cycle (~10 s).

        Returns:
            True if the schedule was accepted, False on parse error.
        """
        interval = _parse_interval_seconds(schedule)
        if interval is None:
            logger.error(
                "Cannot schedule connector %s: unrecognised schedule '%s'",
                connector_id,
                schedule,
            )
            return False

        await self._redis_set_schedule(connector_id, schedule, interval)

        if self._lease.is_leader:
            await self._start_local_task(connector_id, interval)

        logger.info(
            "Scheduled connector %s every %d seconds (schedule='%s')",
            connector_id,
            interval,
            schedule,
        )
        return True

    async def stop(self, connector_id: str) -> None:
        """Remove schedule from Redis and cancel any local task."""
        await self._redis_del_schedule(connector_id)
        await self._cancel_local_task(connector_id)
        logger.info("Stopped scheduled connector %s", connector_id)

    async def stop_all(self) -> None:
        """Cancel all local asyncio tasks without touching Redis schedules.

        Used on graceful worker shutdown.  Redis schedule definitions survive
        so the next elected leader rehydrates them automatically.
        """
        ids = list(self._tasks.keys())
        for connector_id in ids:
            await self._cancel_local_task(connector_id)
        if self._leader_task and not self._leader_task.done():
            self._leader_task.cancel()
            try:
                await self._leader_task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped all %d local connector scheduler tasks", len(ids))

    async def is_running(self, connector_id: str) -> bool:
        """Return True if a schedule entry exists in Redis for *connector_id*.

        Reads from Redis so the answer is consistent across all workers.
        """
        redis = await get_async_redis_client(database="knowledge")
        if redis is None:
            return False
        try:
            return bool(await redis.exists(_SCHEDULE_PREFIX + connector_id))
        except Exception as exc:
            logger.warning("is_running Redis check failed for %s: %s", connector_id, exc)
            return False

    def list_scheduled(self) -> Dict[str, bool]:
        """Return {connector_id: is_running} for locally active tasks (leader only)."""
        return {cid: not t.done() for cid, t in self._tasks.items()}

    # ------------------------------------------------------------------
    # Leader election
    # ------------------------------------------------------------------

    async def begin_leader_election(self) -> None:
        """Spawn the background leader-election loop (call once at worker startup)."""
        if self._leader_task is None or self._leader_task.done():
            self._leader_task = asyncio.create_task(
                self._leader_loop(),
                name="connector-scheduler-leader",
            )

    async def _leader_loop(self) -> None:
        """Hold or contest the leader lease, reconciling schedules while leader."""
        await self._lease.run(
            on_tick=self._reconcile_schedules,
            on_lost=self._cancel_all_local_tasks,
        )


    # ------------------------------------------------------------------
    # Schedule reconciliation (leader only)
    # ------------------------------------------------------------------

    async def _reconcile_schedules(self) -> None:
        """Sync local asyncio tasks with Redis: start missing ones, cancel orphaned ones."""
        redis = await get_async_redis_client(database="knowledge")
        if redis is None:
            return
        try:
            persisted: Dict[str, int] = {}
            async for key in redis.scan_iter(match=_SCHEDULE_PREFIX + "*"):
                raw = await redis.get(key)
                if raw is None:
                    continue
                data = json.loads(raw)
                persisted[data["connector_id"]] = data["interval_seconds"]

            for cid, interval in persisted.items():
                task = self._tasks.get(cid)
                if task is None or task.done():
                    await self._start_local_task(cid, interval)

            orphaned = [cid for cid in list(self._tasks) if cid not in persisted]
            for cid in orphaned:
                await self._cancel_local_task(cid)

        except Exception as exc:
            logger.error("Schedule reconciliation failed: %s", exc)

    # ------------------------------------------------------------------
    # Local asyncio task helpers
    # ------------------------------------------------------------------

    async def _start_local_task(self, connector_id: str, interval: int) -> None:
        await self._cancel_local_task(connector_id)
        task = asyncio.create_task(
            self._run_loop(connector_id, interval),
            name="connector-scheduler-%s" % connector_id,
        )
        self._tasks[connector_id] = task

    async def _cancel_local_task(self, connector_id: str) -> None:
        task = self._tasks.pop(connector_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _cancel_all_local_tasks(self) -> None:
        for cid in list(self._tasks):
            await self._cancel_local_task(cid)

    # ------------------------------------------------------------------
    # Redis persistence helpers
    # ------------------------------------------------------------------

    async def _redis_set_schedule(self, connector_id: str, schedule: str, interval: int) -> None:
        redis = await get_async_redis_client(database="knowledge")
        if redis is None:
            logger.warning("Redis unavailable - schedule for %s not persisted", connector_id)
            return
        data = json.dumps(
            {"connector_id": connector_id, "schedule": schedule, "interval_seconds": interval},
            ensure_ascii=False,
        )
        await redis.set(_SCHEDULE_PREFIX + connector_id, data)

    async def _redis_del_schedule(self, connector_id: str) -> None:
        redis = await get_async_redis_client(database="knowledge")
        if redis is None:
            return
        await redis.delete(_SCHEDULE_PREFIX + connector_id)

    # ------------------------------------------------------------------
    # Sync loop (unchanged from original)
    # ------------------------------------------------------------------

    async def _run_loop(self, connector_id: str, interval_seconds: int) -> None:
        """Sleep -> sync -> repeat until cancelled."""
        logger.info("Scheduler loop started for connector %s (interval=%ds)", connector_id, interval_seconds)
        while True:
            try:
                await asyncio.sleep(interval_seconds)
                await self._trigger_sync(connector_id)
            except asyncio.CancelledError:
                logger.info("Scheduler loop cancelled for connector %s", connector_id)
                break
            except Exception as exc:
                logger.error("Scheduler loop error for connector %s: %s", connector_id, exc)

    async def _trigger_sync(self, connector_id: str) -> None:
        """Look up the connector instance and run an incremental sync."""
        from knowledge.connectors.registry import ConnectorRegistry

        connector = ConnectorRegistry.get(connector_id)
        if connector is None:
            logger.warning("Scheduled sync: connector %s not in registry - skipping", connector_id)
            return

        logger.info("Scheduler triggering sync for connector %s", connector_id)
        started_at = time.monotonic()
        try:
            result = await connector.sync(incremental=True)
            logger.info(
                "Scheduled sync complete: connector=%s status=%s added=%d updated=%d deleted=%d errors=%d",
                connector_id,
                result.status,
                result.added,
                result.updated,
                result.deleted,
                len(result.errors),
            )
        except Exception as exc:
            elapsed = time.monotonic() - started_at
            logger.error("Scheduled sync failed: connector=%s elapsed=%.1fs error=%s", connector_id, elapsed, exc)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_scheduler: ConnectorScheduler | None = None


def get_connector_scheduler() -> ConnectorScheduler:
    """Return the module-level ConnectorScheduler singleton."""
    global _scheduler
    if _scheduler is None:
        _scheduler = ConnectorScheduler()
    return _scheduler
