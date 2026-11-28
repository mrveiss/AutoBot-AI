# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pure validation of a workflow graph (#18390). No I/O, no session.

*Errors* make a graph unsavable: one Start, every node and End reachable from it,
typed transitions carrying the fields their type needs, references that resolve in
this company, and a cross-role handoff that really crosses roles. *Warnings* are
what the UI surfaces without blocking a draft: a process with no on-failure path,
an ``if`` with no ``else``, a required skill the owner role does not hold.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Set

from llc.models.company_os_enums import MAX_RETRIES, NodeKind, TransitionKind

from .graph_types import GraphContext, GraphReport, GraphSpec, NodeSpec, TransitionSpec

_ACTION_NODES = (NodeKind.PROCESS, NodeKind.META_SKILL)
#: A node may carry at most one outgoing edge of each of these kinds.
_SINGLETON_KINDS = (TransitionKind.SUCCESS, TransitionKind.FAILURE, TransitionKind.ELSE, TransitionKind.TIMEOUT)


def _check_node(node: NodeSpec, ctx: GraphContext) -> List[str]:
    """Per-node field rules: each kind carries exactly its own reference."""
    errs: List[str] = []
    wants = {
        "process_key": node.kind == NodeKind.PROCESS,
        "meta_skill_id": node.kind == NodeKind.META_SKILL,
        "end_outcome": node.kind == NodeKind.END,
    }
    for attr, required in wants.items():
        value = getattr(node, attr)
        if required and value is None:
            errs.append(f"node {node.key!r}: a {node.kind.value} node needs {attr}")
        if not required and value is not None:
            errs.append(f"node {node.key!r}: a {node.kind.value} node must not set {attr}")
    if node.process_key is not None and node.process_key not in ctx.processes:
        errs.append(f"node {node.key!r}: process {node.process_key!r} does not exist in this company")
    if node.meta_skill_id is not None:
        if node.meta_skill_id == ctx.own_workflow_id:
            errs.append(f"node {node.key!r}: a meta skill cannot call itself")
        elif node.meta_skill_id not in ctx.meta_skills:
            errs.append(f"node {node.key!r}: meta skill {node.meta_skill_id!r} does not exist in this company")
    return errs


def _check_nodes(spec: GraphSpec, ctx: GraphContext) -> List[str]:
    errs: List[str] = []
    keys = [n.key for n in spec.nodes]
    for dup in sorted({k for k in keys if keys.count(k) > 1}):
        errs.append(f"node key {dup!r} is used more than once")
    starts = [n for n in spec.nodes if n.kind == NodeKind.START]
    if len(starts) != 1:
        errs.append(f"a workflow needs exactly one Start node, found {len(starts)}")
    if not any(n.kind == NodeKind.END for n in spec.nodes):
        errs.append("a workflow needs at least one End node")
    for node in spec.nodes:
        errs.extend(_check_node(node, ctx))
    return errs


def _check_transition_fields(t: TransitionSpec, ctx: GraphContext) -> List[str]:
    """Each transition type carries exactly the fields its type needs."""
    where = f"transition {t.from_node!r} -{t.kind.value}->"
    errs: List[str] = []
    if t.kind == TransitionKind.HANDOFF:
        if t.to_node is not None:
            errs.append(f"{where} a handoff targets a workflow, not a node")
        errs.extend(_check_handoff(t, ctx, where))
    elif t.to_node is None:
        errs.append(f"{where} needs to_node")
    if t.kind != TransitionKind.HANDOFF and t.handoff_workflow_id is not None:
        errs.append(f"{where} only a handoff may set handoff_workflow_id")
    if t.kind == TransitionKind.FAILURE and t.retry_max is not None and t.retry_max > MAX_RETRIES:
        errs.append(f"{where} retry_max {t.retry_max} exceeds {MAX_RETRIES}")
    if t.kind != TransitionKind.FAILURE and t.retry_max is not None:
        errs.append(f"{where} only a failure transition may set retry_max")
    if t.kind == TransitionKind.IF and not (t.condition or "").strip():
        errs.append(f"{where} an if needs a condition")
    if t.kind != TransitionKind.IF and t.condition is not None:
        errs.append(f"{where} only an if may set a condition")
    if (t.kind == TransitionKind.TIMEOUT) != (t.timeout_seconds is not None):
        errs.append(f"{where} timeout_seconds belongs to, and is required by, a timeout transition")
    return errs


def _check_handoff(t: TransitionSpec, ctx: GraphContext, where: str) -> List[str]:
    """A handoff must target an existing workflow of ANOTHER role, same company."""
    if t.handoff_workflow_id is None:
        return [f"{where} a handoff needs handoff_workflow_id"]
    target = ctx.handoff_targets.get(t.handoff_workflow_id)
    if target is None or target.kind != "workflow":
        return [f"{where} workflow {t.handoff_workflow_id!r} does not exist in this company"]
    if ctx.own_role_id is None:
        return [f"{where} only a workflow owned by a role can hand off"]
    if target.owner_role_id is None:
        return [f"{where} workflow {t.handoff_workflow_id!r} has no owner role"]
    if target.owner_role_id == ctx.own_role_id:
        return [f"{where} a handoff must cross roles; {t.handoff_workflow_id!r} belongs to the same role"]
    return []


def _calls_back(start: str, target: str, calls: Dict[str, frozenset]) -> bool:
    """True when meta skill *start* reaches *target* through stored calls."""
    seen, stack = set(), [start]
    while stack:
        cur = stack.pop()
        if cur == target:
            return True
        if cur not in seen:
            seen.add(cur)
            stack.extend(calls.get(cur, ()))
    return False


def _check_meta_cycles(spec: GraphSpec, ctx: GraphContext) -> List[str]:
    """A meta skill may not, however indirectly, call itself."""
    return [
        f"node {n.key!r}: meta skill {n.meta_skill_id!r} calls back into this one"
        for n in spec.nodes
        if n.meta_skill_id
        and n.meta_skill_id != ctx.own_workflow_id
        and _calls_back(n.meta_skill_id, ctx.own_workflow_id, ctx.meta_calls)
    ]


def _adjacency(spec: GraphSpec) -> Dict[str, List[str]]:
    adj: Dict[str, List[str]] = defaultdict(list)
    for t in spec.transitions:
        if t.to_node is not None:
            adj[t.from_node].append(t.to_node)
    return adj


def _reachable(start: str, adj: Dict[str, List[str]]) -> Set[str]:
    seen, stack = {start}, [start]
    while stack:
        for nxt in adj.get(stack.pop(), ()):
            if nxt not in seen:
                seen.add(nxt)
                stack.append(nxt)
    return seen


def _check_edges(spec: GraphSpec, ctx: GraphContext) -> List[str]:
    kinds = {n.key: n.kind for n in spec.nodes}
    errs: List[str] = []
    for t in spec.transitions:
        errs.extend(_check_transition_fields(t, ctx))
        if t.from_node not in kinds:
            errs.append(f"transition from unknown node {t.from_node!r}")
        elif kinds[t.from_node] == NodeKind.END and t.kind != TransitionKind.HANDOFF:
            errs.append(f"End node {t.from_node!r} can only hand off, not continue")
        if t.to_node is not None and t.to_node not in kinds:
            errs.append(f"transition {t.from_node!r} -> unknown node {t.to_node!r}")
        elif t.to_node is not None and kinds[t.to_node] == NodeKind.START:
            errs.append(f"transition {t.from_node!r} -> Start: Start has no incoming transition")
    for (src, kind), n in _count_by_kind(spec).items():
        if kind in _SINGLETON_KINDS and n > 1:
            errs.append(f"node {src!r} has {n} {kind.value} transitions; at most one")
    return errs


def _count_by_kind(spec: GraphSpec) -> Dict[tuple, int]:
    counts: Dict[tuple, int] = defaultdict(int)
    for t in spec.transitions:
        counts[(t.from_node, t.kind)] += 1
    return counts


def _check_reachability(spec: GraphSpec) -> List[str]:
    starts = [n.key for n in spec.nodes if n.kind == NodeKind.START]
    if len(starts) != 1:
        return []
    seen = _reachable(starts[0], _adjacency(spec))
    errs = []
    for node in spec.nodes:
        if node.key not in seen:
            what = "End" if node.kind == NodeKind.END else "node"
            errs.append(f"{what} {node.key!r} is not reachable from Start")
    return errs


def _warnings(spec: GraphSpec, ctx: GraphContext) -> List[str]:
    out: List[str] = []
    counts = _count_by_kind(spec)
    for node in spec.nodes:
        if node.kind in _ACTION_NODES and counts.get((node.key, TransitionKind.FAILURE), 0) == 0:
            out.append(f"node {node.key!r} has no on-failure path")
        if counts.get((node.key, TransitionKind.IF), 0) and not counts.get((node.key, TransitionKind.ELSE), 0):
            out.append(f"node {node.key!r} has an if without an else")
        for skill in ctx.processes.get(node.process_key or "", []):
            if skill not in ctx.held_skills:
                out.append(f"node {node.key!r}: the owner role does not hold skill {skill!r}")
    return out


def validate_graph(spec: GraphSpec, ctx: GraphContext) -> GraphReport:
    """Validate *spec* against *ctx*; never raises."""
    errors = _check_nodes(spec, ctx) + _check_edges(spec, ctx) + _check_reachability(spec)
    errors += _check_meta_cycles(spec, ctx)
    return GraphReport(errors=errors, warnings=_warnings(spec, ctx))
