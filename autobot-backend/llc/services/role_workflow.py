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
mismatch, so the caller can tell "does not exist" apart from "exists but is
unattributed, and needs reconciling" — those call for different fixes.

#14271: ``_require_workflow`` used to run one *unscoped* ``SELECT ... WHERE
workflow_id = :workflow_id`` — sound only while ``workflow_id`` was a global
primary key, since exactly one row could ever match. Now that
``UNIQUE (company_id, workflow_id)`` allows the same string in more than one
company, that query could return an arbitrary row belonging to a company the
caller has nothing to do with, and — worse — the resulting "does not belong
to company X" message was a cross-tenant presence oracle for a client-supplied
id, the exact defect class #14271 exists to close. The check is now two
queries, each scoped to a company this caller is already allowed to see
(their own, or the unattributed-legacy set), so it never reads — and never
reports on — another company's row.
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

        #14271: each query below is scoped to a company this caller is
        entitled to see (their own, or the unattributed-legacy rows) — never
        to ``workflow_id`` alone. A workflow that exists, but belongs to a
        *different* company, is therefore indistinguishable from one that
        does not exist at all: reporting the two differently would be a
        cross-tenant presence oracle for a client-supplied id.

        The ``company_id == company_id`` query below may use
        ``scalar_one_or_none()`` safely: ``UNIQUE(company_id, workflow_id)``
        guarantees at most one row for any concrete (non-NULL) company_id.
        The ``company_id IS NULL`` query cannot make that assumption — SQL
        unique-constraint semantics treat every NULL as distinct from every
        other NULL, so two legacy rows (e.g. from two backfill runs) can
        legally share a ``workflow_id`` with ``company_id`` both NULL. This
        branch only needs to know whether *any* such row exists — every
        matching row produces the identical "no company attribution" refusal
        regardless of which one is read — so ``.first()`` is the correct,
        deliberate choice here, not merely a way to avoid
        ``MultipleResultsFound``.
        """
        own = await session.execute(
            select(Workflow.workflow_id).where(
                Workflow.workflow_id == workflow_id,
                Workflow.company_id == company_id,
            )
        )
        if own.scalar_one_or_none() is not None:
            return

        unattributed = await session.execute(
            select(Workflow.workflow_id).where(
                Workflow.workflow_id == workflow_id,
                Workflow.company_id.is_(None),
            )
        )
        if unattributed.first() is not None:
            raise ValueError(f"workflow {workflow_id!r} has no company attribution and cannot be " "attached to a role")

        raise ValueError(f"workflow {workflow_id!r} does not exist")

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
