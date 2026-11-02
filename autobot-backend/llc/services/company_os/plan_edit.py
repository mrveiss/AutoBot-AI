# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Edit one lane, step, edge or edge case of a plan, without resending the rest (#20086).

Every method takes the plan's row lock (``plan_store.locked_plan``), reads the document under it, changes one
thing and saves. Two people editing at once therefore queue on the row: the second reads what the first
committed, so neither overwrites the other's change. Two people changing the SAME item still end with the
later write. A converted revision is refused (409) by the same lock. The map rules, the derived handoffs and
the status are the ones ``PUT /map`` uses, so a single edit and a whole replace cannot disagree.
"""

from __future__ import annotations

import uuid
from functools import partial
from typing import Any, Callable, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from llc.services.base import LLCServiceBase

from . import plan_breakdown, plan_map, plan_store
from .plan_types import CompanyWorkflowPlan, Edge, EdgeCase, Lane, Step

MapChange = Callable[[CompanyWorkflowPlan], plan_map.MapParts]
CaseChange = Callable[[CompanyWorkflowPlan], None]


class PlanEditService(LLCServiceBase):
    async def _map(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, actor: Optional[uuid.UUID], change: MapChange
    ) -> CompanyWorkflowPlan:
        row, plan = await plan_store.locked_plan(session, company_id, plan_key, actor)
        lanes, steps, edges = change(plan)
        plan_map.refuse_dropping_chosen_step(plan, steps)  # a 409 before the map rules can answer 422 for it
        plan_map.check_map(lanes, steps, edges)
        # Only the lanes this edit added or changed: a role removed since from an untouched lane is not this edit's.
        await plan_map.check_roles(session, company_id, [x for x in lanes if x not in plan.lanes])
        plan_map.apply_map(plan, lanes, steps, edges)
        return await plan_store.save_plan(session, row, plan, actor=actor)

    async def _cases(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        actor: Optional[uuid.UUID],
        change: CaseChange,
    ) -> CompanyWorkflowPlan:
        row, plan = await plan_store.locked_plan(session, company_id, plan_key, actor)
        change(plan)
        return await plan_store.save_plan(session, row, plan, actor=actor)

    async def add_lane(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, lane: Lane, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.add_lane, lane=lane)
        return await self._map(session, company_id, plan_key, actor, change)

    async def patch_lane(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        lane_key: str,
        fields: Dict[str, Any],
        *,
        actor: Optional[uuid.UUID],
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.patch_lane, lane_key=lane_key, fields=fields)
        return await self._map(session, company_id, plan_key, actor, change)

    async def delete_lane(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, lane_key: str, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.remove_lane, lane_key=lane_key)
        return await self._map(session, company_id, plan_key, actor, change)

    async def add_step(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, step: Step, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.add_step, step=step)
        return await self._map(session, company_id, plan_key, actor, change)

    async def patch_step(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        step_key: str,
        fields: Dict[str, Any],
        *,
        actor: Optional[uuid.UUID],
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.patch_step, step_key=step_key, fields=fields)
        return await self._map(session, company_id, plan_key, actor, change)

    async def delete_step(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, step_key: str, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.remove_step, step_key=step_key)
        return await self._map(session, company_id, plan_key, actor, change)

    async def add_edge(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, edge: Edge, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.add_edge, edge=edge)
        return await self._map(session, company_id, plan_key, actor, change)

    async def patch_edge(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        from_step: str,
        to_step: str,
        fields: Dict[str, Any],
        *,
        actor: Optional[uuid.UUID],
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.patch_edge, from_step=from_step, to_step=to_step, fields=fields)
        return await self._map(session, company_id, plan_key, actor, change)

    async def delete_edge(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        from_step: str,
        to_step: str,
        *,
        actor: Optional[uuid.UUID],
    ) -> CompanyWorkflowPlan:
        change = partial(plan_map.remove_edge, from_step=from_step, to_step=to_step)
        return await self._map(session, company_id, plan_key, actor, change)

    async def add_edge_case(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        step_key: str,
        case: EdgeCase,
        *,
        actor: Optional[uuid.UUID],
    ) -> CompanyWorkflowPlan:
        change = partial(plan_breakdown.add_edge_case, step_key=step_key, case=case)
        return await self._cases(session, company_id, plan_key, actor, change)

    async def patch_edge_case(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        plan_key: str,
        case_key: str,
        fields: Dict[str, Any],
        *,
        actor: Optional[uuid.UUID],
    ) -> CompanyWorkflowPlan:
        change = partial(plan_breakdown.patch_edge_case, case_key=case_key, fields=fields)
        return await self._cases(session, company_id, plan_key, actor, change)

    async def delete_edge_case(
        self, session: AsyncSession, company_id: uuid.UUID, plan_key: str, case_key: str, *, actor: Optional[uuid.UUID]
    ) -> CompanyWorkflowPlan:
        change = partial(plan_breakdown.remove_edge_case, case_key=case_key)
        return await self._cases(session, company_id, plan_key, actor, change)
