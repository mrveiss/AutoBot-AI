# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attach and detach workflows on a role (#14221 step 5).

The attachment belongs to the role, so a change of holder moves nothing here —
that is the point of #14221. Offboarding (step 4) therefore has nothing to
transfer for workflows: they were never the occupant's.

Two guards matter more than the CRUD:

* the role must exist **in this company** (#14222's orphan-reference shape), and
* the workflow must belong to **the same company**.

The second one has a wrinkle worth stating: ``Workflow.company_id`` is
**nullable**, because rows backfilled from Redis carry no company attribution
(``source = legacy_redis_unattributed``). Attaching one of those to a company's
role would give that company a workflow nobody has established it owns.

The NULL case gets its own error rather than being folded into the ownership
mismatch. To be precise about what that buys: comparing ``None != company_id``
in Python is already ``True``, so an unattributed workflow would be refused
either way — the branch does not close a bypass. What it closes is a
*diagnostic* gap. Without it the caller is told the workflow "does not belong to
company X", which reads as "it belongs to someone else" when the truth is "it
belongs to nobody yet, and needs attributing". Those call for different fixes.
A guard expressed as a SQL predicate instead of a Python comparison would be
worse still, reporting the row as simply missing.
"""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sa_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.workflow import Workflow
from user_management.models.role import Role

from ..models.activity import ActorType
from ..models.role_workflow import LLCRoleWorkflow
from .authz import require_company_admin
from .base import LLCServiceBase


class RoleWorkflowService(LLCServiceBase):
    """Company-scoped attachment of workflows to roles."""

    async def _record(
        self,
        session: AsyncSession,
        attachment: LLCRoleWorkflow,
        event_type: str,
        actor: Optional[str],
        after: Optional[Dict[str, Any]],
    ) -> None:
        """Emit one activity-log event, or nothing if the DI slot is unpopulated."""
        if not self.activity_log:
            return
        await self.activity_log.record(
            session=session,
            company_id=str(attachment.company_id),
            actor_type=ActorType.USER if actor else ActorType.SYSTEM,
            actor_id=actor,
            event_type=event_type,
            entity_type="llc_role_workflow",
            entity_id=str(attachment.id),
            after=after,
        )

    async def _require_role(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> None:
        result = await session.execute(select(Role.id).where(Role.id == role_id, Role.org_id == company_id))
        if result.scalar_one_or_none() is None:
            raise ValueError(f"role {role_id} does not exist in company {company_id}")

    async def _require_workflow(self, session: AsyncSession, company_id: uuid.UUID, workflow_id: str) -> None:
        """The workflow must exist and belong to this company.

        A NULL ``company_id`` is refused distinctly from a missing row: it means
        the workflow predates company attribution, not that it is absent.
        """
        result = await session.execute(select(Workflow.company_id).where(Workflow.workflow_id == workflow_id))
        row = result.first()
        if row is None:
            raise ValueError(f"workflow {workflow_id!r} does not exist")

        owner = row[0]
        if owner is None:
            raise ValueError(f"workflow {workflow_id!r} has no company attribution and cannot be " "attached to a role")
        if owner != company_id:
            raise ValueError(f"workflow {workflow_id!r} does not belong to company {company_id}")

    async def attach(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        workflow_id: str,
        actor_user_id: uuid.UUID,
    ) -> LLCRoleWorkflow:
        if company_id is None or role_id is None or not (workflow_id or "").strip():
            raise ValueError("company_id, role_id and workflow_id are all required")

        # Attaching a workflow to a role changes what every current and future
        # holder of that role runs, so it is an admin action — same gate as
        # occupancy and permissions.
        await require_company_admin(session, company_id, actor_user_id)
        await self._require_role(session, company_id, role_id)
        await self._require_workflow(session, company_id, workflow_id)

        if await self.get(session, company_id, role_id, workflow_id) is not None:
            raise ValueError(f"workflow {workflow_id!r} is already attached to role {role_id}")

        attachment = LLCRoleWorkflow(company_id=company_id, role_id=role_id, workflow_id=workflow_id)
        session.add(attachment)
        await session.flush()
        await self._record(
            session,
            attachment,
            "role_workflow.attached",
            str(actor_user_id),
            {"role_id": str(role_id), "workflow_id": workflow_id},
        )
        return attachment

    async def get(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        workflow_id: str,
    ) -> Optional[LLCRoleWorkflow]:
        result = await session.execute(
            select(LLCRoleWorkflow).where(
                LLCRoleWorkflow.company_id == company_id,
                LLCRoleWorkflow.role_id == role_id,
                LLCRoleWorkflow.workflow_id == workflow_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_for_role(
        self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID
    ) -> List[LLCRoleWorkflow]:
        """Workflows this role carries — independent of who currently holds it."""
        result = await session.execute(
            select(LLCRoleWorkflow)
            .where(
                LLCRoleWorkflow.company_id == company_id,
                LLCRoleWorkflow.role_id == role_id,
            )
            .order_by(LLCRoleWorkflow.workflow_id)
        )
        return list(result.scalars().all())

    async def roles_for_workflow(self, session: AsyncSession, company_id: uuid.UUID, workflow_id: str) -> List[Role]:
        """Which roles run this workflow — the reverse lookup an audit needs."""
        result = await session.execute(
            select(Role)
            .join(LLCRoleWorkflow, LLCRoleWorkflow.role_id == Role.id)
            .where(
                Role.org_id == company_id,
                LLCRoleWorkflow.company_id == company_id,
                LLCRoleWorkflow.workflow_id == workflow_id,
            )
            .order_by(Role.name)
        )
        return list(result.scalars().all())

    async def detach(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        workflow_id: str,
        *,
        actor_user_id: uuid.UUID,
    ) -> bool:
        """Remove an attachment. Returns True when a row was actually removed.

        Unlike ending a tenure, this deletes the row. A tenure is a fact about
        the past that later questions depend on; an attachment is a statement
        about the present, and the activity log carries the history of changes
        to it.
        """
        await require_company_admin(session, company_id, actor_user_id)
        attachment = await self.get(session, company_id, role_id, workflow_id) if self.activity_log else None
        result = await session.execute(
            sa_delete(LLCRoleWorkflow).where(
                LLCRoleWorkflow.company_id == company_id,
                LLCRoleWorkflow.role_id == role_id,
                LLCRoleWorkflow.workflow_id == workflow_id,
            )
        )
        detached = bool(result.rowcount)
        if detached and attachment is not None:
            await self._record(
                session,
                attachment,
                "role_workflow.detached",
                str(actor_user_id),
                {"role_id": str(role_id), "workflow_id": workflow_id},
            )
        return detached
