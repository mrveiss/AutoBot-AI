# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC liveness monitor — stuck run detection and recovery (GH#8228).

Runs every 60 seconds. Finds heartbeat runs where status='running' and
started_at is older than the per-agent timeout (default 30 minutes).
For each stuck run:
  1. Marks the run status = timed_out
  2. Calls adapter.cancel() (best-effort)
  3. Deletes the Redis checkout lock llc:checkout:{work_item_id} while it names the agent
  4. Sets the work item status = blocked
  5. Creates a recovery work item (type=bug) assigned to the agent's manager
  6. Writes an activity log entry
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from autobot_shared.redis_utils import delete_if_value
from user_management.database import get_async_session_factory

from ..models.enums import ActivityEventType, WorkItemStatus, WorkItemType
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.work_item import LLCWorkItem
from ..services.activity_log import LLCActivityLogService
from ..services.work_item_hierarchy import HierarchyViolation, parent_if_allowed
from ..services.work_item_service import WorkItemService
from .base import PollLoopScheduler
from .dispatch_gate import agent_ref_block_reason

logger = get_logger(__name__)

_DEFAULT_TIMEOUT_MINUTES = 30
_POLL_INTERVAL_SECONDS = 60


class LivenessMonitor(PollLoopScheduler):
    """Periodic monitor that detects and recovers stuck heartbeat runs."""

    _task_name = "llc-liveness-monitor"

    def __init__(
        self,
        activity_log: Optional[LLCActivityLogService] = None,
        poll_interval: int = _POLL_INTERVAL_SECONDS,
    ) -> None:
        super().__init__(poll_interval)
        self._activity_log = activity_log

    def start(self) -> None:
        """Start the background polling loop."""
        if super().start():
            logger.info("LivenessMonitor started (poll interval: %ds)", self._poll_interval)

    async def _tick(self) -> None:
        await self._check_once()

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

        # FR-GOV-05: skip recovery for deliberately paused/terminated agents
        if await agent_ref_block_reason(session, str(agent_id), company_id, deliberate_only=True):
            logger.info(
                "LivenessMonitor: skipping recovery for run %s — agent %s is deliberately paused",
                run_id,
                agent_id,
            )
            return

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
            await self._release_checkout_lock(str(run.work_item_id), str(agent_id))

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

    async def _release_checkout_lock(self, work_item_id: str, agent_id: str) -> None:
        """Drop the fence only while it still names the stuck run's agent."""
        redis = await get_async_redis_client()
        if redis is None:
            return
        try:
            await delete_if_value(redis, f"llc:checkout:{work_item_id}", agent_id)
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
        description = (
            f"Automatic recovery item. Run {run.id} for agent {agent_id} "
            f"exceeded the liveness timeout and was marked timed_out. "
            f"Work item {identifier} has been set to blocked. "
            f"Investigate and unblock manually."
        )
        svc = WorkItemService()
        # #18978: the Bug follows the stuck item's parent only where the hierarchy rules allow it
        # (a stuck Subtask's parent is a Task) and always sits in the stuck item's project.
        parent_id = await parent_if_allowed(
            session,
            svc.get,
            company_id,
            WorkItemType.BUG,
            str(work_item.parent_id) if work_item and work_item.parent_id else None,
        )
        try:
            await svc.create(
                session,
                company_id=company_id,
                type=WorkItemType.BUG,
                title=title,
                description=description,
                # Resolve manager via company hierarchy -- default to None (board-visible)
                assignee_agent_id=await self._resolve_manager(session, company_id, agent_id),
                parent_id=parent_id,
                project_id=str(work_item.project_id) if work_item and work_item.project_id else None,
                goal_id=str(work_item.goal_id) if work_item and work_item.goal_id else None,
            )
        except HierarchyViolation as exc:
            await _note_unfiled_recovery(session, svc, work_item, company_id, f"{title}. {description}", exc)

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


async def _note_unfiled_recovery(session, svc, work_item, company_id: str, text_: str, exc: Exception) -> None:
    """The recovery Bug was refused (a stuck item from before the every-item-has-a-project rule may have no
    project, #18978): record it on the stuck item itself so the recovery is not lost."""
    logger.error("Recovery item not created (%s); noting it on the stuck work item", exc)
    if work_item is not None:
        await svc.add_comment(session, str(work_item.id), company_id, f"{text_} ({exc})")


def run_id_label(run_id: str) -> str:
    """Short label for display when work_item.identifier is unavailable."""
    return f"run:{run_id[:8]}"
