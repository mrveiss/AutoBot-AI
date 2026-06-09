# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sprint auto-close service (GH#8224).

Provides ``SprintAutoCloseService`` which:
  1. ``check_and_queue`` — finds expired active sprints, creates SPRINT_CLOSE
     approval requests for each (idempotent: skips sprints with pending approval).
  2. ``execute_close`` — called after board approves; closes sprint, computes
     actual_points, calls KB stub, rolls over incomplete items.

Rollover behaviour (GH#8224 configurable):
  - auto_rollover=true (default): incomplete items stay in next sprint backlog
    (sprint_id=null, backlog_position=0).
  - auto_rollover=false (manual_triage): items go to backlog with needs_triage=true.
"""

import logging
import uuid
from datetime import date, datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..kb.sprint_summarizer import SprintKbSummarizer
from ..models.enums import ActivityEventType, ApprovalStatus, ApprovalType, SprintStatus, WorkItemStatus
from ..models.sprint import LLCSprint
from ..models.work_item import LLCWorkItem
from ..services.approval import ApprovalService
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_INCOMPLETE_STATUSES = frozenset(
    [
        WorkItemStatus.BACKLOG.value,
        WorkItemStatus.READY.value,
        WorkItemStatus.IN_PROGRESS.value,
        WorkItemStatus.BLOCKED.value,
    ]
)

_SYSTEM_AGENT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


class SprintAutoCloseService(LLCServiceBase):
    """Manages sprint lifecycle from expiry detection through board-approved close."""

    def __init__(
        self,
        approval_service: Optional[ApprovalService] = None,
        summarizer: Optional[SprintKbSummarizer] = None,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)  # type: ignore[arg-type]
        self._approval = approval_service or ApprovalService(activity_log=self.activity_log)
        self._summarizer = summarizer or SprintKbSummarizer()

    # ------------------------------------------------------------------
    # Phase 1 — detect expired sprints and queue approval
    # ------------------------------------------------------------------

    async def check_and_queue(
        self,
        session: AsyncSession,
        *,
        today: Optional[date] = None,
    ) -> List[LLCSprint]:
        """Find expired active sprints and create SPRINT_CLOSE approval requests.

        Idempotent: sprints with a pending_close_approval_id already set are
        skipped to avoid duplicate approval records.

        Args:
            session: Async SQLAlchemy session.
            today: Override for today's date (for testing). Defaults to UTC today.

        Returns:
            List of LLCSprint rows for which a new approval was just created.
        """
        today = today or datetime.now(timezone.utc).date()

        stmt = (
            select(LLCSprint)
            .where(
                LLCSprint.status == SprintStatus.ACTIVE.value,
                LLCSprint.end_date < today,
                LLCSprint.pending_close_approval_id.is_(None),
            )
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        sprints: List[LLCSprint] = list(result.scalars().all())

        queued: List[LLCSprint] = []
        for sprint in sprints:
            approval = await self._approval.request_approval(
                session,
                company_id=sprint.company_id,
                gate_type=ApprovalType.SPRINT_CLOSE,
                payload={
                    "sprint_id": str(sprint.id),
                    "sprint_name": sprint.name,
                    "end_date": str(sprint.end_date),
                    "project_id": str(sprint.project_id),
                },
                requested_by=_SYSTEM_AGENT_ID,
            )
            sprint.pending_close_approval_id = approval.id
            await session.flush()

            if self.activity_log:
                await self.activity_log.log(
                    session,
                    event_type=ActivityEventType.APPROVAL_REQUESTED,
                    entity_type="sprint",
                    entity_id=str(sprint.id),
                    company_id=str(sprint.company_id),
                    after_state={"sprint_id": str(sprint.id), "approval_id": str(approval.id)},
                )

            queued.append(sprint)
            logger.info(
                "Sprint close approval queued: sprint_id=%s approval_id=%s",
                sprint.id,
                approval.id,
            )

        return queued

    async def publish_queued(self, sprints: List[LLCSprint]) -> None:
        """Publish SPRINT_CLOSE approval events after commit — call post-transaction."""
        for sprint in sprints:
            if sprint.pending_close_approval_id is not None:
                await self._approval._publish(
                    "llc:approvals:{company_id}".format(company_id=sprint.company_id),
                    {
                        "event": "sprint_close_requested",
                        "sprint_id": str(sprint.id),
                        "approval_id": str(sprint.pending_close_approval_id),
                        "company_id": str(sprint.company_id),
                    },
                )

    # ------------------------------------------------------------------
    # Phase 2 — execute close after board approval
    # ------------------------------------------------------------------

    async def execute_close(
        self,
        session: AsyncSession,
        *,
        sprint_id: uuid.UUID,
        approval_id: uuid.UUID,
        decided_by: uuid.UUID,
    ) -> LLCSprint:
        """Close a sprint after its SPRINT_CLOSE approval is granted.

        Steps:
          1. Validate approval is APPROVED for this sprint.
          2. Compute actual_points from DONE work items.
          3. Set sprint status → CLOSED.
          4. Summarize into KB (stub; real impl in Phase 5).
          5. Roll over incomplete items.
          6. Write activity log entry.

        Args:
            session: Async SQLAlchemy session.
            sprint_id: Sprint to close.
            approval_id: ID of the APPROVED LLCApproval row.
            decided_by: Agent that granted approval.

        Returns:
            Updated LLCSprint row.

        Raises:
            ValueError: Sprint not found, wrong status, or approval mismatch.
        """
        # -- Fetch and validate sprint --
        result = await session.execute(select(LLCSprint).where(LLCSprint.id == sprint_id).with_for_update())
        sprint = result.scalar_one_or_none()
        if sprint is None:
            raise ValueError(f"Sprint {sprint_id} not found")
        if sprint.status not in (SprintStatus.ACTIVE.value, SprintStatus.REVIEW.value):
            raise ValueError(f"Sprint {sprint_id} has status {sprint.status!r}; expected active or review")
        if sprint.pending_close_approval_id != approval_id:
            raise ValueError(
                f"Sprint {sprint_id} pending approval is " f"{sprint.pending_close_approval_id!r}, got {approval_id!r}"
            )

        # -- Validate the approval itself is APPROVED (GH#8473) --
        from ..models.approval import LLCApproval as _LLCApproval

        approval_row = await session.execute(select(_LLCApproval).where(_LLCApproval.id == approval_id))
        approval_obj = approval_row.scalar_one_or_none()
        if approval_obj is None:
            raise ValueError(f"Approval {approval_id} not found")
        if approval_obj.status != ApprovalStatus.APPROVED.value:
            raise ValueError(f"Approval {approval_id} has status {approval_obj.status!r}; expected approved")

        # -- Compute actual_points from DONE items --
        points_result = await session.execute(
            select(func.coalesce(func.sum(LLCWorkItem.story_points), 0)).where(
                LLCWorkItem.sprint_id == sprint_id,
                LLCWorkItem.status == WorkItemStatus.DONE.value,
            )
        )
        actual_points: int = int(points_result.scalar_one())

        # -- Close the sprint --
        before_state = {"status": sprint.status, "actual_points": sprint.actual_points}
        sprint.status = SprintStatus.CLOSED.value
        sprint.actual_points = actual_points
        sprint.pending_close_approval_id = None
        await session.flush()

        # -- KB summarization (GH#8238) --
        kb_summary = await self._summarizer.summarize_and_merge(sprint_id, session=session)

        # -- Roll over incomplete items --
        auto_rollover = await self._resolve_auto_rollover(session, sprint)
        rolled_count = await self._rollover_items(session, sprint_id=sprint_id, auto_rollover=auto_rollover)

        # -- Activity log --
        if self.activity_log:
            await self.activity_log.log(
                session,
                event_type=ActivityEventType.SPRINT_COMPLETED,
                entity_type="sprint",
                entity_id=str(sprint.id),
                company_id=str(sprint.company_id),
                before_state=before_state,
                after_state={
                    "status": SprintStatus.CLOSED.value,
                    "actual_points": actual_points,
                    "rolled_over_items": rolled_count,
                    "decided_by": str(decided_by),
                    "kb_summary_generated": bool(kb_summary),
                },
            )

        logger.info(
            "Sprint closed: sprint_id=%s actual_points=%d rolled_over=%d",
            sprint_id,
            actual_points,
            rolled_count,
        )
        return sprint

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _resolve_auto_rollover(self, session: AsyncSession, sprint: LLCSprint) -> bool:
        """Determine rollover mode: project override > company default (true)."""
        from ..models.sprint import LLCProject

        result = await session.execute(select(LLCProject.auto_rollover).where(LLCProject.id == sprint.project_id))
        project_override: Optional[bool] = result.scalar_one_or_none()
        if project_override is not None:
            return project_override
        return True  # company default: auto-rollover

    async def _rollover_items(
        self,
        session: AsyncSession,
        *,
        sprint_id: uuid.UUID,
        auto_rollover: bool,
    ) -> int:
        """Move incomplete items out of the sprint.

        auto_rollover=True: sprint_id → null, backlog_position=0.
        auto_rollover=False: sprint_id → null, needs_triage=True.

        Returns the count of rolled-over rows.
        """
        count_result = await session.execute(
            select(func.count(LLCWorkItem.id)).where(
                LLCWorkItem.sprint_id == sprint_id,
                LLCWorkItem.status.in_(list(_INCOMPLETE_STATUSES)),
            )
        )
        rolled_count = int(count_result.scalar_one())

        if rolled_count == 0:
            return 0

        if auto_rollover:
            await session.execute(
                update(LLCWorkItem)
                .where(
                    LLCWorkItem.sprint_id == sprint_id,
                    LLCWorkItem.status.in_(list(_INCOMPLETE_STATUSES)),
                )
                .values(sprint_id=None, backlog_position=0)
            )
        else:
            await session.execute(
                update(LLCWorkItem)
                .where(
                    LLCWorkItem.sprint_id == sprint_id,
                    LLCWorkItem.status.in_(list(_INCOMPLETE_STATUSES)),
                )
                .values(sprint_id=None, needs_triage=True)
            )

        return rolled_count


__all__ = ["SprintAutoCloseService"]
