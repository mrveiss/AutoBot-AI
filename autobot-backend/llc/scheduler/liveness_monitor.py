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
  3. Releases every checkout the run made (keyed on checkout_run_id; its Redis fence is dropped
     once the transaction commits), one activity entry per item. An item still in progress is set to
     blocked by that same release (its activity entry records the status change); an item in any
     other status keeps its status
  4. (done by step 3: there is one release rule, parameterised only by where an unfinished item goes)
  5. Creates ONE recovery work item (type=bug) assigned to the agent's manager, naming every released item
  6. Writes an activity log entry (first of all, in fact: see ``_recover``)

Each run recovers inside its own SAVEPOINT. A failure, the audit write included, undoes that
run alone and is logged; the other runs in the scan, and the transaction they share, are untouched.
"""

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session_factory

from ..models.activity import ActorType
from ..models.enums import ActivityEventType, WorkItemStatus, WorkItemType
from ..models.heartbeat_run import LLCHeartbeatRun
from ..models.sprint import LLCProject
from ..models.work_item import LLCWorkItem
from ..services.accessors import get_work_item_service
from ..services.activity_log import LLCActivityLogService
from ..services.actor import audit
from ..services.run_checkouts import ReleasedCheckout, ReleaseWhy, drop_released_fences, release_checkouts_for_run
from ..services.work_item_hierarchy import HierarchyViolation, parent_if_allowed
from .base import PollLoopScheduler
from .dispatch_gate import agent_ref_block_reason

logger = get_logger(__name__)

_DEFAULT_TIMEOUT_MINUTES = 30

#: The ``reason`` on the run's activity entry and on each checkout released because the run timed out.
LIVENESS_REASON = "liveness_timeout"

#: Unlike a cancel or a stall, a run that timed out needs a person to look at what it was doing, so the monitor
#: parks the unfinished items it releases as BLOCKED, visible and recoverable, instead of offering them again.
_PARKED_AS = WorkItemStatus.BLOCKED


def _liveness_release(log: LLCActivityLogService) -> ReleaseWhy:
    """Why the monitor releases a stuck run's checkouts: the system, on a liveness timeout."""
    return ReleaseWhy(reason=LIVENESS_REASON, source="liveness_monitor", log=log, then=_PARKED_AS)


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
        self._activity_log = activity_log or LLCActivityLogService()

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
                run_id = run.id  # read while loaded: the rollback below expires the run it undoes
                try:
                    async with session.begin_nested():
                        released = await self._recover(session, run)
                except Exception:
                    logger.exception("Recovery failed for run %s — rolled back to its savepoint", run_id)
                    continue
                await session.commit()  # a failed commit fails the scan; the loop logs it and retries
                await drop_released_fences(released)  # only once the DB release is durable

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

    async def _recover(self, session: AsyncSession, run: LLCHeartbeatRun) -> list[ReleasedCheckout]:
        """Perform the six-step recovery protocol for a single stuck run.

        Returns the checkouts it released, whose Redis fences the caller drops once the transaction commits.
        """
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
            return []

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

        # Step 6, first: the audit row shares the transaction, so a failed write must fail the
        # recovery BEFORE the adapter is cancelled and the Redis fence dropped, which cannot be undone.
        await self._log_activity(session, run, company_id, agent_id)

        # Step 2: Call adapter.cancel() — best-effort, swallow all errors
        await self._cancel_adapter(agent_id, run_id)

        # Step 3: Release every checkout the run made (DB row; its Redis fence follows the commit)
        released = await release_checkouts_for_run(session, run, _liveness_release(self._activity_log))

        # Step 5: one recovery item for the run, naming every item released (step 4 is part of the release)
        work_items = [r.item for r in released]
        await self._create_recovery_item(
            session, run, work_items[0] if work_items else None, company_id, agent_id, released_items=work_items
        )
        return released

    async def _cancel_adapter(self, agent_id: str, run_id: str) -> None:
        try:
            from ..adapters import get_adapter_for_agent

            adapter = await get_adapter_for_agent(agent_id)
            if adapter is not None:
                await adapter.cancel({}, run_id)
        except Exception:
            logger.debug("adapter.cancel() swallowed for agent %s run %s", agent_id, run_id)

    async def _create_recovery_item(
        self,
        session: AsyncSession,
        run: LLCHeartbeatRun,
        work_item: Optional[LLCWorkItem],
        company_id: str,
        agent_id: str,
        released_items: Sequence[LLCWorkItem] = (),
    ) -> None:
        identifier = work_item.identifier if work_item else run_id_label(str(run.id))
        title = f"Recovery: agent {agent_id} timed out on {identifier}"
        description = (
            f"Automatic recovery item. Run {run.id} for agent {agent_id} "
            f"exceeded the liveness timeout and was marked timed_out. "
            f"{_released_sentence(released_items or ([work_item] if work_item else []))}"
            f"Investigate and unblock manually."
        )
        svc = get_work_item_service()
        # #18978: the Bug follows the stuck item's parent only where the hierarchy rules allow it
        # (a stuck Subtask's parent is a Task) and always sits in the stuck item's project.
        project_id = await _recovery_project(session, work_item, company_id)
        parent_id = await parent_if_allowed(
            session,
            svc.get,
            company_id,
            WorkItemType.BUG,
            str(work_item.parent_id) if work_item and work_item.parent_id else None,
            project_id,
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
                project_id=project_id,
                goal_id=str(work_item.goal_id) if work_item and work_item.goal_id else None,
            )
        except HierarchyViolation as exc:
            recovery = _UnfiledRecovery(company_id, f"{title}. {description}", exc, run, agent_id)
            await _note_unfiled_recovery(session, svc, work_item, recovery, self._activity_log)

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
        await audit(
            self._activity_log,
            session,
            company_id=company_id,
            actor_type=ActorType.SYSTEM,
            actor_id=None,
            event_type=ActivityEventType.HEARTBEAT_FAILED,
            entity_type="heartbeat_run",
            entity_id=str(run.id),
            after={"status": "timed_out"},
            metadata={"agent_id": str(agent_id), "reason": LIVENESS_REASON},
        )


def _released_sentence(items: Sequence[LLCWorkItem]) -> str:
    """Every work item the run held, and the state each was left in: blocked, or unchanged if it had moved on."""
    if not items:
        return ""
    named = ", ".join(f"{i.identifier} ({WorkItemStatus(i.status).value})" for i in items)
    return f"Work items released from the run: {named}. "


async def _recovery_project(session: AsyncSession, work_item: Optional[LLCWorkItem], company_id: str) -> Optional[str]:
    """The stuck item's project, else the company's oldest (#18978); None when the company has none."""
    if work_item is not None and work_item.project_id:
        return str(work_item.project_id)
    oldest = await session.execute(
        select(LLCProject.id)
        .where(LLCProject.company_id == uuid.UUID(str(company_id)))
        .order_by(LLCProject.created_at, LLCProject.id)
        .limit(1)
    )
    found = oldest.scalar_one_or_none()
    return str(found) if found else None


@dataclass(frozen=True)
class _UnfiledRecovery:
    """What a refused recovery Bug was about: the company, the Bug's text, why it was refused, and the run/agent."""

    company_id: str
    text: str
    exc: Exception
    run: LLCHeartbeatRun
    agent_id: str


async def _note_unfiled_recovery(
    session, svc, work_item, recovery: _UnfiledRecovery, log: LLCActivityLogService
) -> None:
    """The recovery Bug was refused (a stuck item from before the every-item-has-a-project rule may have no
    project, #18978): record it on the stuck item itself so the recovery is not lost. A run with no work item has
    nowhere to comment, so the company is told instead (#20687, #20930): an activity-feed entry, which is what
    company users see, and the notification router's live event; nothing is created for it."""
    r = recovery
    logger.error("Recovery item not created (%s); noting it on the stuck work item", r.exc)
    if work_item is not None:
        await svc.add_comment(session, str(work_item.id), r.company_id, f"{r.text} ({r.exc})")
        return
    await _log_unfiled_recovery(log, session, r.company_id, r.agent_id, r.run, r.exc)
    await _notify_admins_unfiled_recovery(r.company_id, r.agent_id, r.run, r.exc)


async def _log_unfiled_recovery(
    log: LLCActivityLogService, session, company_id: str, agent_id: str, run: LLCHeartbeatRun, exc: Exception
) -> None:
    """The company activity feed's entry for an unfiled recovery: best-effort, in its own savepoint, so a failed
    write rolls back only itself and never fails the recovery it annotates. The row is a write in the caller's
    transaction (it cannot be deferred past the commit); the live publish to the company's dashboard follows the
    commit, as every activity record's does."""
    try:
        async with session.begin_nested():
            await audit(
                log,
                session,
                company_id=company_id,
                actor_type=ActorType.SYSTEM,
                actor_id=None,
                event_type=ActivityEventType.HEARTBEAT_FAILED,
                entity_type="heartbeat_run",
                entity_id=str(run.id),
                metadata={
                    "agent_id": str(agent_id),
                    "reason": "recovery_unfiled",
                    "message": f"Agent {agent_id} timed out on run {run.id}; no recovery item could be filed ({exc})",
                },
            )
    except Exception:
        logger.warning("Unfiled-recovery activity entry for run %s not written", run.id, exc_info=True)


async def _notify_admins_unfiled_recovery(company_id: str, agent_id: str, run: LLCHeartbeatRun, exc: Exception) -> None:
    """Tell the company about a timed-out run whose recovery could not be filed: ``heartbeat_missed``
    (reason ``recovery_unfiled``) on the router's ``llc:agent:*`` channel, naming the agent and the run.

    The router addresses a company only, so this notice is company-wide, not admin-only, until #20885 adds
    role addressing; the event carries no user ids."""
    redis = await get_async_redis_client()
    if redis is None:
        logger.warning("Redis unavailable; company %s not told of the unfiled recovery", company_id)
        return
    event = {
        "company_id": str(company_id),
        "event_type": "heartbeat_missed",
        "entity_type": "heartbeat_run",
        "entity_id": str(run.id),
        "payload": {
            "agent_id": str(agent_id),
            "run_id": str(run.id),
            "reason": "recovery_unfiled",
            "message": f"Agent {agent_id} timed out on run {run.id}; no recovery item could be filed ({exc})",
        },
    }
    try:
        await redis.publish(f"llc:agent:{agent_id}", json.dumps(event))
    except Exception as err:
        logger.warning("Failed to notify company %s of the unfiled recovery: %s", company_id, err)


def run_id_label(run_id: str) -> str:
    """Short label for display when work_item.identifier is unavailable."""
    return f"run:{run_id[:8]}"
