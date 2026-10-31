# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Sub-steps, edge cases and labels of the chosen step (#19934, FR-4 and FR-5)."""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Sequence

from .errors import CompanyOsConflict, CompanyOsNotFound, GraphInvalid
from .plan_map import changed, find_index
from .plan_measure import find_step
from .plan_types import CompanyWorkflowPlan, EdgeCase, Label, PlanApprovalPolicy, SubStep, SubStepState


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
    case_keys = [c.key for c in edge_cases]
    errors += [f"duplicate edge case key {k!r}" for k in sorted({k for k in case_keys if case_keys.count(k) > 1})]
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


def _step_cases(plan: CompanyWorkflowPlan, step_key: str) -> List[EdgeCase]:
    return [c for c in plan.edge_cases if c.step_key == step_key]


def _store_cases(plan: CompanyWorkflowPlan, step_key: str, cases: List[EdgeCase]) -> None:
    """Check *cases* against the step's sub-steps, then replace that step's edge cases with them."""
    errors = _breakdown_errors([s for s in plan.sub_steps if s.step_key == step_key], cases)
    if errors:
        raise GraphInvalid(errors)
    plan.edge_cases = [c for c in plan.edge_cases if c.step_key != step_key] + cases


def _case_index(cases: Sequence[EdgeCase], case_key: str) -> int:
    return find_index(cases, "edge case", repr(case_key), lambda c: c.key == case_key)


def add_edge_case(plan: CompanyWorkflowPlan, step_key: str, case: EdgeCase) -> None:
    """Add one edge case to the chosen step (FR-4.2); a key the step already uses is a 422."""
    find_step(plan, step_key)
    if plan.one_number is None or plan.one_number.step_key != step_key:
        raise CompanyOsConflict("pick the One Number on this step before breaking it down")
    added = case.model_copy(update={"step_key": step_key})
    _store_cases(plan, step_key, [*_step_cases(plan, step_key), added])


def _edge_case_step(plan: CompanyWorkflowPlan, case_key: str) -> str:
    return plan.edge_cases[_case_index(plan.edge_cases, case_key)].step_key


def patch_edge_case(plan: CompanyWorkflowPlan, case_key: str, fields: Dict[str, Any]) -> None:
    step_key = _edge_case_step(plan, case_key)
    cases = _step_cases(plan, step_key)
    i = _case_index(cases, case_key)
    cases[i] = changed(cases[i], fields)
    _store_cases(plan, step_key, cases)


def remove_edge_case(plan: CompanyWorkflowPlan, case_key: str) -> None:
    step_key = _edge_case_step(plan, case_key)
    cases = _step_cases(plan, step_key)
    del cases[_case_index(cases, case_key)]
    _store_cases(plan, step_key, cases)


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


def _repeated(values: Sequence[str]) -> List[str]:
    """The values that occur more than once, sorted; one pass."""
    return sorted(k for k, n in Counter(values).items() if n > 1)


def _policy_target_errors(plan: CompanyWorkflowPlan, policies: Sequence[PlanApprovalPolicy]) -> List[str]:
    """A policy makes an AI sub-step wait for a person: it cannot name a missing, current or By Hand one (#20168)."""
    subs = {s.key: s for s in plan.sub_steps}
    errors: List[str] = []
    for p in policies:
        for k in p.sub_step_keys:
            sub = subs.get(k)
            if sub is None:
                errors.append(f"policy {p.key!r} names sub-step {k!r}, which does not exist")
            elif sub.state is SubStepState.CURRENT:
                errors.append(f"policy {p.key!r} names sub-step {k!r}, which is current and is not converted")
            elif sub.classification is Label.BY_HAND:
                errors.append(f"policy {p.key!r} names sub-step {k!r}, which is By Hand: a person already does it")
    return errors


def replace_policies(plan: CompanyWorkflowPlan, policies: Sequence[PlanApprovalPolicy]) -> None:
    """Whole replace of the approval policies (FR-6.2). Each names sub-steps of this plan, and no sub-step twice."""
    covered = [k for p in policies for k in p.sub_step_keys]
    errors = [f"duplicate approval policy key {k!r}" for k in _repeated([p.key for p in policies])]
    errors += _policy_target_errors(plan, policies)
    errors += [f"sub-step {k!r} is covered by two policies" for k in _repeated(covered)]
    if errors:
        raise GraphInvalid(errors)
    plan.approval_policies = list(policies)
