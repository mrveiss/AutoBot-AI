# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The workflow graph of one role lane, drafted from the plan's sub-steps (#19936, section 7A.3).

Pure. One Start, a process node per sub-step, ``End(done)`` and ``End(failed)``. A process node
fails to ``End(failed)`` ("needs a person"); an edge case routed as a branch becomes an ``if`` with
an ``else`` carrying on; an approval policy with a wait limit adds a ``timeout`` transition; the
last lane's ``End(done)`` hands off to the next lane's workflow, which is created first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from llc.models.company_os_enums import EndOutcome, NodeKind, TransitionKind

from .graph_types import NodeSpec, TransitionSpec
from .plan_types import EdgeCase, Label, PlanApprovalPolicy, SubStep

START, DONE, FAILED = "_start", "_done", "_failed"
RESERVED_NODE_KEYS = (START, DONE, FAILED)


@dataclass
class LaneChain:
    """The converted sub-steps of one lane, in order, and what shapes their graph."""

    workflow_id: str
    subs: List[SubStep]
    handoff_to: Optional[str] = None
    branches: Dict[str, List[EdgeCase]] = field(default_factory=dict)
    policies: Dict[str, PlanApprovalPolicy] = field(default_factory=dict)
    wait_seconds: int = 0


def _nodes(chain: LaneChain, process_key) -> List[NodeSpec]:  # noqa: ANN001
    nodes = [NodeSpec(key=START, kind=NodeKind.START, label="Start")]
    nodes += [NodeSpec(key=s.key, kind=NodeKind.PROCESS, label=s.label, process_key=process_key(s)) for s in chain.subs]
    nodes.append(NodeSpec(key=DONE, kind=NodeKind.END, label="Done", end_outcome=EndOutcome.DONE))
    nodes.append(NodeSpec(key=FAILED, kind=NodeKind.END, label="Needs a person", end_outcome=EndOutcome.FAILED))
    return nodes


def _forward(source: str, target: str, cases: List[EdgeCase]) -> List[TransitionSpec]:
    """Leave *source* for *target*: straight on, or through the ``if``/``else`` of its branch edge cases."""
    if not cases:
        return [TransitionSpec(from_node=source, kind=TransitionKind.SUCCESS, to_node=target)]
    ifs = [
        TransitionSpec(from_node=source, kind=TransitionKind.IF, to_node=FAILED, condition=c.description) for c in cases
    ]
    return ifs + [TransitionSpec(from_node=source, kind=TransitionKind.ELSE, to_node=target)]


def _node_exits(chain: LaneChain, sub: SubStep) -> List[TransitionSpec]:
    out = [TransitionSpec(from_node=sub.key, kind=TransitionKind.FAILURE, to_node=FAILED)]
    policy = chain.policies.get(sub.key)
    if sub.classification is Label.AI and policy is not None and policy.wait_limit:
        out.append(
            TransitionSpec(
                from_node=sub.key, kind=TransitionKind.TIMEOUT, to_node=FAILED, timeout_seconds=chain.wait_seconds
            )
        )
    return out


def _transitions(chain: LaneChain, first: bool) -> List[TransitionSpec]:
    keys = [s.key for s in chain.subs]
    targets = keys[1:] + [DONE]
    out = _forward(START, keys[0], chain.branches.get(START, []) if first else [])
    for sub, target in zip(chain.subs, targets):
        out += _forward(sub.key, target, chain.branches.get(sub.key, [])) + _node_exits(chain, sub)
    if chain.handoff_to is not None:
        out.append(TransitionSpec(from_node=DONE, kind=TransitionKind.HANDOFF, handoff_workflow_id=chain.handoff_to))
    return out


def draft_graph(chain: LaneChain, first: bool, process_key) -> tuple:  # noqa: ANN001
    """The ``(nodes, transitions)`` of one lane's workflow."""
    return _nodes(chain, process_key), _transitions(chain, first)
