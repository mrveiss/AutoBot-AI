# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sub-steps, edge cases and labels of the chosen step (#19934, FR-4 and FR-5)."""

from __future__ import annotations

from typing import List, Sequence

from .errors import CompanyOsConflict, CompanyOsNotFound, GraphInvalid
from .plan_measure import find_step
from .plan_types import CompanyWorkflowPlan, EdgeCase, PlanApprovalPolicy, SubStep, SubStepState


def _breakdown_errors(sub_steps: Sequence[SubStep], edge_cases: Sequence[EdgeCase]) -> List[str]:
    keys = [s.key for s in sub_steps]
    errors = [f"duplicate sub-step key {k!r}" for k in sorted({k for k in keys if keys.count(k) > 1})]
    current = {s.key for s in sub_steps if s.state is SubStepState.CURRENT}
    seen_proposed = False
    for s in sub_steps:
        seen_proposed = seen_proposed or s.state is SubStepState.PROPOSED
        if s.state is SubStepState.CURRENT and seen_proposed:
            errors.append(f"current sub-step {s.key!r} comes after a proposed one: list current first")
        if s.state is SubStepState.CURRENT and s.replaces:
            errors.append(f"current sub-step {s.key!r} cannot replace anything")
        errors += [
            f"sub-step {s.key!r} replaces {r!r}, which is not a current sub-step"
            for r in s.replaces
            if r not in current
        ]
    errors += [
        f"edge case {c.key!r} names sub-step {c.sub_step_key!r}, which does not exist"
        for c in edge_cases
        if c.sub_step_key is not None and c.sub_step_key not in set(keys)
    ]
    return errors


def replace_breakdown(
    plan: CompanyWorkflowPlan, step_key: str, sub_steps: Sequence[SubStep], edge_cases: Sequence[EdgeCase]
) -> None:
    """Whole replace of the chosen step's sub-steps and edge cases (FR-4.1, FR-4.2)."""
    step = find_step(plan, step_key)
    if plan.one_number is None or plan.one_number.step_key != step_key:
        raise CompanyOsConflict("pick the One Number on this step before breaking it down")
    fixed = [
        s.model_copy(update={"step_key": step_key, "lane_key": step.lane_key, "position": i})
        for i, s in enumerate(sub_steps)
    ]
    cases = [c.model_copy(update={"step_key": step_key}) for c in edge_cases]
    errors = _breakdown_errors(fixed, cases)
    if errors:
        raise GraphInvalid(errors)
    plan.sub_steps = [s for s in plan.sub_steps if s.step_key != step_key] + fixed
    plan.edge_cases = [c for c in plan.edge_cases if c.step_key != step_key] + cases
    plan.by_hand_acknowledged_at = None  # an acknowledgement covers the breakdown it was given for


def relabel_sub_step(plan: CompanyWorkflowPlan, sub_step_key: str, fields: dict) -> None:
    """Set the label and/or rationale of one sub-step (FR-5.1). A current sub-step takes no label."""
    for i, s in enumerate(plan.sub_steps):
        if s.key != sub_step_key:
            continue
        if fields.get("classification") is not None and s.state is SubStepState.CURRENT:
            raise GraphInvalid([f"sub-step {s.key!r} is current: only proposed sub-steps are labeled"])
        plan.sub_steps[i] = s.model_copy(update=fields)
        plan.by_hand_acknowledged_at = None  # an acknowledgement covers the labels it was given for
        return
    raise CompanyOsNotFound(f"sub-step {sub_step_key!r} does not exist in this plan")


def replace_policies(plan: CompanyWorkflowPlan, policies: Sequence[PlanApprovalPolicy]) -> None:
    """Whole replace of the approval policies (FR-6.2). Each names sub-steps of this plan, and no sub-step twice."""
    known = {s.key for s in plan.sub_steps}
    keys = [p.key for p in policies]
    covered = [k for p in policies for k in p.sub_step_keys]
    errors = [f"duplicate approval policy key {k!r}" for k in sorted({k for k in keys if keys.count(k) > 1})]
    errors += [
        f"policy {p.key!r} names sub-step {k!r}, which does not exist"
        for p in policies
        for k in p.sub_step_keys
        if k not in known
    ]
    errors += [
        f"sub-step {k!r} is covered by two policies" for k in sorted({k for k in covered if covered.count(k) > 1})
    ]
    if errors:
        raise GraphInvalid(errors)
    plan.approval_policies = list(policies)
