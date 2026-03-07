# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Approval Gate Service (#1402)

Manages the full approval lifecycle: create, approve, reject,
request revision, resubmit, and comment. Publishes WebSocket
notifications for pending approvals.
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Dict, List, Optional

from models.approval import Approval, ApprovalComment, ApprovalStatus, TaskApprovalLink
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)

# Valid state transitions: source -> {allowed targets}
_VALID_TRANSITIONS = {
    ApprovalStatus.PENDING.value: {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
        ApprovalStatus.REVISION_REQUESTED.value,
    },
    ApprovalStatus.REVISION_REQUESTED.value: {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
    },
}


class ApprovalGateService:
    """Service for approval gate CRUD and lifecycle transitions."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # -- Create --------------------------------------------------------

    async def create_approval(
        self,
        title: str,
        approval_type: str,
        requested_by_agent: Optional[str] = None,
        description: Optional[str] = None,
        workflow_id: Optional[str] = None,
        workflow_step: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        task_ids: Optional[List[str]] = None,
    ) -> Approval:
        """Create a new approval gate request."""
        approval = Approval(
            title=title,
            description=description,
            approval_type=approval_type,
            status=ApprovalStatus.PENDING.value,
            requested_by_agent=requested_by_agent,
            workflow_id=workflow_id,
            workflow_step=workflow_step,
            context=context or {},
        )
        self.session.add(approval)
        await self.session.flush()

        if task_ids:
            for tid in task_ids:
                link = TaskApprovalLink(
                    approval_id=approval.id,
                    task_id=tid,
                )
                self.session.add(link)

        await self.session.commit()
        await self.session.refresh(approval)

        await self._notify("approval_pending", approval)
        logger.info(
            "Approval %s created: type=%s, agent=%s",
            approval.id,
            approval_type,
            requested_by_agent,
        )
        return approval

    # -- Status transitions --------------------------------------------

    async def approve(
        self,
        approval_id: uuid.UUID,
        decided_by: str,
        comment: Optional[str] = None,
    ) -> Approval:
        """Approve a pending approval gate."""
        return await self._transition(
            approval_id,
            ApprovalStatus.APPROVED,
            decided_by,
            comment,
        )

    async def reject(
        self,
        approval_id: uuid.UUID,
        decided_by: str,
        comment: Optional[str] = None,
    ) -> Approval:
        """Reject a pending approval gate."""
        return await self._transition(
            approval_id,
            ApprovalStatus.REJECTED,
            decided_by,
            comment,
        )

    async def request_revision(
        self,
        approval_id: uuid.UUID,
        decided_by: str,
        comment: Optional[str] = None,
    ) -> Approval:
        """Request revision on a pending approval gate."""
        return await self._transition(
            approval_id,
            ApprovalStatus.REVISION_REQUESTED,
            decided_by,
            comment,
        )

    async def resubmit(
        self,
        approval_id: uuid.UUID,
        description: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Approval:
        """Resubmit after revision request, reset to pending."""
        approval = await self._get_or_raise(approval_id)
        if approval.status != ApprovalStatus.REVISION_REQUESTED.value:
            raise ValueError(
                f"Cannot resubmit: status is {approval.status}, "
                "expected revision_requested"
            )

        approval.status = ApprovalStatus.PENDING.value
        approval.decided_by_user = None
        approval.decided_at = None
        if description is not None:
            approval.description = description
        if context is not None:
            approval.context = context

        await self.session.commit()
        await self.session.refresh(approval)
        await self._notify("approval_pending", approval)
        logger.info("Approval %s resubmitted", approval_id)
        return approval

    # -- Comments ------------------------------------------------------

    async def add_comment(
        self,
        approval_id: uuid.UUID,
        author: str,
        body: str,
        author_type: str = "human",
    ) -> ApprovalComment:
        """Add a comment to an approval."""
        await self._get_or_raise(approval_id)
        comment = ApprovalComment(
            approval_id=approval_id,
            author=author,
            author_type=author_type,
            body=body,
        )
        self.session.add(comment)
        await self.session.commit()
        await self.session.refresh(comment)
        return comment

    # -- Task linking --------------------------------------------------

    async def link_task(
        self,
        approval_id: uuid.UUID,
        task_id: str,
        task_type: str = "github_issue",
    ) -> TaskApprovalLink:
        """Link a task/issue to an approval."""
        await self._get_or_raise(approval_id)
        link = TaskApprovalLink(
            approval_id=approval_id,
            task_id=task_id,
            task_type=task_type,
        )
        self.session.add(link)
        await self.session.commit()
        await self.session.refresh(link)
        return link

    async def unlink_task(
        self,
        approval_id: uuid.UUID,
        task_id: str,
    ) -> bool:
        """Remove a task link from an approval."""
        stmt = select(TaskApprovalLink).where(
            TaskApprovalLink.approval_id == approval_id,
            TaskApprovalLink.task_id == task_id,
        )
        result = await self.session.execute(stmt)
        link = result.scalar_one_or_none()
        if link is None:
            return False
        await self.session.delete(link)
        await self.session.commit()
        return True

    # -- Queries -------------------------------------------------------

    async def get(self, approval_id: uuid.UUID) -> Optional[Approval]:
        """Get an approval with comments and task links loaded."""
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.comments),
                selectinload(Approval.task_links),
            )
            .where(Approval.id == approval_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_approvals(
        self,
        status: Optional[str] = None,
        approval_type: Optional[str] = None,
        workflow_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Approval]:
        """List approvals with optional filters."""
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.comments),
                selectinload(Approval.task_links),
            )
            .order_by(Approval.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            stmt = stmt.where(Approval.status == status)
        if approval_type:
            stmt = stmt.where(Approval.approval_type == approval_type)
        if workflow_id:
            stmt = stmt.where(Approval.workflow_id == workflow_id)
        if agent_id:
            stmt = stmt.where(Approval.requested_by_agent == agent_id)

        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending_for_workflow(
        self,
        workflow_id: str,
    ) -> List[Approval]:
        """Get all pending approvals for a workflow."""
        return await self.list_approvals(
            status=ApprovalStatus.PENDING.value,
            workflow_id=workflow_id,
        )

    # -- Internal helpers ----------------------------------------------

    async def _get_or_raise(
        self,
        approval_id: uuid.UUID,
    ) -> Approval:
        """Load approval with relationships or raise ValueError."""
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.comments),
                selectinload(Approval.task_links),
            )
            .where(Approval.id == approval_id)
        )
        result = await self.session.execute(stmt)
        approval = result.scalar_one_or_none()
        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")
        return approval

    async def _transition(
        self,
        approval_id: uuid.UUID,
        new_status: ApprovalStatus,
        decided_by: str,
        comment: Optional[str],
    ) -> Approval:
        """Perform a status transition with validation."""
        approval = await self._get_or_raise(approval_id)

        allowed = _VALID_TRANSITIONS.get(approval.status, set())
        if new_status.value not in allowed:
            raise ValueError(
                f"Cannot transition from {approval.status} " f"to {new_status.value}"
            )

        approval.status = new_status.value
        approval.decided_by_user = decided_by
        approval.decided_at = datetime.now(UTC)

        if comment:
            c = ApprovalComment(
                approval_id=approval_id,
                author=decided_by,
                author_type="human",
                body=comment,
            )
            self.session.add(c)

        await self.session.commit()
        await self.session.refresh(approval)

        event = f"approval_{new_status.value}"
        await self._notify(event, approval)
        logger.info(
            "Approval %s -> %s by %s",
            approval_id,
            new_status.value,
            decided_by,
        )
        return approval

    async def _notify(
        self,
        event_type: str,
        approval: Approval,
    ) -> None:
        """Publish WebSocket notification via event_manager."""
        try:
            from event_manager import event_manager

            await event_manager.publish(
                event_type=event_type,
                payload={
                    "approval_id": str(approval.id),
                    "title": approval.title,
                    "approval_type": approval.approval_type,
                    "status": approval.status,
                    "requested_by_agent": approval.requested_by_agent,
                    "decided_by_user": approval.decided_by_user,
                    "workflow_id": approval.workflow_id,
                    "workflow_step": approval.workflow_step,
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to publish %s notification: %s",
                event_type,
                exc,
            )
