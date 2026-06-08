# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC RoutineScheduler — fires routines via Redis sorted set (GH#8229).

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

Session handling: each dispatch opens a fresh AsyncSession via
get_async_session_factory() to avoid idle_in_transaction_session_timeout.
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


class RoutineScheduler:
    """Polls the sorted set and dispatches due routines."""

    def __init__(self, poll_interval: float = _POLL_INTERVAL) -> None:
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Startup / shutdown
    # ------------------------------------------------------------------

    async def startup(self) -> None:
        """Load routines into the schedule and start the polling loop."""
        await self._load_routines()
        self._running = True
        self._task = asyncio.ensure_future(self._poll_loop())

    async def shutdown(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_routines(self) -> None:
        """Load ACTIVE routines into ``llc:heartbeat:schedule`` (nx=True)."""
        try:
            from croniter import croniter
        except ImportError:
            logger.warning("croniter not installed — routine scheduling disabled")
            return

        try:
            from user_management.database import get_async_session_factory

            from ..models.enums import RoutineStatus
            from ..services.routine_service import RoutineService

            svc = RoutineService()
            factory = get_async_session_factory()
            async with factory() as session:
                routines = await svc.list(session, status=RoutineStatus.ACTIVE, limit=10000)
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

    async def _poll_loop(self) -> None:
        """Continuously poll for due items and dispatch them."""
        while self._running:
            try:
                await self._process_due()
            except Exception as exc:
                logger.error("RoutineScheduler poll error: %s", exc)
            await asyncio.sleep(self._poll_interval)

    async def _process_due(self) -> None:
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
                routine_id_str = member_str[len("routine:") :]
                await self._dispatch_routine(routine_id_str)

    async def _company_or_agent_paused(self, company_id: str, agent_id: Optional[str]) -> bool:
        """Return True if a FR-GOV-05 pause flag is active for company or agent."""
        redis = await get_async_redis_client()
        if redis is None:
            return False
        if await redis.exists(f"llc:company:{company_id}:paused"):
            return True
        if agent_id and await redis.exists(f"llc:agent:{agent_id}:paused"):
            return True
        return False

    async def _dispatch_routine(self, routine_id_str: str) -> None:
        """Record a run and re-queue the routine at its next fire time."""
        try:
            from croniter import croniter
        except ImportError:
            return

        try:
            import uuid

            from user_management.database import get_async_session_factory

            from ..models.enums import RoutineStatus
            from ..services.routine_service import RoutineService

            svc = RoutineService()
            routine_id = uuid.UUID(routine_id_str)
            factory = get_async_session_factory()
            cron_schedule: Optional[str] = None

            async with factory() as session:
                routine = await svc.get(session, routine_id)
                if routine is None or routine.status != RoutineStatus.ACTIVE:
                    return  # Archived or paused — don't re-queue

                # FR-GOV-05: skip if company or assignee agent is paused/terminated
                company_id = str(routine.company_id) if hasattr(routine, "company_id") and routine.company_id else ""
                agent_id = str(routine.assignee_agent_id) if routine.assignee_agent_id else None
                if company_id and await self._company_or_agent_paused(company_id, agent_id):
                    logger.info(
                        "RoutineScheduler: skipping %s — company or agent is paused (FR-GOV-05)",
                        routine_id_str,
                    )
                    # Re-queue at next fire time so the routine resumes automatically when unpaused
                    next_ts_skip: float = croniter(routine.cron_schedule, datetime.now(tz=timezone.utc)).get_next(float)
                    redis = await get_async_redis_client()
                    if redis is None:
                        raise RuntimeError(f"Redis unavailable — cannot re-queue paused routine {routine_id_str}")
                    await redis.zadd(_SCHEDULE_KEY, {f"routine:{routine_id}": next_ts_skip})
                    return

                cron_schedule = routine.cron_schedule
                routine.last_fired_at = datetime.now(tz=timezone.utc)
                await svc.record_run(session, routine_id, status="queued")
                await session.commit()

            # Re-insert next fire time (outside session — session already committed)
            redis = await get_async_redis_client()
            if redis is not None and cron_schedule is not None:
                next_ts: float = croniter(cron_schedule, datetime.now(tz=timezone.utc)).get_next(float)
                await redis.zadd(_SCHEDULE_KEY, {f"routine:{routine_id}": next_ts})

        except Exception as exc:
            logger.error("Failed to dispatch routine %s: %s", routine_id_str, exc)
            # Re-add with a short retry delay so the routine isn't permanently lost
            try:
                redis = await get_async_redis_client()
                if redis is not None:
                    await redis.zadd(
                        _SCHEDULE_KEY,
                        {f"routine:{routine_id_str}": time.time() + 60},
                        nx=True,
                    )
            except Exception:
                pass

    async def on_run_complete(
        self,
        run_id: str,
        agent_id: str,
        status: str,
        work_item_id: Optional[str] = None,
        context_snapshot: Optional[dict] = None,
    ) -> None:
        """Post-heartbeat hook — write diary entry to KB when a run terminates.

        Called by the adapter layer (or test harness) after a heartbeat run
        reaches ``succeeded`` or ``failed``.  Delegates to
        ``AgentDiaryKbWriter`` which is best-effort and will not propagate
        exceptions.

        Args:
            run_id: Heartbeat run identifier.
            agent_id: Agent that completed the run.
            status: Terminal status string (``"succeeded"`` or ``"failed"``).
            work_item_id: Optional work item checked out during the run.
            context_snapshot: JSONB context snapshot from ``LLCHeartbeatRun``.
        """
        if status not in ("succeeded", "failed", "completed"):
            return

        # Fetch company_id from work_item if available, for write guard (GH#8598).
        company_id: Optional[str] = None
        session = None
        if work_item_id:
            try:
                import uuid

                from database.get_session import get_async_session_factory
                from sqlalchemy import select

                from ..models.work_item import LLCWorkItem

                factory = get_async_session_factory()
                session = factory()
                result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)))
                work_item = result.scalar_one_or_none()
                if work_item:
                    company_id = str(work_item.company_id)
            except Exception:
                logger.debug(
                    "RoutineScheduler: failed to fetch company_id for work_item %s",
                    work_item_id,
                    exc_info=True,
                )

        try:
            from ..kb.diary_writer import AgentDiaryKbWriter

            writer = AgentDiaryKbWriter()
            await writer.write_from_run(
                run_id=run_id,
                agent_id=agent_id,
                status=status,
                work_item_id=work_item_id,
                context_snapshot=context_snapshot,
                company_id=company_id,
                session=session,
            )
        except Exception:
            logger.warning(
                "RoutineScheduler.on_run_complete: diary write failed for run_id=%s",
                run_id,
                exc_info=True,
            )
        finally:
            if session:
                await session.close()
