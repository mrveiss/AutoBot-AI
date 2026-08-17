# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped workflow service (#14210, #14271).

Company-scoped CRUD for ``Workflow`` (``models/workflow.py``) — the
foundation a future process node (#13963) will reference. Every method takes
``company_id`` explicitly and filters on it in the query itself (not just in
a post-hoc check) — callers (API routes) are responsible for verifying the
caller may act for that company before invoking these methods, matching
``ContactService`` (``llc/services/contact.py``).

``create`` requires a non-``None`` ``company_id`` — new workflows created
through this service are always company-attributed, even though the
underlying table column stays nullable to hold pre-existing rows backfilled
from Redis by ``services/workflow_redis_backfill.py`` (see
``models/workflow.py`` docstring).

#14271: the table's uniqueness is now ``UNIQUE (company_id, workflow_id)``,
not a global primary key on ``workflow_id`` alone — so a same-company
duplicate is the only case that can still conflict. ``create``'s route-level
pre-check (``get()`` then ``create()``) is TOCTOU under concurrency, so a
race between two same-company requests can still reach the DB constraint;
``create`` catches that ``IntegrityError`` and raises
``WorkflowConflictError`` so the route can translate it to a clean 409
instead of an unhandled 500 (mirrors ``ReviewGatePolicyConflictError`` in
``llc/services/review_gate.py``).
"""

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models.workflow import SOURCE_CREATED, Workflow

from ..models.activity import ActorType
from ..models.enums import WorkflowStatus
from .base import LLCServiceBase


class WorkflowConflictError(Exception):
    """Raised when a workflow_id already exists for this company (unique-constraint race)."""


class WorkflowService(LLCServiceBase):
    """Company-scoped CRUD for the durable workflow identity table."""

    async def create(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        workflow_id: str,
        *,
        name: Optional[str] = None,
        status: str = WorkflowStatus.PLANNED.value,
        definition: Optional[Dict[str, Any]] = None,
        actor: Optional[uuid.UUID] = None,
    ) -> Workflow:
        if company_id is None:
            raise ValueError("company_id is required to create a workflow")
        # Coerce rather than store free text: an unvalidated status column is
        # #13937's defect and #13954 is what it cost. Raises on a bad value so it
        # surfaces as an error, not as a row nothing can ever match.
        status = WorkflowStatus(status).value

        workflow = Workflow(
            workflow_id=workflow_id,
            company_id=company_id,
            name=name,
            status=status,
            source=SOURCE_CREATED,
            definition=definition or {},
            created_by=actor,
        )
        session.add(workflow)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise WorkflowConflictError(
                f"workflow {workflow_id!r} already exists for company {company_id}"
            ) from exc

        if self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=str(company_id),
                actor_type=ActorType.USER if actor else ActorType.SYSTEM,
                actor_id=actor,
                event_type="workflow.created",
                entity_type="workflow",
                entity_id=workflow.workflow_id,
                after={"workflow_id": workflow.workflow_id, "status": workflow.status},
            )
        return workflow

    async def get(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        workflow_id: str,
    ) -> Optional[Workflow]:
        result = await session.execute(
            select(Workflow).where(
                Workflow.workflow_id == workflow_id,
                Workflow.company_id == company_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
    ) -> List[Workflow]:
        result = await session.execute(
            select(Workflow).where(Workflow.company_id == company_id).order_by(Workflow.created_at.desc())
        )
        return list(result.scalars().all())

    async def update_status(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        workflow_id: str,
        status: str,
        *,
        actor: Optional[uuid.UUID] = None,
    ) -> Optional[Workflow]:
        status = WorkflowStatus(status).value
        workflow = await self.get(session, company_id, workflow_id)
        if workflow is None:
            return None
        workflow.status = status
        await session.flush()

        if self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=str(company_id),
                actor_type=ActorType.USER if actor else ActorType.SYSTEM,
                actor_id=actor,
                event_type="workflow.updated",
                entity_type="workflow",
                entity_id=workflow.workflow_id,
                after={"status": status},
            )
        return workflow

    async def delete(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        workflow_id: str,
        *,
        actor: Optional[uuid.UUID] = None,
    ) -> bool:
        """Delete a workflow row. Returns True if a row was deleted.

        Mirrors ``ContactService.delete``'s bool return so the route can 404
        without a second lookup; the audit record is written only after
        ``rowcount`` confirms a row actually matched this company.
        """
        result = await session.execute(
            sa_delete(Workflow).where(
                Workflow.workflow_id == workflow_id,
                Workflow.company_id == company_id,
            )
        )
        deleted = result.rowcount > 0

        if deleted and self.activity_log:
            await self.activity_log.record(
                session=session,
                company_id=str(company_id),
                actor_type=ActorType.USER if actor else ActorType.SYSTEM,
                actor_id=actor,
                event_type="workflow.deleted",
                entity_type="workflow",
                entity_id=workflow_id,
                after=None,
            )
        return deleted


__all__ = ["WorkflowConflictError", "WorkflowService"]
