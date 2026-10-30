# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Map rules, derived handoffs and the status gate of a plan (#19934, section 7A.1 / 7B).

Pure functions over ``CompanyWorkflowPlan``: no session, no clock. The service calls
``evaluate_plan_gate`` on every write and stores the status it returns, so the client never sets one.

``STATUS_LADDER`` is the one place a status is tied to its gates. G5-G7 (``approved``) and
the conversion (``converted``) join it as further rungs when they are delivered; nothing in
``evaluate_plan_gate`` assumes ``labeled`` is the top.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence, Tuple

from .plan_types import (
    CompanyWorkflowPlan,
    Edge,
    Handoff,
    Lane,
    Step,
    SubStepState,
    WorkflowPlanStatus,
)


@dataclass(frozen=True)
class Missing:
    gate: str
    message: str
    step: Optional[str] = None


GateCheck = Callable[[CompanyWorkflowPlan], List[Missing]]


def handoff_key(from_step: str, to_step: str) -> str:
    return f"{from_step}->{to_step}"


def map_errors(lanes: Sequence[Lane], steps: Sequence[Step], edges: Sequence[Edge]) -> List[str]:
    """Why this map cannot be stored; empty when it can (FR-1.1)."""
    errors: List[str] = []
    if len(lanes) < 1:
        errors.append("a plan needs at least 1 lane")
    if len(steps) < 2:
        errors.append("a plan needs at least 2 steps")
    if len(edges) < 1:
        errors.append("a plan needs at least 1 edge")
    errors += _duplicates("lane", [lane.key for lane in lanes]) + _duplicates("step", [s.key for s in steps])
    lane_keys, step_keys = {lane.key for lane in lanes}, {s.key for s in steps}
    errors += [
        f"step {s.key!r} is in lane {s.lane_key!r}, which does not exist" for s in steps if s.lane_key not in lane_keys
    ]
    errors += _edge_errors(edges, step_keys)
    return errors


def _duplicates(kind: str, keys: Sequence[str]) -> List[str]:
    return [f"duplicate {kind} key {k!r}" for k in sorted({k for k in keys if keys.count(k) > 1})]


def _edge_errors(edges: Sequence[Edge], step_keys: set) -> List[str]:
    errors: List[str] = []
    seen = set()
    for e in edges:
        for end in (e.from_step, e.to_step):
            if end not in step_keys:
                errors.append(f"edge {e.from_step!r} -> {e.to_step!r} names step {end!r}, which does not exist")
        if e.from_step == e.to_step:
            errors.append(f"edge {e.from_step!r} -> {e.to_step!r} loops a step onto itself")
        if (e.from_step, e.to_step) in seen:
            errors.append(f"duplicate edge {e.from_step!r} -> {e.to_step!r}")
        seen.add((e.from_step, e.to_step))
    return errors


def map_warnings(steps: Sequence[Step], edges: Sequence[Edge]) -> List[str]:
    """Steps no edge touches: allowed, but almost certainly a drawing slip."""
    touched = {e.from_step for e in edges} | {e.to_step for e in edges}
    return [f"step {s.key!r} has no edge" for s in steps if s.key not in touched]


def derive_handoffs(
    steps: Sequence[Step], edges: Sequence[Edge], notes: Optional[Dict[str, Optional[str]]] = None
) -> List[Handoff]:
    """Every edge whose two steps sit in different lanes is a handoff, and nothing else is (FR-1.3)."""
    lane_of = {s.key: s.lane_key for s in steps}
    notes = notes or {}
    out: List[Handoff] = []
    for e in edges:
        a, b = lane_of.get(e.from_step), lane_of.get(e.to_step)
        if a is None or b is None or a == b:
            continue
        key = handoff_key(e.from_step, e.to_step)
        out.append(
            Handoff(key=key, from_step=e.from_step, to_step=e.to_step, from_lane=a, to_lane=b, wait_note=notes.get(key))
        )
    return out


def _g1_map(plan: CompanyWorkflowPlan) -> List[Missing]:
    found = [Missing("G1", msg) for msg in map_errors(plan.lanes, plan.steps, plan.edges)]
    stored = sorted((h.key, h.from_lane, h.to_lane) for h in plan.handoffs)
    derived = sorted((h.key, h.from_lane, h.to_lane) for h in derive_handoffs(plan.steps, plan.edges))
    if stored != derived:
        found.append(Missing("G1", "handoffs mismatch: they must equal the cross-lane edges exactly"))
    return found


def _g2_measured(plan: CompanyWorkflowPlan) -> List[Missing]:
    have = {m.step_key for m in plan.step_metrics}
    found = [Missing("G2", f"step {s.key!r} has no metric", s.key) for s in plan.steps if s.key not in have]
    if plan.one_number is None:
        found.append(Missing("G2", "the owner has not picked a One Number with a baseline"))
    return found


def _chosen_sub_steps(plan: CompanyWorkflowPlan, state: SubStepState) -> list:
    step = plan.one_number.step_key if plan.one_number else None
    return [s for s in plan.sub_steps if s.step_key == step and s.state is state]


def _g3_broken_down(plan: CompanyWorkflowPlan) -> List[Missing]:
    if plan.one_number is None:
        return [Missing("G3", "no One Number, so no chosen step to break down")]
    step = plan.one_number.step_key
    current = _chosen_sub_steps(plan, SubStepState.CURRENT)
    found = []
    if not current:
        found.append(Missing("G3", f"step {step!r} has no current sub-step", step))
    if not _chosen_sub_steps(plan, SubStepState.PROPOSED):
        found.append(Missing("G3", f"step {step!r} has no proposed sub-step", step))
    keys = {s.key for s in current}
    for s in _chosen_sub_steps(plan, SubStepState.PROPOSED):
        found += [
            Missing("G3", f"sub-step {s.key!r} replaces {r!r}, which is not current", step)
            for r in s.replaces
            if r not in keys
        ]
    return found


def _g4_labeled(plan: CompanyWorkflowPlan) -> List[Missing]:
    if plan.one_number is None:
        return [Missing("G4", "no One Number, so no chosen step to label")]
    step = plan.one_number.step_key
    found = [
        Missing("G4", f"proposed sub-step {s.key!r} has no label", step)
        for s in _chosen_sub_steps(plan, SubStepState.PROPOSED)
        if s.classification is None
    ]
    found += [
        Missing("G4", f"edge case {c.key!r} has no handling", step)
        for c in plan.edge_cases
        if c.step_key == step and not (c.handling or "").strip()
    ]
    return found


#: Each rung: the status it earns and the gates that must all pass, cumulatively.
STATUS_LADDER: Tuple[Tuple[WorkflowPlanStatus, Tuple[GateCheck, ...]], ...] = (
    (WorkflowPlanStatus.MEASURED, (_g1_map, _g2_measured)),
    (WorkflowPlanStatus.LABELED, (_g3_broken_down, _g4_labeled)),
)


@dataclass(frozen=True)
class GateReport:
    status: WorkflowPlanStatus
    next_status: Optional[WorkflowPlanStatus]
    missing: List[Missing]


def evaluate_plan_gate(plan: CompanyWorkflowPlan) -> GateReport:
    """The highest status whose gates (and every lower rung's) pass, and what the next one lacks."""
    earned = WorkflowPlanStatus.DRAFT
    for status, checks in STATUS_LADDER:
        missing = [m for check in checks for m in check(plan)]
        if missing:
            return GateReport(earned, status, missing)
        earned = status
    return GateReport(earned, None, [])
