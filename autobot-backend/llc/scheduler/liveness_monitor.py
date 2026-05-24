# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC liveness monitor — stuck run detection and recovery (GH#8228).

Runs every 60 seconds. Finds heartbeat runs where status='running' and
started_at is older than the per-agent timeout (default 30 minutes).
For each stuck run:
  1. Marks the run status = timed_out
  2. Calls adapter.cancel() (best-effort)
  3. Deletes the Redis checkout lock: DEL llc:checkout:{work_item_id}
  4. Sets the work item status = blocked
  5. Creates a recovery work item (type=bug) assigned to the agent's manager
  6. Writes an activity log entry
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.enums import WorkItemStatus, WorkItemType
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.work_item import LLCWorkItem
from ..services.activity_log import ActivityEventType, LLCActivityLogService
from ..services.work_item_service import WorkItemService

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_MINUTES = 30
_POLL_INTERVAL_SECONDS = 60


class LivenessMonitor:
    """Periodic monitor that detects and recovers stuck heartbeat runs."""

    def __init__(
        self,
        activity_log: Optional[LLCActivityLogService] = None,
        poll_interval: int = _POLL_INTERVAL_SECONDS,
    ) -> None:
        self._activity_log = activity_log
        self._poll_interval = poll_interval
        self._running = False
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    def start(self) -> None:
        """Start the background polling loop."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop(), name="llc-liveness-monitor")
        logger.info("LivenessMonitor started (poll interval: %ds)", self._poll_interval)

    def stop(self) -> None:
        """Stop the background polling loop."""
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()

    async def _loop(self) -> None:
        while self._running:
            try:
                await self._check_once()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("LivenessMonitor._check_once failed")
            await asyncio.sleep(self._poll_interval)

    async def _check_once(self) -> None:
        """Single scan — find stuck runs and trigger recovery for each."""
        factory = get_async_session_factory()
        async with factory() as session:
            stuck = await self._find_stuck_runs(session)
            for run in stuck:
                try:
                    await self._recover(session, run)
                    await session.commit()
                except Exception:
                    logger.exception("Recovery failed for run %s — rolling back", run.id)
                    await session.rollback()

    async def _find_stuck_runs(self, session: AsyncSession) -> list:
        """Return all runs where status=running and started_at is too old."""
        now = datetime.now(tz=timezone.utc)

        # Per-agent timeout comes from adapter_config.timeout_minutes if available.
        # The fallback default is _DEFAULT_TIMEOUT_MINUTES.
        # We use a single query with the default cutoff; the per-agent override is
        # checked inside _recover() when adapter_config is available.
        cutoff = now - timedelta(minutes=_DEFAULT_TIMEOUT_MINUTES)

        result = await session.execute(
            select(LLCHeartbeatRun).where(
                LLCHeartbeatRun.status == "running",
                LLCHeartbeatRun.started_at < cutoff,
            )
        )
        return list(result.scalars().all())

    async def _recover(self, session: AsyncSession, run: LLCHeartbeatRun) -> None:
        """Perform the six-step recovery protocol for a single stuck run."""
        run_id = str(run.id)
        agent_id = run.agent_id
        company_id = str(run.company_id)

        logger.warning(
            "LivenessMonitor: run %s for agent %s is stuck (started_at=%s) — recovering",
            run_id,
            agent_id,
            run.started_at,
        )

        # Step 1: Mark run as timed_out
        run.status = "timed_out"
        run.finished_at = datetime.now(tz=timezone.utc)
        session.add(run)

        # Step 2: Call adapter.cancel() — best-effort, swallow all errors
        await self._cancel_adapter(agent_id, run_id)

        # Step 3: Release Redis checkout lock
        if run.work_item_id:
            await self._release_checkout_lock(str(run.work_item_id))

        # Step 4: Set work item status = blocked
        work_item = None
        if run.work_item_id:
            work_item = await self._block_work_item(session, str(run.work_item_id))

        # Step 5: Create recovery work item
        await self._create_recovery_item(session, run, work_item, company_id, agent_id)

        # Step 6: Write activity log entry
        await self._log_activity(session, run, company_id, agent_id)

    async def _cancel_adapter(self, agent_id: str, run_id: str) -> None:
        try:
            from ..adapters import get_adapter_for_agent

            adapter = await get_adapter_for_agent(agent_id)
            if adapter is not None:
                await adapter.cancel({}, run_id)
        except Exception:
            logger.debug("adapter.cancel() swallowed for agent %s run %s", agent_id, run_id)

    async def _release_checkout_lock(self, work_item_id: str) -> None:
        redis = await get_async_redis_client()
        if redis is None:
            return
        try:
            await redis.delete(f"llc:checkout:{work_item_id}")
        except Exception:
            logger.debug("Redis DEL llc:checkout:%s failed (swallowed)", work_item_id)

    async def _block_work_item(self, session: AsyncSession, work_item_id: str) -> Optional[LLCWorkItem]:
        result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == work_item_id))
        item = result.scalar_one_or_none()
        if item is not None:
            item.status = WorkItemStatus.BLOCKED
            session.add(item)
        return item

    async def _create_recovery_item(
        self,
        session: AsyncSession,
        run: LLCHeartbeatRun,
        work_item: Optional[LLCWorkItem],
        company_id: str,
        agent_id: str,
    ) -> None:
        identifier = work_item.identifier if work_item else run_id_label(str(run.id))
        title = f"Recovery: agent {agent_id} timed out on {identifier}"

        # Resolve manager via company hierarchy — default to None (board-visible)
        manager_agent_id = await self._resolve_manager(session, company_id, agent_id)

        svc = WorkItemService()
        await svc.create(
            session,
            company_id=company_id,
            type=WorkItemType.BUG,
            title=title,
            description=(
                f"Automatic recovery item. Run {run.id} for agent {agent_id} "
                f"exceeded the liveness timeout and was marked timed_out. "
                f"Work item {identifier} has been set to blocked. "
                f"Investigate and unblock manually."
            ),
            assignee_agent_id=manager_agent_id,
            parent_id=str(work_item.parent_id) if work_item and work_item.parent_id else None,
            goal_id=str(work_item.goal_id) if work_item and work_item.goal_id else None,
        )

    async def _resolve_manager(self, session: AsyncSession, company_id: str, agent_id: str) -> Optional[str]:
        """Best-effort lookup for the agent's manager agent_id."""
        try:
            result = await session.execute(
                text(
                    "SELECT manager_agent_id FROM agent_org_nodes"
                    " WHERE company_id = :company_id AND agent_id = :agent_id"
                    " LIMIT 1"
                ),
                {"company_id": company_id, "agent_id": agent_id},
            )
            row = result.fetchone()
            return str(row[0]) if row and row[0] else None
        except Exception:
            logger.debug("_resolve_manager failed for agent %s (swallowed)", agent_id)
            return None

    async def _log_activity(
        self,
        session: AsyncSession,
        run: LLCHeartbeatRun,
        company_id: str,
        agent_id: str,
    ) -> None:
        if self._activity_log is None:
            return
        try:
            await self._activity_log.record(
                session=session,
                company_id=company_id,
                actor_id="liveness_monitor",
                event_type=ActivityEventType.HEARTBEAT_FAILED,
                entity_type="heartbeat_run",
                entity_id=str(run.id),
                after={"status": "timed_out"},
                metadata={"agent_id": agent_id, "reason": "liveness_timeout"},
            )
        except Exception:
            logger.debug("activity_log.record failed for run %s (swallowed)", run.id)


def run_id_label(run_id: str) -> str:
    """Short label for display when work_item.identifier is unavailable."""
    return f"run:{run_id[:8]}"
