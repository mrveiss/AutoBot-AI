# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC HeartbeatScheduler — fires routines via Redis sorted set (GH#8229).

Architecture:
  - sorted set key: ``llc:heartbeat:schedule``
  - member format:  ``routine:<uuid>``
  - score:          Unix timestamp (float) of next fire time

Startup loads all ACTIVE routines and inserts them (nx=True — never overwrites
an existing scheduled time so concurrent workers don't race).  The polling loop
uses ZRANGEBYSCORE ... LIMIT 1 to claim one item per tick, dispatches it via
RoutineService.record_run(), then re-inserts the member with the next fire time.

Croniter is required (``pip install croniter``).  If the library is missing the
scheduler logs a warning and skips routine scheduling gracefully.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from autobot_shared.redis_client import get_async_redis_client

logger = logging.getLogger(__name__)

_SCHEDULE_KEY = "llc:heartbeat:schedule"
_POLL_INTERVAL = 5.0  # seconds between sorted-set polls


class HeartbeatScheduler:
    """Polls the sorted set and dispatches due routines."""

    def __init__(self, poll_interval: float = _POLL_INTERVAL) -> None:
        self._poll_interval = poll_interval
        self._running = False

    # ------------------------------------------------------------------
    # Startup / shutdown
    # ------------------------------------------------------------------

    async def startup(self, session: object) -> None:
        """Load agents (stub) and routines into the schedule on service start."""
        await self._load_routines(session)
        self._running = True
        asyncio.ensure_future(self._poll_loop(session))

    async def shutdown(self) -> None:
        self._running = False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_routines(self, session: object) -> None:
        """Load ACTIVE routines into ``llc:heartbeat:schedule`` (nx=True)."""
        try:
            from croniter import croniter
        except ImportError:
            logger.warning("croniter not installed — routine scheduling disabled")
            return

        try:
            from ..models.enums import RoutineStatus
            from ..services.routine_service import RoutineService

            svc = RoutineService()
            routines = await svc.list(session, company_id=None, status=RoutineStatus.ACTIVE)  # type: ignore[arg-type]
        except Exception as exc:
            logger.warning("Failed to load routines for scheduling: %s", exc)
            return

        redis = await get_async_redis_client()
        if redis is None:
            logger.warning("Redis unavailable — skipping routine schedule load")
            return

        now = datetime.now(tz=timezone.utc)
        for routine in routines:
            try:
                next_ts: float = croniter(routine.cron_schedule, now).get_next(float)
                await redis.zadd(
                    _SCHEDULE_KEY,
                    {f"routine:{routine.id}": next_ts},
                    nx=True,
                )
            except Exception as exc:
                logger.warning("Failed to schedule routine %s: %s", routine.id, exc)

    async def _poll_loop(self, session: object) -> None:
        """Continuously poll for due items and dispatch them."""
        while self._running:
            try:
                await self._process_due(session)
            except Exception as exc:
                logger.error("HeartbeatScheduler poll error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _process_due(self, session: object) -> None:
        """Pop and dispatch all members whose score ≤ now."""
        redis = await get_async_redis_client()
        if redis is None:
            return

        now_ts = time.time()
        due_items = await redis.zrangebyscore(_SCHEDULE_KEY, "-inf", now_ts, withscores=False)

        for member in due_items:
            member_str = member.decode() if isinstance(member, bytes) else member
            # Remove from schedule before dispatch to avoid double-fire
            removed = await redis.zrem(_SCHEDULE_KEY, member_str)
            if not removed:
                continue  # another worker already claimed it

            if member_str.startswith("routine:"):
                routine_id_str = member_str[len("routine:"):]
                await self._dispatch_routine(session, routine_id_str)

    async def _dispatch_routine(self, session: object, routine_id_str: str) -> None:
        """Record a run and re-queue the routine at its next fire time."""
        try:
            from croniter import croniter
        except ImportError:
            return

        try:
            import uuid

            from ..services.routine_service import RoutineService

            svc = RoutineService()
            routine_id = uuid.UUID(routine_id_str)
            routine = await svc.get(session, routine_id)  # type: ignore[arg-type]
            await svc.record_run(session, routine_id, status="queued")  # type: ignore[arg-type]

            # Re-insert next fire time
            redis = await get_async_redis_client()
            if redis is not None:
                next_ts: float = croniter(
                    routine.cron_schedule, datetime.now(tz=timezone.utc)
                ).get_next(float)
                await redis.zadd(_SCHEDULE_KEY, {f"routine:{routine_id}": next_ts})

        except Exception as exc:
            logger.error("Failed to dispatch routine %s: %s", routine_id_str, exc)
