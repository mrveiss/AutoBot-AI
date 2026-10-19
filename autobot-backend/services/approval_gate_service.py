# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Approval Gate Service (#1402)

Manages the full approval lifecycle: create, approve, reject,
request revision, resubmit, and comment. Publishes WebSocket
notifications for pending approvals.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List

from sqlalchemy import and_, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from autobot_shared.logging_manager import get_logger
from autobot_shared.store_authority import system_of_record
from autobot_shared.time_utils import now_utc
from models.approval import Approval, ApprovalComment, ApprovalStatus, TaskApprovalLink
from services.approval_execution import (
    resume_decided_approval,
    run_post_approval_actions,
    set_verified_decider,
)
from services.approval_record_fields import payload_hash_of, record_fields

logger = get_logger(__name__)
SYSTEM_OF_RECORD = system_of_record("approval")

# Valid state transitions: source -> {allowed targets}
_VALID_TRANSITIONS = {
    ApprovalStatus.PENDING.value: {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
        ApprovalStatus.REVISION_REQUESTED.value,
        ApprovalStatus.EXPIRED.value,
    },
    ApprovalStatus.REVISION_REQUESTED.value: {
        ApprovalStatus.APPROVED.value,
        ApprovalStatus.REJECTED.value,
    },
}


class ApprovalGateService:
    """Service for approval gate CRUD and lifecycle transitions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- Create --------------------------------------------------------

    async def create_approval(
        self,
        title: str,
        approval_type: str,
        requested_by_agent: str | None = None,
        description: str | None = None,
        workflow_id: str | None = None,
        workflow_step: str | None = None,
        context: Dict[str, Any] | None = None,
        task_ids: List[str] | None = None,
        company_id: uuid.UUID | None = None,
        *,
        source: str | None = None,
        risk_tier: Any = None,
        expires_at: datetime | None = None,
        payload_hash: str | None = None,
        resume_ref: str | None = None,
        owner_user: str | None = None,
    ) -> Approval:
        """Create a new approval gate request (company-scoped when *company_id* is given, #18430).

        The keyword-only record fields (#13421) are for server-side emitters; they are validated
        by ``record_fields`` and are deliberately not accepted from the HTTP create route.
        """
        approval = Approval(
            company_id=company_id,
            title=title,
            description=description,
            approval_type=approval_type,
            status=ApprovalStatus.PENDING.value,
            requested_by_agent=requested_by_agent,
            workflow_id=workflow_id,
            workflow_step=workflow_step,
            context=context or {},
            **record_fields(
                source=source,
                risk_tier=risk_tier,
                expires_at=expires_at,
                payload_hash=payload_hash,
                resume_ref=resume_ref,
                context=context,
                owner_user=owner_user,
            ),
        )
        self.session.add(approval)
        await self.session.flush()
        for tid in task_ids or ():
            self.session.add(TaskApprovalLink(approval_id=approval.id, task_id=tid))

        await self.session.commit()
        await self.session.refresh(approval)
        await self.session.refresh(approval, attribute_names=["comments", "task_links"])

        await self._notify("approval_pending", approval)
        logger.info("Approval %s created: type=%s, agent=%s", approval.id, approval_type, requested_by_agent)
        return approval

    # -- Status transitions --------------------------------------------

    async def approve(
        self,
        approval_id: uuid.UUID,
        decided_by: str,
        comment: str | None = None,
        *,
        author_type: str,
        decider_id: uuid.UUID | None = None,
    ) -> Approval:
        """Approve a pending approval gate, then run whatever it proposed (#17038/#17043).

        ``decider_id`` is the authenticated person's user id (#18430); handlers that care who decided compare it,
        never ``decided_by`` (a display name).

        The transition itself commits first; ``run_post_approval_actions``
        cannot fail the approval decision, only what happens after it.
        """
        approval = await self._transition(
            approval_id,
            ApprovalStatus.APPROVED,
            decided_by,
            comment,
            author_type,
        )
        set_verified_decider(approval, decider_id)
        await run_post_approval_actions(approval, self.session)
        return approval

    async def reject(
        self,
        approval_id: uuid.UUID,
        decided_by: str,
        comment: str | None = None,
        *,
        author_type: str,
    ) -> Approval:
        """Reject a pending approval gate."""
        return await self._transition(
            approval_id,
            ApprovalStatus.REJECTED,
            decided_by,
            comment,
            author_type,
        )

    async def request_revision(
        self,
        approval_id: uuid.UUID,
        decided_by: str,
        comment: str | None = None,
        *,
        author_type: str,
    ) -> Approval:
        """Request revision on a pending approval gate."""
        return await self._transition(
            approval_id,
            ApprovalStatus.REVISION_REQUESTED,
            decided_by,
            comment,
            author_type,
        )

    async def resubmit(
        self,
        approval_id: uuid.UUID,
        description: str | None = None,
        context: Dict[str, Any] | None = None,
    ) -> Approval:
        """Resubmit after revision request, reset to pending."""
        approval = await self._get_or_raise(approval_id)
        if approval.status != ApprovalStatus.REVISION_REQUESTED.value:
            raise ValueError(f"Cannot resubmit: status is {approval.status}, " "expected revision_requested")

        approval.status = ApprovalStatus.PENDING.value
        approval.decided_by_user = None
        approval.decided_at = None
        if description is not None:
            approval.description = description
        if context is not None:
            approval.context = context
            if approval.source:
                approval.payload_hash = payload_hash_of(context)

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
        *,
        author_type: str,
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
        """Remove a task link from an approval.

        Goes through ``_get_or_raise`` first, like ``link_task`` (#17043
        review): the unscoped chokepoint's whole point is that a
        company-scoped row 404s before any mutation, and this was the one
        method that queried ``TaskApprovalLink`` directly instead.
        """
        await self._get_or_raise(approval_id)
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

    async def get(self, approval_id: uuid.UUID) -> Approval | None:
        """Get an unscoped approval with comments and task links loaded.

        Never returns a company-scoped row (#17043): this service has no
        tenant context to authorize one, and its callers -- these API routes,
        ``chat_workflow`` -- never pass any. The LLC case reads/writes the
        same ``approvals`` table directly, through its own tenant-checked
        queries in ``llc/services/approval.py``, not through this class.
        """
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.comments),
                selectinload(Approval.task_links),
            )
            .where(Approval.id == approval_id, Approval.company_id.is_(None))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_approvals(
        self,
        status: str | None = None,
        approval_type: str | None = None,
        workflow_id: str | None = None,
        agent_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
        *,
        source: str | None = None,
        risk_tier: str | None = None,
        extra_where: tuple = (),
    ) -> List[Approval]:
        """List unscoped approvals with optional filters (see ``get``: never a company-scoped row)."""
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.comments),
                selectinload(Approval.task_links),
            )
            .where(Approval.company_id.is_(None))
            .order_by(Approval.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        filters = {
            Approval.status: status,
            Approval.approval_type: approval_type,
            Approval.workflow_id: workflow_id,
            Approval.requested_by_agent: agent_id,
            Approval.source: source,
            Approval.risk_tier: risk_tier,
        }
        for column, wanted in filters.items():
            if wanted:
                stmt = stmt.where(column == wanted)
        for clause in extra_where:
            stmt = stmt.where(clause)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_pending(
        self,
        *,
        viewer: str | None,
        is_admin: bool,
        source: str | None = None,
        risk_tier: str | None = None,
        limit: int,
        offset: int,
    ) -> List[Approval]:
        """Pending, unexpired, unscoped approvals the *viewer* may see -- the inbox query (#13421).

        Ownership (#18413, THREAT_MODEL s2): an admin sees all; anyone else sees the approvals
        whose ``owner_user`` is their username, plus the legacy unsourced gates that never had an
        owner. A sourced row with no owner matches nobody but an admin -- unknown is never unowned.
        A past ``expires_at`` is hidden (#18412) even before a sweeper has marked the row.
        """
        visible = [or_(Approval.expires_at.is_(None), Approval.expires_at > now_utc())]
        if not is_admin:
            legacy = and_(Approval.source.is_(None), Approval.owner_user.is_(None))
            visible.append(or_(Approval.owner_user == viewer, legacy) if viewer else legacy)
        return await self.list_approvals(
            status=ApprovalStatus.PENDING.value,
            limit=limit,
            offset=offset,
            source=source,
            risk_tier=risk_tier,
            extra_where=tuple(visible),
        )

    async def expire_stale(self) -> int:
        """Move every pending approval past ``expires_at`` to EXPIRED and resume its source (#18412).

        Each row is claimed by the same conditional UPDATE a decision uses, so a sweep racing a
        decision resumes the work exactly once. Returns the number expired.
        """
        stale = select(Approval.id).where(
            Approval.company_id.is_(None),
            Approval.status == ApprovalStatus.PENDING.value,
            Approval.expires_at.is_not(None),
            Approval.expires_at <= now_utc(),
        )
        expired = 0
        for approval_id in (await self.session.execute(stale)).scalars().all():
            if await self._expire_if_pending(approval_id) is not None:
                expired += 1
        return expired

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
        """Load an unscoped approval with relationships, or raise ValueError.

        Excludes a company-scoped row for the same reason as ``get`` above --
        this is the chokepoint every mutating method (approve/reject/
        request_revision/add_comment/link_task/unlink_task) goes through.
        """
        stmt = (
            select(Approval)
            .options(
                selectinload(Approval.comments),
                selectinload(Approval.task_links),
            )
            .where(Approval.id == approval_id, Approval.company_id.is_(None))
        )
        result = await self.session.execute(stmt)
        approval = result.scalar_one_or_none()
        if approval is None:
            raise ValueError(f"Approval {approval_id} not found")
        return approval

    async def _claim(
        self,
        approval_id: uuid.UUID,
        new_status: ApprovalStatus,
        decided_by: str | None,
        *,
        unexpired_only: bool,
    ) -> bool:
        """Atomically move a row to *new_status*; True only for the caller that won (#18413).

        One conditional UPDATE keyed on the allowed source statuses, so two concurrent decisions
        cannot both pass: the loser matches no row. Resume runs only for the winner.
        """
        allowed_from = [src for src, targets in _VALID_TRANSITIONS.items() if new_status.value in targets]
        conditions = [
            Approval.id == approval_id,
            Approval.company_id.is_(None),
            Approval.status.in_(allowed_from),
        ]
        if unexpired_only:
            conditions.append(or_(Approval.expires_at.is_(None), Approval.expires_at > now_utc()))
        stmt = (
            update(Approval)
            .where(*conditions)
            .values(status=new_status.value, decided_by_user=decided_by, decided_at=now_utc())
            .returning(Approval.id)
        )
        return (await self.session.execute(stmt)).first() is not None

    async def _expire_if_pending(self, approval_id: uuid.UUID) -> Approval | None:
        """Claim pending -> EXPIRED, commit, notify and resume; None when someone else decided first."""
        if not await self._claim(approval_id, ApprovalStatus.EXPIRED, None, unexpired_only=False):
            await self.session.rollback()
            return None
        await self.session.commit()
        approval = await self._reload(approval_id)
        await self._notify("approval_expired", approval)
        logger.info("Approval %s expired", approval_id)
        await resume_decided_approval(approval, self.session)
        return approval

    async def _reload(self, approval_id: uuid.UUID) -> Approval:
        """Re-read the row after a Core UPDATE, bypassing any stale identity-map state."""
        approval = await self._get_or_raise(approval_id)
        await self.session.refresh(approval)
        return approval

    async def _transition(
        self,
        approval_id: uuid.UUID,
        new_status: ApprovalStatus,
        decided_by: str,
        comment: str | None,
        author_type: str,
    ) -> Approval:
        """Perform a status transition atomically; resume the source only for the winning caller."""
        current = await self._get_or_raise(approval_id)
        prior_status = current.status  # read now: a rollback below expires the instance
        if current.expires_at is not None and current.expires_at <= now_utc():
            if prior_status == ApprovalStatus.PENDING.value:
                await self._expire_if_pending(approval_id)
            raise ValueError(f"Cannot transition: approval {approval_id} expired")
        if not await self._claim(approval_id, new_status, decided_by, unexpired_only=True):
            await self.session.rollback()
            raise ValueError(f"Cannot transition from {prior_status} to {new_status.value}")
        if comment:
            # author_type is the verified caller's, never a literal (#17056).
            self.session.add(
                ApprovalComment(approval_id=approval_id, author=decided_by, author_type=author_type, body=comment)
            )
        await self.session.commit()
        approval = await self._reload(approval_id)
        await self._notify(f"approval_{new_status.value}", approval)
        logger.info("Approval %s -> %s by %s", approval_id, new_status.value, decided_by)
        await resume_decided_approval(approval, self.session)
        return approval

    async def _notify(
        self,
        event_type: str,
        approval: Approval,
    ) -> None:
        """Publish the notification: the approval on ``global``, its workflow identity on ``workflow:{id}``.

        ``global`` reaches every authenticated client, so it carries no workflow id (#17354); a subscriber that is
        entitled to a workflow reads those two fields from that workflow's own channel.
        """
        try:
            from events.bus import PersistStrategy, publish_event

            await publish_event(
                "global",
                event_type=event_type,
                payload={
                    "approval_id": str(approval.id),
                    "title": approval.title,
                    "approval_type": approval.approval_type,
                    "status": approval.status,
                    "requested_by_agent": approval.requested_by_agent,
                    "decided_by_user": approval.decided_by_user,
                    "source": approval.source,
                    "risk_tier": approval.risk_tier,
                    "expires_at": approval.expires_at.isoformat() if approval.expires_at else None,
                },
                persist=PersistStrategy.NONE,
            )
            if approval.workflow_id:
                await publish_event(
                    f"workflow:{approval.workflow_id}",
                    event_type=event_type,
                    payload={
                        "approval_id": str(approval.id),
                        "status": approval.status,
                        "workflow_id": approval.workflow_id,
                        "workflow_step": approval.workflow_step,
                    },
                    persist=PersistStrategy.NONE,
                )
        except Exception as exc:
            logger.warning(
                "Failed to publish %s notification: %s",
                event_type,
                exc,
            )
