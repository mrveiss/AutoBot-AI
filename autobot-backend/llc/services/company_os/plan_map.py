# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The map of a plan: lanes, steps, edges, and the handoffs derived from them (#19934)."""

from __future__ import annotations

import uuid
from typing import List, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from .errors import CompanyOsConflict, GraphInvalid
from .loaders import require_role_in_company
from .plan_gate import derive_handoffs, map_errors, map_warnings
from .plan_types import CompanyWorkflowPlan, Edge, Lane, Step


async def check_roles(session: AsyncSession, company_id: uuid.UUID, lanes: Sequence[Lane]) -> None:
    """A lane's role must be one of THIS company's; another company's is a 404 (FR-1.2).

    Reads the ``roles`` table only. Nothing here, or anywhere in the planner, creates a role.
    """
    for lane in lanes:
        if lane.role_id is not None:
            await require_role_in_company(session, company_id, lane.role_id)


def check_map(lanes: Sequence[Lane], steps: Sequence[Step], edges: Sequence[Edge]) -> List[str]:
    """Raise ``GraphInvalid`` on any error; return the warnings."""
    errors = map_errors(lanes, steps, edges)
    if errors:
        raise GraphInvalid(errors)
    return map_warnings(steps, edges)


def _refuse_dropping_chosen_step(plan: CompanyWorkflowPlan, steps: Sequence[Step]) -> None:
    if plan.one_number and plan.one_number.step_key not in {s.key for s in steps}:
        raise CompanyOsConflict(
            f"step {plan.one_number.step_key!r} holds the One Number: change the One Number before removing it"
        )


def apply_map(plan: CompanyWorkflowPlan, lanes: Sequence[Lane], steps: Sequence[Step], edges: Sequence[Edge]) -> None:
    """Replace the map as a whole, in authoring order, and re-derive the handoffs."""
    _refuse_dropping_chosen_step(plan, steps)
    notes = {h.key: h.wait_note for h in plan.handoffs}
    plan.lanes = [lane.model_copy(update={"position": i}) for i, lane in enumerate(lanes)]
    plan.steps = [s.model_copy(update={"position": i}) for i, s in enumerate(steps)]
    plan.edges = list(edges)
    plan.handoffs = derive_handoffs(plan.steps, plan.edges, notes)
    _prune_to_steps(plan)


def _prune_to_steps(plan: CompanyWorkflowPlan) -> None:
    """Drop what hangs off a step that is gone; follow a step that moved lanes."""
    lane_of = {s.key: s.lane_key for s in plan.steps}
    plan.step_metrics = [m for m in plan.step_metrics if m.step_key in lane_of]
    plan.sub_steps = [
        s.model_copy(update={"lane_key": lane_of[s.step_key]}) for s in plan.sub_steps if s.step_key in lane_of
    ]
    plan.edge_cases = [c for c in plan.edge_cases if c.step_key in lane_of]
