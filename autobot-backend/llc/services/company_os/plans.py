# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company-scoped Workflow Planner plans (#19934).

Writes need company owner/admin, except a step's self-reported metric, which a member
holding that lane's role may also write (D10). Tenancy is the ``company_id`` the caller
passes -- the router takes it from the authenticated org context and nowhere else.
Creating or editing a plan never creates a ``roles`` row.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.company_os_plan import CompanyOsWorkflowPlan as PlanRow
from llc.services.authz import require_company_admin
from llc.services.base import LLCServiceBase

from . import plan_breakdown, plan_map, plan_measure, plan_store
from .errors import CompanyOsConflict, CompanyOsNotFound
from .plan_gate import GateReport, gate, map_errors
from .plan_types import CompanyWorkflowPlan, Edge, Lane, PlanStatus, Step

_META_FIELDS = ("name", "industry", "headcount", "starts_at", "ends_at")


class CompanyOsPlanService(LLCServiceBase):
    async def _writable(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, actor: Optional[uuid.UUID]
    ) -> Tuple[PlanRow, CompanyWorkflowPlan]:
        await require_company_admin(session, company_id, actor)
        row = await plan_store.load_writable(session, company_id, plan_key)
        return row, plan_store.read_plan(row)

    async def create(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        *,
        actor: Optional[uuid.UUID],
        lanes: Sequence[Lane],
        steps: Sequence[Step],
        edges: Sequence[Edge],
        **fields: Any,
    ) -> CompanyWorkflowPlan:
        await require_company_admin(session, company_id, actor)
        plan_map.check_map(lanes, steps, edges)
        await plan_map.check_roles(session, company_id, lanes)
        if await plan_store.plan_key_taken(session, company_id, fields["key"]):
            raise CompanyOsConflict(f"workflow plan {fields['key']!r} already exists")
        plan = CompanyWorkflowPlan(**fields)
        plan_map.apply_map(plan, lanes, steps, edges)
        row = PlanRow(company_id=company_id, plan_key=plan.key, revision=1, created_by=actor, document={})
        return await plan_store.save(session, row, plan, actor=actor)

    async def get(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, revision: Optional[int] = None
    ) -> CompanyWorkflowPlan:
        return plan_store.read_plan(await plan_store.load_row(session, company_id, plan_key, revision))

    async def list(
        self, session: AsyncSession, company_id: uuid.UUID, status: Optional[PlanStatus] = None
    ) -> List[PlanRow]:
        """The latest revision of every plan, newest activity first."""
        latest = (
            select(PlanRow.plan_key, func.max(PlanRow.revision).label("rev"))
            .where(PlanRow.company_id == company_id)
            .group_by(PlanRow.plan_key)
            .subquery()
        )
        stmt = select(PlanRow).join(
            latest, (PlanRow.plan_key == latest.c.plan_key) & (PlanRow.revision == latest.c.rev)
        )
        stmt = stmt.where(PlanRow.company_id == company_id).order_by(PlanRow.updated_at.desc(), PlanRow.plan_key)
        if status is not None:
            stmt = stmt.where(PlanRow.status == status.value)
        return list((await session.execute(stmt)).scalars().all())

    async def update_meta(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, *, actor: Optional[uuid.UUID], **fields: Any
    ) -> CompanyWorkflowPlan:
        row, plan = await self._writable(session, company_id, plan_key, actor)
        for name in _META_FIELDS:
            if name in fields:
                setattr(plan, name, fields[name])
        return await plan_store.save(session, row, plan, actor=actor)

    async def delete(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, *, actor: Optional[uuid.UUID]
    ) -> None:
        await require_company_admin(session, company_id, actor)
        rows = (
            (
                await session.execute(
                    select(PlanRow).where(PlanRow.company_id == company_id, PlanRow.plan_key == plan_key)
                )
            )
            .scalars()
            .all()
        )
        if not rows:
            raise CompanyOsNotFound(f"workflow plan {plan_key!r} does not exist in this company")
        if any(r.status == PlanStatus.CONVERTED.value for r in rows):
            raise CompanyOsConflict("a converted plan cannot be deleted: its workflows may still exist")
        for r in rows:
            await session.delete(r)
        await session.flush()

    async def gate_report(self, session: AsyncSession, company_id: uuid.UUID, plan_key: str) -> GateReport:
        return gate(await self.get(session, company_id, plan_key))

    async def validate_map(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        lanes: Sequence[Lane],
        steps: Sequence[Step],
        edges: Sequence[Edge],
    ) -> Tuple[List[str], List[str]]:
        """Dry run (FR-1.4): the errors and warnings of a map, nothing written."""
        await plan_map.check_roles(session, company_id, lanes)
        return map_errors(lanes, steps, edges), plan_map.map_warnings(steps, edges)

    async def replace_map(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        *,
        actor: Optional[uuid.UUID],
        lanes: Sequence[Lane],
        steps: Sequence[Step],
        edges: Sequence[Edge],
    ) -> CompanyWorkflowPlan:
        row, plan = await self._writable(session, company_id, plan_key, actor)
        plan_map.check_map(lanes, steps, edges)
        await plan_map.check_roles(session, company_id, lanes)
        plan_map.apply_map(plan, lanes, steps, edges)
        return await plan_store.save(session, row, plan, actor=actor)

    async def set_wait_note(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        handoff_key: str,
        wait_note: Optional[str],
        *,
        actor: Optional[uuid.UUID],
    ) -> CompanyWorkflowPlan:
        """The only thing a client may say about a handoff."""
        row, plan = await self._writable(session, company_id, plan_key, actor)
        for i, h in enumerate(plan.handoffs):
            if h.key == handoff_key:
                plan.handoffs[i] = h.model_copy(update={"wait_note": wait_note})
                return await plan_store.save(session, row, plan, actor=actor)
        raise CompanyOsNotFound(f"handoff {handoff_key!r} is not derived from any edge of this plan")

    async def _metric_target(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, step_key: str, actor: Optional[uuid.UUID]
    ) -> Tuple[PlanRow, CompanyWorkflowPlan]:
        """The writable plan, after checking the actor may write THIS step's metric (D10).

        Checked before the row lock, so a caller who may not write cannot hold it, and again under
        the lock, because the map may have moved the step to another lane in between.
        """
        unlocked = plan_store.read_plan(await plan_store.load_row(session, company_id, plan_key))
        await self._require_step_writer(session, company_id, unlocked, step_key, actor)
        row = await plan_store.load_writable(session, company_id, plan_key)
        plan = plan_store.read_plan(row)
        await self._require_step_writer(session, company_id, plan, step_key, actor)
        return row, plan

    @staticmethod
    async def _require_step_writer(
        session: AsyncSession,
        company_id: uuid.UUID,
        plan: CompanyWorkflowPlan,
        step_key: str,
        actor: Optional[uuid.UUID],
    ) -> None:
        lane_key = plan_measure.find_step(plan, step_key).lane_key
        role_id = next((ln.role_id for ln in plan.lanes if ln.key == lane_key), None)
        await plan_measure.require_metric_writer(session, company_id, actor, role_id)

    async def put_metric(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        step_key: str,
        *,
        actor: Optional[uuid.UUID],
        frequency: tuple,
        duration: tuple,
    ) -> CompanyWorkflowPlan:
        row, plan = await self._metric_target(session, company_id, plan_key, step_key, actor)
        plan_measure.set_metric(plan, step_key, frequency, duration, actor)
        return await plan_store.save(session, row, plan, actor=actor)

    async def delete_metric(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, step_key: str, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        row, plan = await self._metric_target(session, company_id, plan_key, step_key, actor)
        plan.step_metrics = [m for m in plan.step_metrics if m.step_key != step_key]
        return await plan_store.save(session, row, plan, actor=actor)

    async def put_one_number(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, *, actor: Optional[uuid.UUID], **fields: Any
    ) -> CompanyWorkflowPlan:
        row, plan = await self._writable(session, company_id, plan_key, actor)
        await plan_measure.set_one_number(session, company_id, plan, actor=actor, **fields)
        return await plan_store.save(session, row, plan, actor=actor)

    async def put_breakdown(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        step_key: str,
        *,
        actor: Optional[uuid.UUID],
        sub_steps: Sequence[Any],
        edge_cases: Sequence[Any],
    ) -> CompanyWorkflowPlan:
        row, plan = await self._writable(session, company_id, plan_key, actor)
        plan_breakdown.replace_breakdown(plan, step_key, sub_steps, edge_cases)
        return await plan_store.save(session, row, plan, actor=actor)

    async def patch_sub_step(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        sub_step_key: str,
        *,
        actor: Optional[uuid.UUID],
        **fields: Any,
    ) -> CompanyWorkflowPlan:
        row, plan = await self._writable(session, company_id, plan_key, actor)
        plan_breakdown.relabel_sub_step(plan, sub_step_key, fields)
        return await plan_store.save(session, row, plan, actor=actor)

    async def acknowledge_by_hand(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        """G5's owner confirmation. It is not an edit of the plan, so it keeps an approval."""
        row, plan = await self._writable(session, company_id, plan_key, actor)
        plan.by_hand_acknowledged_at = datetime.now(timezone.utc)
        return await plan_store.save(session, row, plan, actor=actor, clears_approval=False)
