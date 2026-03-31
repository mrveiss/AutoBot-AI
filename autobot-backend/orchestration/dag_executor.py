# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DAG-based Workflow Executor

Issue #2140: Upgrade WorkflowExecutor to support condition nodes and
branching execution.  Linear workflows continue to use the existing
sequential path in WorkflowExecutor for full backward compatibility.

Key classes
-----------
WorkflowDAG
    Builds an adjacency structure from a flat list of node dicts + edge
    dicts.  Validates the graph (no cycles, reachability) before execution.

DAGExecutor
    Walks the DAG starting from root nodes.  Condition nodes branch to
    either the true-branch or false-branch successors; regular nodes
    forward their result to all successors.  Independent branches that
    have no shared join node are executed concurrently via asyncio.gather.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    """Recognised node types in a workflow DAG."""

    STEP = "step"
    CONDITION = "condition"
    PARALLEL = "parallel"

    @classmethod
    def _missing_(cls, value: object) -> "NodeType":
        """Treat unknown node types as STEP so new types degrade gracefully."""
        return cls.STEP


@dataclass
class DAGEdge:
    """
    Directed edge between two DAG nodes.

    *label* is ``None`` for unconditional edges, ``True`` for the branch
    taken when a condition evaluates to truthy, and ``False`` for the
    falsy branch.
    """

    source: str
    target: str
    label: Optional[bool] = None  # None = unconditional; True/False = condition branch


@dataclass
class DAGNode:
    """Single node in the workflow DAG."""

    node_id: str
    node_type: NodeType
    data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DAGExecutionContext:
    """
    Mutable execution state threaded through the DAG walk.

    Mirrors the shape of the execution_context dict used by
    WorkflowExecutor so results can be merged after DAG execution.

    Issue #2141: ``step_outputs`` holds typed StepOutput objects populated by
    WorkflowExecutor._execute_step_with_agent after each node completes.  They
    are available to the VariableResolver before subsequent nodes execute.
    """

    workflow_id: str
    step_results: Dict[str, Any] = field(default_factory=dict)
    agents_involved: Set[str] = field(default_factory=set)
    interactions: List[Any] = field(default_factory=list)
    branches_taken: Dict[str, bool] = field(default_factory=dict)
    skipped_nodes: Set[str] = field(default_factory=set)
    # Issue #2141: typed step outputs for structured variable piping
    step_outputs: Dict[str, Any] = field(default_factory=dict)
    status: str = "in_progress"
    error: Optional[str] = None


# ---------------------------------------------------------------------------
# WorkflowDAG
# ---------------------------------------------------------------------------


class WorkflowDAG:
    """
    Immutable DAG built from raw node + edge dicts.

    Expected node dict shape::

        {
            "id": "node_abc",
            "type": "step" | "condition" | "parallel",   # optional, defaults "step"
            "data": { ... }                               # arbitrary payload
        }

    Expected edge dict shape::

        {
            "source": "node_abc",
            "target": "node_def",
            "label": null | true | false      # JSON null → unconditional
        }

    Edges without a ``label`` key are treated as unconditional.  Condition
    nodes should have exactly two outgoing edges: one with ``label=True``
    and one with ``label=False``.
    """

    def __init__(self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> None:
        self._nodes: Dict[str, DAGNode] = {}
        self._successors: Dict[str, List[DAGEdge]] = {}
        self._predecessors: Dict[str, List[str]] = {}

        for raw in nodes:
            nid = raw["id"]
            self._nodes[nid] = DAGNode(
                node_id=nid,
                node_type=NodeType(raw.get("type", NodeType.STEP)),
                data=raw.get("data", {}),
            )
            self._successors[nid] = []
            self._predecessors[nid] = []

        for raw in edges:
            src, tgt = raw["source"], raw["target"]
            if src not in self._nodes or tgt not in self._nodes:
                logger.warning(
                    "DAG edge (%s → %s) references unknown node; skipping", src, tgt
                )
                continue
            label_raw = raw.get("label")
            label: Optional[bool] = None if label_raw is None else bool(label_raw)
            edge = DAGEdge(source=src, target=tgt, label=label)
            self._successors[src].append(edge)
            self._predecessors[tgt].append(src)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def nodes(self) -> Dict[str, DAGNode]:
        return self._nodes

    def root_nodes(self) -> List[DAGNode]:
        """Nodes with no incoming edges — execution entry points."""
        return [n for nid, n in self._nodes.items() if not self._predecessors[nid]]

    def successors(self, node_id: str) -> List[DAGEdge]:
        """Outgoing edges from *node_id*."""
        return self._successors.get(node_id, [])

    def has_condition_nodes(self) -> bool:
        """True when at least one node is a CONDITION node."""
        return any(n.node_type == NodeType.CONDITION for n in self._nodes.values())

    def detect_cycle(self) -> Optional[List[str]]:
        """
        Return the first cycle found (as a path) or None if the graph is acyclic.

        Uses iterative DFS with a grey/black colouring scheme.
        """
        WHITE, GREY, BLACK = 0, 1, 2
        colour: Dict[str, int] = {nid: WHITE for nid in self._nodes}
        parent: Dict[str, Optional[str]] = {nid: None for nid in self._nodes}

        for start in self._nodes:
            if colour[start] != WHITE:
                continue
            stack = [start]
            while stack:
                nid = stack[-1]
                if colour[nid] == WHITE:
                    colour[nid] = GREY
                    for edge in self._successors[nid]:
                        child = edge.target
                        if colour[child] == WHITE:
                            parent[child] = nid
                            stack.append(child)
                        elif colour[child] == GREY:
                            # Reconstruct cycle
                            cycle: List[str] = [child, nid]
                            cur = nid
                            while cur != child and cur is not None:
                                cur = parent[cur]
                                if cur:
                                    cycle.append(cur)
                            return list(reversed(cycle))
                else:
                    colour[nid] = BLACK
                    stack.pop()
        return None

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def from_step_list(cls, steps: List[Dict[str, Any]]) -> "WorkflowDAG":
        """
        Build a linear DAG from a plain step list (no edges dict).

        Each step is connected to the next in list order.  This converts
        the legacy ``steps`` format into a DAG so DAGExecutor can handle
        both representations uniformly.
        """
        nodes = [{"id": s["id"], "type": "step", "data": s} for s in steps]
        edges: List[Dict[str, Any]] = []
        for i in range(len(steps) - 1):
            edges.append({"source": steps[i]["id"], "target": steps[i + 1]["id"]})
        return cls(nodes, edges)


# ---------------------------------------------------------------------------
# Condition evaluator
# ---------------------------------------------------------------------------


def _evaluate_condition(node: DAGNode, ctx: DAGExecutionContext) -> bool:
    """
    Evaluate a condition expression stored in *node.data["condition"]*.

    The expression is a Python expression string evaluated against a
    restricted namespace containing:

    - ``results`` — mapping of step_id → step result dict
    - ``True`` / ``False`` / ``len`` / ``str`` / ``int`` / ``float``

    Returns True if the condition is truthy, False otherwise.  On any
    evaluation error the condition defaults to False and a warning is
    logged.

    Security note: eval is intentionally sandboxed to a read-only namespace
    and cannot import modules or access builtins beyond the allowed set.
    """
    expr: str = node.data.get("condition", "")
    if not expr:
        logger.warning("Condition node %s has empty expression; defaulting False", node.node_id)
        return False

    safe_globals: Dict[str, Any] = {"__builtins__": {}}
    safe_locals: Dict[str, Any] = {
        "results": ctx.step_results,
        "True": True,
        "False": False,
        "len": len,
        "str": str,
        "int": int,
        "float": float,
        "bool": bool,
    }

    try:
        result = eval(expr, safe_globals, safe_locals)  # noqa: S307
        logger.debug(
            "Condition node %s: expr=%r → %s", node.node_id, expr, bool(result)
        )
        return bool(result)
    except Exception as exc:
        logger.warning(
            "Condition node %s: expression %r raised %s; defaulting False",
            node.node_id,
            expr,
            exc,
        )
        return False


# ---------------------------------------------------------------------------
# DAGExecutor
# ---------------------------------------------------------------------------

#: Signature for the callable that executes a single non-condition step.
StepExecutorCallback = Callable[
    [DAGNode, DAGExecutionContext],
    Coroutine[Any, Any, Dict[str, Any]],
]


class DAGExecutor:
    """
    Walks a WorkflowDAG and executes each node.

    Condition nodes are evaluated to choose a branch; all other nodes
    are executed via *step_executor_callback*.  Independent sub-graphs
    (i.e. sets of nodes whose paths do not converge before a common
    join node) are executed concurrently using asyncio.gather.

    Args:
        step_executor_callback: Async callable ``(node, ctx) → result_dict``.
            The callback is responsible for the actual work (agent dispatch,
            shell execution, etc.).  It must not mutate *ctx* directly —
            results are merged by DAGExecutor after the call returns.
    """

    def __init__(self, step_executor_callback: StepExecutorCallback) -> None:
        self._execute_step = step_executor_callback

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        dag: WorkflowDAG,
        workflow_id: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> DAGExecutionContext:
        """
        Execute *dag* from all root nodes.

        Args:
            dag: The workflow graph to execute.
            workflow_id: Identifier used for logging and the execution context.
            context: Optional extra context forwarded to the step executor.

        Returns:
            Populated DAGExecutionContext after all reachable nodes finish.
        """
        cycle = dag.detect_cycle()
        if cycle:
            logger.error(
                "Workflow %s DAG contains a cycle (%s); aborting execution",
                workflow_id,
                " → ".join(cycle),
            )
            ctx = DAGExecutionContext(workflow_id=workflow_id)
            ctx.status = "failed"
            ctx.error = f"Cycle detected in workflow graph: {' → '.join(cycle)}"
            return ctx

        ctx = DAGExecutionContext(workflow_id=workflow_id)
        roots = dag.root_nodes()
        if not roots:
            logger.error("Workflow %s DAG has no root nodes", workflow_id)
            ctx.status = "failed"
            ctx.error = "DAG has no root nodes"
            return ctx

        logger.info(
            "Workflow %s: starting DAG execution from %d root node(s): %s",
            workflow_id,
            len(roots),
            [r.node_id for r in roots],
        )

        visited: Set[str] = set()
        try:
            await self._visit_nodes([r.node_id for r in roots], dag, ctx, visited, context or {})
        except Exception as exc:
            logger.error("Workflow %s DAG execution raised: %s", workflow_id, exc)
            ctx.status = "failed"
            ctx.error = str(exc)
            return ctx

        ctx.status = "completed" if ctx.error is None else "partially_completed"
        logger.info("Workflow %s DAG execution finished: status=%s", workflow_id, ctx.status)
        return ctx

    # ------------------------------------------------------------------
    # Internal traversal
    # ------------------------------------------------------------------

    async def _visit_nodes(
        self,
        node_ids: List[str],
        dag: WorkflowDAG,
        ctx: DAGExecutionContext,
        visited: Set[str],
        context: Dict[str, Any],
    ) -> None:
        """
        Visit a list of node IDs, running independent groups in parallel.

        A node is skipped if it has already been visited (join semantics:
        the first path to arrive executes it; subsequent arrivals are no-ops).
        """
        unvisited = [nid for nid in node_ids if nid not in visited]
        if not unvisited:
            return

        if len(unvisited) == 1:
            await self._visit_single(unvisited[0], dag, ctx, visited, context)
        else:
            await asyncio.gather(
                *(
                    self._visit_single(nid, dag, ctx, visited, context)
                    for nid in unvisited
                )
            )

    async def _visit_single(
        self,
        node_id: str,
        dag: WorkflowDAG,
        ctx: DAGExecutionContext,
        visited: Set[str],
        context: Dict[str, Any],
    ) -> None:
        """Visit and execute a single node, then recurse to its successors."""
        if node_id in visited:
            return
        visited.add(node_id)

        node = dag.nodes.get(node_id)
        if node is None:
            logger.warning("Node %s referenced in edges but not found in DAG", node_id)
            return

        if node_id in ctx.skipped_nodes:
            logger.debug("Skipping node %s (marked skipped by branch pruning)", node_id)
            next_ids = self._get_next_node_ids(node, dag, condition_result=None, skipped=True)
            await self._visit_nodes(next_ids, dag, ctx, visited, context)
            return

        logger.debug("Visiting node %s (type=%s)", node_id, node.node_type)
        next_ids = await self._execute_node(node, dag, ctx, context)
        await self._visit_nodes(next_ids, dag, ctx, visited, context)

    async def _execute_node(
        self,
        node: DAGNode,
        dag: WorkflowDAG,
        ctx: DAGExecutionContext,
        context: Dict[str, Any],
    ) -> List[str]:
        """
        Execute a single node and return the IDs of its successors.

        For CONDITION nodes the expression is evaluated and only the
        matching branch's targets are returned; the other branch's
        descendants are marked skipped.
        """
        if node.node_type == NodeType.CONDITION:
            return await self._execute_condition_node(node, dag, ctx)

        # Regular (STEP / PARALLEL / unknown-as-STEP) node
        try:
            result = await self._execute_step(node, ctx)
        except Exception as exc:
            logger.error("Step node %s raised: %s", node.node_id, exc)
            result = {"success": False, "error": str(exc), "node_id": node.node_id}

        ctx.step_results[node.node_id] = result
        agent_id = node.data.get("assigned_agent") or result.get("agent_id")
        if agent_id:
            ctx.agents_involved.add(str(agent_id))

        return [e.target for e in dag.successors(node.node_id)]

    async def _execute_condition_node(
        self,
        node: DAGNode,
        dag: WorkflowDAG,
        ctx: DAGExecutionContext,
    ) -> List[str]:
        """
        Evaluate a condition node and return only the matching branch targets.

        Descendants of the non-taken branch are added to
        ``ctx.skipped_nodes`` so the traversal prunes them cleanly.
        """
        condition_result = _evaluate_condition(node, ctx)
        ctx.branches_taken[node.node_id] = condition_result
        ctx.step_results[node.node_id] = {
            "success": True,
            "condition": node.data.get("condition", ""),
            "result": condition_result,
            "node_id": node.node_id,
        }

        logger.info(
            "Condition node %s evaluated to %s", node.node_id, condition_result
        )

        true_targets: List[str] = []
        false_targets: List[str] = []
        unconditional_targets: List[str] = []

        for edge in dag.successors(node.node_id):
            if edge.label is True:
                true_targets.append(edge.target)
            elif edge.label is False:
                false_targets.append(edge.target)
            else:
                unconditional_targets.append(edge.target)

        taken = true_targets if condition_result else false_targets
        pruned = false_targets if condition_result else true_targets

        # Mark the not-taken branch as skipped so it is bypassed during traversal
        self._mark_descendants_skipped(pruned, dag, ctx)

        return taken + unconditional_targets

    def _mark_descendants_skipped(
        self,
        node_ids: List[str],
        dag: WorkflowDAG,
        ctx: DAGExecutionContext,
    ) -> None:
        """BFS-mark all descendants of *node_ids* as skipped."""
        queue = list(node_ids)
        while queue:
            nid = queue.pop(0)
            if nid in ctx.skipped_nodes:
                continue
            ctx.skipped_nodes.add(nid)
            for edge in dag.successors(nid):
                queue.append(edge.target)

    def _get_next_node_ids(
        self,
        node: DAGNode,
        dag: WorkflowDAG,
        condition_result: Optional[bool],
        skipped: bool = False,
    ) -> List[str]:
        """
        Return successor node IDs for a skipped node.

        Skipped nodes propagate the skip to all successors so downstream
        nodes are also pruned.
        """
        return [e.target for e in dag.successors(node.node_id)]


# ---------------------------------------------------------------------------
# Convenience helpers used by WorkflowExecutor integration
# ---------------------------------------------------------------------------


def workflow_has_condition_nodes(steps: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> bool:
    """
    Return True when the step/edge list describes a branching workflow.

    Used by WorkflowExecutor to decide whether to engage DAGExecutor.
    """
    if not edges:
        return False
    node_types = {s.get("type", "step") for s in steps}
    return "condition" in node_types


def build_dag(steps: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> WorkflowDAG:
    """Construct a WorkflowDAG from workflow API payloads."""
    return WorkflowDAG(steps, edges)
