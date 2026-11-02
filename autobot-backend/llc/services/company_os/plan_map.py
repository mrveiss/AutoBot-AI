# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The map of a plan: lanes, steps, edges, and the handoffs derived from them (#19934)."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Sequence, Tuple, TypeVar

from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .errors import CompanyOsConflict, CompanyOsNotFound, GraphInvalid
from .loaders import require_role_in_company
from .plan_gate import derive_handoffs, map_errors, map_warnings
from .plan_types import CompanyWorkflowPlan, Edge, Lane, Step

MapParts = Tuple[List[Lane], List[Step], List[Edge]]
M = TypeVar("M", bound=BaseModel)


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


def refuse_dropping_chosen_step(plan: CompanyWorkflowPlan, steps: Sequence[Step]) -> None:
    if plan.one_number and plan.one_number.step_key not in {s.key for s in steps}:
        raise CompanyOsConflict(
            f"step {plan.one_number.step_key!r} holds the One Number: change the One Number before removing it"
        )


def apply_map(plan: CompanyWorkflowPlan, lanes: Sequence[Lane], steps: Sequence[Step], edges: Sequence[Edge]) -> None:
    """Replace the map as a whole, in authoring order, and re-derive the handoffs."""
    refuse_dropping_chosen_step(plan, steps)
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
    kept = {s.key for s in plan.sub_steps}
    plan.approval_policies = [
        p.model_copy(update={"sub_step_keys": [k for k in p.sub_step_keys if k in kept]})
        for p in plan.approval_policies
    ]


# ------------------------------------------------------------ one lane, step or edge at a time (#20086)


def _parts(plan: CompanyWorkflowPlan) -> MapParts:
    return list(plan.lanes), list(plan.steps), list(plan.edges)


def find_index(items: Sequence[M], kind: str, ident: str, same: Callable[[M], bool]) -> int:
    """Where the first item satisfying *same* sits; a 404 naming *kind* and *ident* when none does."""
    for i, item in enumerate(items):
        if same(item):
            return i
    raise CompanyOsNotFound(f"{kind} {ident} does not exist in this plan")


def changed(current: M, fields: Dict[str, Any]) -> M:
    """The model with *fields* set, validated again: a patch cannot step round the model's own rules."""
    try:
        return type(current)(**{**dict(current), **fields})
    except ValidationError as exc:
        raise GraphInvalid([e["msg"] for e in exc.errors()]) from exc


def add_lane(plan: CompanyWorkflowPlan, lane: Lane) -> MapParts:
    lanes, steps, edges = _parts(plan)
    return [*lanes, lane], steps, edges


def patch_lane(plan: CompanyWorkflowPlan, lane_key: str, fields: Dict[str, Any]) -> MapParts:
    lanes, steps, edges = _parts(plan)
    i = find_index(lanes, "lane", repr(lane_key), lambda x: x.key == lane_key)
    lanes[i] = changed(lanes[i], fields)
    return lanes, steps, edges


def remove_lane(plan: CompanyWorkflowPlan, lane_key: str) -> MapParts:
    """A lane that still holds a step is refused by the map rules (422), never emptied silently."""
    lanes, steps, edges = _parts(plan)
    find_index(lanes, "lane", repr(lane_key), lambda x: x.key == lane_key)
    return [x for x in lanes if x.key != lane_key], steps, edges


def add_step(plan: CompanyWorkflowPlan, step: Step) -> MapParts:
    lanes, steps, edges = _parts(plan)
    return lanes, [*steps, step], edges


def patch_step(plan: CompanyWorkflowPlan, step_key: str, fields: Dict[str, Any]) -> MapParts:
    lanes, steps, edges = _parts(plan)
    i = find_index(steps, "step", repr(step_key), lambda x: x.key == step_key)
    steps[i] = changed(steps[i], fields)
    return lanes, steps, edges


def remove_step(plan: CompanyWorkflowPlan, step_key: str) -> MapParts:
    """The step and the edges that touch it; what hangs off it is pruned by ``apply_map``."""
    lanes, steps, edges = _parts(plan)
    find_index(steps, "step", repr(step_key), lambda x: x.key == step_key)
    return (
        lanes,
        [x for x in steps if x.key != step_key],
        [e for e in edges if step_key not in (e.from_step, e.to_step)],
    )


def add_edge(plan: CompanyWorkflowPlan, edge: Edge) -> MapParts:
    lanes, steps, edges = _parts(plan)
    return lanes, steps, [*edges, edge]


def _is_edge(from_step: str, to_step: str) -> Callable[[Edge], bool]:
    return lambda e: (e.from_step, e.to_step) == (from_step, to_step)


def patch_edge(plan: CompanyWorkflowPlan, from_step: str, to_step: str, fields: Dict[str, Any]) -> MapParts:
    lanes, steps, edges = _parts(plan)
    i = find_index(edges, "edge", f"{from_step!r} -> {to_step!r}", _is_edge(from_step, to_step))
    edges[i] = changed(edges[i], fields)
    return lanes, steps, edges


def remove_edge(plan: CompanyWorkflowPlan, from_step: str, to_step: str) -> MapParts:
    lanes, steps, edges = _parts(plan)
    i = find_index(edges, "edge", f"{from_step!r} -> {to_step!r}", _is_edge(from_step, to_step))
    return lanes, steps, [*edges[:i], *edges[i + 1 :]]
