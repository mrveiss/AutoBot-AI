# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Plan -> ``PlanConversion``: how the chosen step's proposed sub-steps map onto Company OS rows (#19936).

Pure: the facts it needs from the database (which roles exist, which have a person holder, which keys
are taken, the wait limit) arrive in ``ConversionFacts``. It never writes and never validates a graph;
``plan_convert`` runs the existing graph validator over what it drafts.

Rules (section 7A.3 and the umbrella's D8, D12): one workflow per role lane, a process per AI or
Automation sub-step, a By Hand sub-step that starts the chain is ``documentation_only`` and one inside
the chain is a person-held node, workflows are always new, and an AI-line change is only proposed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from autobot_shared.ai_lines import AiLine
from llc.services.ai_lines import normalise_key

from .plan_convert_graph import RESERVED_NODE_KEYS, START, LaneChain, draft_graph
from .plan_types import (
    NO_ROLE_HOLDERS,
    AiLineProposal,
    CompanyWorkflowPlan,
    DocumentationOnly,
    EdgeCase,
    EdgeCaseTreatment,
    EdgeCaseTreatmentKind,
    HandoffTreatment,
    HandoffTreatmentKind,
    Label,
    PlanConversion,
    ProcessDraft,
    ProcessExecutor,
    SubStep,
    SubStepState,
    WorkflowDraft,
)

#: The three labels and the AI line each proposes (D3).
LABEL_TO_AI_LINE = {Label.AI: AiLine.DRAFT_THEN_SEND, Label.AUTOMATION: AiLine.AUTONOMOUS, Label.BY_HAND: AiLine.NEVER}
DOC_REASON = "it starts the chain: it is what fires the trigger"


@dataclass(frozen=True)
class ConversionFacts:
    """What the database says, read once by the service. Role ids are this company's only."""

    known_roles: frozenset
    person_roles: frozenset
    agent_roles: frozenset
    taken_process_keys: frozenset
    taken_workflow_ids: frozenset
    wait_seconds: int


def process_key_of(plan: CompanyWorkflowPlan, sub: SubStep) -> str:
    return f"{plan.key}.{sub.key}"


def proposed_sub_steps(plan: CompanyWorkflowPlan) -> List[SubStep]:
    step = plan.one_number.step_key if plan.one_number else None
    subs = [s for s in plan.sub_steps if s.step_key == step and s.state is SubStepState.PROPOSED]
    return sorted(subs, key=lambda s: s.position)


def split_chain(subs: Sequence[SubStep]) -> Tuple[List[SubStep], List[SubStep]]:
    """(documentation, chain): a leading run of By Hand sub-steps starts the chain, so it is handbook text (D8)."""
    lead = 0
    while lead < len(subs) and subs[lead].classification is Label.BY_HAND:
        lead += 1
    return list(subs[:lead]), list(subs[lead:])


def _chain_errors(plan: CompanyWorkflowPlan, chain: Sequence[SubStep], facts: ConversionFacts) -> List[str]:
    lanes = {ln.key: ln for ln in plan.lanes}
    errors = [] if chain else ["no sub-step becomes a process node: there is nothing to create"]
    for s in chain:
        lane = lanes.get(s.lane_key)
        if s.key in RESERVED_NODE_KEYS:
            errors.append(f"sub-step key {s.key!r} is reserved by the graph")
        if lane is None or lane.holder_kind in NO_ROLE_HOLDERS or lane.role_id is None:
            errors.append(
                f"sub-step {s.key!r} sits in lane {s.lane_key!r}, which links no role and cannot own a workflow"
            )
        elif lane.role_id not in facts.known_roles:
            errors.append(f"lane {lane.key!r} links a role that no longer exists in this company")
        elif s.classification is Label.BY_HAND and lane.role_id not in facts.person_roles:
            errors.append(f"By Hand sub-step {s.key!r} sits in lane {lane.key!r}, whose role has no person holder")
        elif s.classification is Label.BY_HAND and lane.role_id in facts.agent_roles:
            errors.append(f"By Hand sub-step {s.key!r} sits in lane {lane.key!r}, whose role an agent also holds")
        if process_key_of(plan, s) in facts.taken_process_keys:
            errors.append(f"process {process_key_of(plan, s)!r} already exists: new workflows only")
    return errors


def _process_drafts(plan: CompanyWorkflowPlan, chain: Sequence[SubStep]) -> List[ProcessDraft]:
    return [
        ProcessDraft(
            process_key=process_key_of(plan, s),
            name=s.label,
            owner_lane_key=s.lane_key,
            sub_step_key=s.key,
            executor=ProcessExecutor.PERSON if s.classification is Label.BY_HAND else ProcessExecutor.ROLE,
        )
        for s in chain
    ]


def _segments(chain: Sequence[SubStep], errors: List[str]) -> List[List[SubStep]]:
    """Consecutive sub-steps of one lane form a segment; a lane may own only one (one workflow per role lane)."""
    out: List[List[SubStep]] = []
    for s in chain:
        if out and out[-1][0].lane_key == s.lane_key:
            out[-1].append(s)
        else:
            if any(seg[0].lane_key == s.lane_key for seg in out):
                errors.append(f"lane {s.lane_key!r} appears twice in the chain: one workflow per role lane")
            out.append([s])
    return out


def _branch_cases(plan: CompanyWorkflowPlan, chain_keys: set) -> Dict[str, List[EdgeCase]]:
    step = plan.one_number.step_key if plan.one_number else None
    out: Dict[str, List[EdgeCase]] = {}
    for c in plan.edge_cases:
        if c.step_key == step and c.classification is not Label.BY_HAND and c.sub_step_key in (None, *chain_keys):
            out.setdefault(c.sub_step_key or START, []).append(c)
    return out


def _edge_case_kind(case: EdgeCase, branched: set, chain_keys: set) -> EdgeCaseTreatmentKind:
    """``handled_in_step`` needs a node: a By Hand case on a leading or unconverted step is documentation (#20187)."""
    if case.key in branched:
        return EdgeCaseTreatmentKind.BRANCH
    if case.classification is Label.BY_HAND and case.sub_step_key in chain_keys:
        return EdgeCaseTreatmentKind.HANDLED_IN_STEP
    return EdgeCaseTreatmentKind.DOCUMENTATION


def _edge_case_treatments(
    plan: CompanyWorkflowPlan, branches: Dict[str, List[EdgeCase]], chain_keys: set
) -> List[EdgeCaseTreatment]:
    step = plan.one_number.step_key if plan.one_number else None
    branched = {c.key for cases in branches.values() for c in cases}
    return [
        EdgeCaseTreatment(edge_case_key=c.key, treatment=_edge_case_kind(c, branched, chain_keys))
        for c in plan.edge_cases
        if c.step_key == step
    ]


def _workflow_drafts(
    plan: CompanyWorkflowPlan,
    segments: List[List[SubStep]],
    branches: Dict[str, List[EdgeCase]],
    facts: ConversionFacts,
) -> List[WorkflowDraft]:
    lanes = {ln.key: ln for ln in plan.lanes}
    ids = [f"{plan.key}.{seg[0].lane_key}" for seg in segments]
    policies = {k: p for p in plan.approval_policies for k in p.sub_step_keys}
    drafts = []
    for i, seg in enumerate(segments):
        chain = LaneChain(ids[i], seg, ids[i + 1] if i + 1 < len(ids) else None, branches, policies, facts.wait_seconds)
        nodes, transitions = draft_graph(chain, i == 0, lambda s: process_key_of(plan, s))
        lane = lanes.get(seg[0].lane_key)
        covering = sorted({policies[s.key].key for s in seg if s.key in policies})
        drafts.append(
            WorkflowDraft(
                workflow_id=ids[i],
                name=f"{plan.name} - {lane.name if lane else seg[0].lane_key}",
                owner_lane_key=seg[0].lane_key,
                trigger_type="manual",
                nodes=nodes,
                transitions=transitions,
                approval_policy_keys=covering,
            )
        )
    return drafts


def _skips_the_chain(h, step: str, adjacent: set, owning: set) -> bool:  # noqa: ANN001
    """A handoff between two lanes of the chain that are not neighbours: no transition is drafted for it."""
    between = h.from_lane in owning and h.to_lane in owning and h.from_lane != h.to_lane
    return step in (h.from_step, h.to_step) and between and (h.from_lane, h.to_lane) not in adjacent


def _handoff_kind(h, step: str, adjacent: set, owning: set, lane_kind: dict) -> HandoffTreatmentKind:  # noqa: ANN001
    """What the conversion does with one plan handoff; a transition is claimed only where one is drafted."""
    if step not in (h.from_step, h.to_step):
        return HandoffTreatmentKind.OUT_OF_SCOPE
    if (h.from_lane, h.to_lane) in adjacent:
        return HandoffTreatmentKind.HANDOFF_TRANSITION
    if h.from_lane in owning and h.to_lane in owning:
        return HandoffTreatmentKind.OUT_OF_SCOPE  # a placeholder: ``_handoff_errors`` blocks the conversion
    if h.to_step == step:
        return HandoffTreatmentKind.TRIGGER
    ends = lane_kind.get(h.to_lane) in NO_ROLE_HOLDERS
    return HandoffTreatmentKind.END if ends else HandoffTreatmentKind.OUT_OF_SCOPE


def _handoff_errors(plan: CompanyWorkflowPlan, segments: List[List[SubStep]]) -> List[str]:
    """One error per handoff that skips over a lane of the chain: the author must restructure it (#20187)."""
    step = plan.one_number.step_key if plan.one_number else None
    owning = {seg[0].lane_key for seg in segments}
    adjacent = {(a[0].lane_key, b[0].lane_key) for a, b in zip(segments, segments[1:])}
    return [
        f"handoff {h.key!r} runs from lane {h.from_lane!r} to lane {h.to_lane!r}, which are not neighbours in the "
        "chain: no transition is drafted for it, so restructure the plan"
        for h in plan.handoffs
        if _skips_the_chain(h, step, adjacent, owning)
    ]


def _handoff_treatments(plan: CompanyWorkflowPlan, segments: List[List[SubStep]]) -> List[HandoffTreatment]:
    step = plan.one_number.step_key if plan.one_number else None
    owning = {seg[0].lane_key for seg in segments}
    adjacent = {(a[0].lane_key, b[0].lane_key) for a, b in zip(segments, segments[1:])}
    lane_kind = {ln.key: ln.holder_kind for ln in plan.lanes}
    out = [
        HandoffTreatment(handoff_key=h.key, treatment=_handoff_kind(h, step, adjacent, owning, lane_kind))
        for h in plan.handoffs
    ]
    for a, b in zip(segments, segments[1:]):
        out.append(
            HandoffTreatment(handoff_key=f"{a[-1].key}->{b[0].key}", treatment=HandoffTreatmentKind.HANDOFF_TRANSITION)
        )
    return out


def _ai_line_proposals(subs: Sequence[SubStep], errors: List[str]) -> List[AiLineProposal]:
    """One proposal per tool action; two sub-steps asking for different lines is the plan's mistake to fix."""
    seen: Dict[str, AiLineProposal] = {}
    for s in subs:
        if not s.tool_action or s.classification is None:
            continue
        try:
            key = normalise_key(s.tool_action)
        except ValueError as exc:
            errors.append(f"sub-step {s.key!r}: tool action {s.tool_action!r}: {exc}")
            continue
        line = LABEL_TO_AI_LINE[s.classification].value
        if key in seen and seen[key].line != line:
            errors.append(f"tool action {key!r} is labeled for two lines ({seen[key].line}, {line})")
        seen.setdefault(key, AiLineProposal(tool_action=key, line=line, sub_step_key=s.key))
    return list(seen.values())


def build_conversion(plan: CompanyWorkflowPlan, facts: ConversionFacts) -> PlanConversion:
    """The preview contract of *plan*, without graph validation. Problems land in ``contract_errors``."""
    subs = proposed_sub_steps(plan)
    docs, chain = split_chain(subs)
    errors = _chain_errors(plan, chain, facts)
    segments = _segments(chain, errors)
    errors += _handoff_errors(plan, segments)
    branches = _branch_cases(plan, {s.key for s in chain})
    workflows = _workflow_drafts(plan, segments, branches, facts) if chain else []
    errors += [
        f"workflow {w.workflow_id!r} already exists: new workflows only"
        for w in workflows
        if w.workflow_id in facts.taken_workflow_ids
    ]
    return PlanConversion(
        processes=_process_drafts(plan, chain),
        workflows=workflows,
        creation_order=[w.workflow_id for w in reversed(workflows)],
        documentation_only=[DocumentationOnly(sub_step_key=s.key, reason=DOC_REASON) for s in docs],
        handoff_treatments=_handoff_treatments(plan, segments),
        edge_case_treatments=_edge_case_treatments(plan, branches, {s.key for s in chain}),
        ai_line_proposals=_ai_line_proposals(subs, errors),
        approval_policies=list(plan.approval_policies),
        contract_errors=errors,
    )
