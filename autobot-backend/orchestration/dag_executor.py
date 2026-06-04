# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
DAG-based Workflow Executor

Issue #2140: Upgrade WorkflowExecutor to support condition nodes and
branching execution.  Linear workflows continue to use the existing
sequential path in WorkflowExecutor for full backward compatibility.

Executor scope (#6826): DAGExecutor is the **production DAG engine**.  It
owns asyncio-based parallel fan-out for independent branches and condition/
branch routing.  The intended successor (GraphRunner via DAGGraphAdapter) is
not yet in production because parallel fan-out is not yet supported there
(tracked in #6826).  Until that gap closes, ``WorkflowExecutor`` delegates
here for all DAG workflows.

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
import ssl
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Set

from autobot_shared.logging_manager import get_logger
from autobot_shared.ssot_config import config
from constants.status_enums import TaskStatus

from .success_criteria import SuccessCriteriaEvaluator

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


class NodeType(str, Enum):
    """Recognised node types in a workflow DAG."""

    STEP = "step"
    CONDITION = "condition"
    PARALLEL = "parallel"
    DISTRIBUTED_SHELL = "distributed_shell"  # Issue #3406: fleet fan-out
    SWITCH = "switch"

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
    label: bool | str | None = None
    # None = unconditional; True/False = condition branch;
    # str = switch-case label ("default" is the catch-all case)


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
    error: str | None = None
    criteria_evaluation: Dict[str, Any] = field(default_factory=dict)


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

    def __init__(
        self, nodes: List[Dict[str, Any]], edges: List[Dict[str, Any]]
    ) -> None:
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
            label: bool | None = None if label_raw is None else bool(label_raw)
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

    def predecessors(self, node_id: str) -> List[str]:
        """IDs of nodes with edges into *node_id* (#7010 cluster 1).

        Public read-only accessor for the predecessor map; needed by branch
        pruning to detect diamond joins where one branch is taken and the
        other is pruned — the join node itself must remain executable from
        the live branch.
        """
        return list(self._predecessors.get(node_id, []))

    def has_condition_nodes(self) -> bool:
        """True when at least one node is a CONDITION node."""
        return any(n.node_type == NodeType.CONDITION for n in self._nodes.values())

    def detect_cycle(self) -> List[str] | None:
        """
        Return the first cycle found (as a path) or None if the graph is acyclic.

        Uses iterative DFS with a grey/black colouring scheme.
        """
        WHITE, GREY, BLACK = 0, 1, 2
        colour: Dict[str, int] = {nid: WHITE for nid in self._nodes}
        parent: Dict[str, str | None] = {nid: None for nid in self._nodes}

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


_JSONPATH_OPS = (">=", "<=", "!=", "==", ">", "<")


def _resolve_jsonpath(path: str, data: Dict[str, Any]) -> Any:
    """Resolve a JSONPath expression against *data*, with graceful fallback.

    Tries jsonpath_ng first; on ImportError falls back to dotted-key
    navigation so the feature works without the optional dependency.
    """
    try:
        from jsonpath_ng import parse as jp_parse  # type: ignore[import]

        matches = jp_parse(path).find(data)
        if not matches:
            return None
        return matches[0].value
    except ImportError:
        logger.warning(
            "jsonpath_ng not installed; using simple dotted-key fallback for %r", path
        )
        # Strip leading $. or $[ prefix for the fallback
        stripped = path.lstrip("$").lstrip(".").lstrip("[").rstrip("]").strip("'\"")
        obj: Any = data
        for part in stripped.split("."):
            if not isinstance(obj, dict):
                return None
            obj = obj.get(part)
        return obj


def _evaluate_jsonpath_expr(expr: str, ctx: DAGExecutionContext) -> bool:
    """Evaluate a JSONPath comparison expression of the form ``$.x.y OP value``."""
    op_used = None
    for op in _JSONPATH_OPS:
        if op in expr:
            op_used = op
            break
    if op_used is None:
        logger.warning(
            "JSONPath expression %r has no comparison operator; defaulting False", expr
        )
        return False

    lhs_raw, rhs_raw = expr.split(op_used, 1)
    lhs_path = lhs_raw.strip()
    rhs_raw = rhs_raw.strip()

    lhs_value = _resolve_jsonpath(lhs_path, ctx.step_results)

    # Coerce rhs to a comparable Python type
    try:
        rhs: Any = int(rhs_raw)
    except ValueError:
        try:
            rhs = float(rhs_raw)
        except ValueError:
            rhs = rhs_raw.strip('"').strip("'")

    try:
        if op_used == "==":
            return lhs_value == rhs
        if op_used == "!=":
            return lhs_value != rhs
        if op_used == ">":
            return lhs_value > rhs  # type: ignore[operator]
        if op_used == "<":
            return lhs_value < rhs  # type: ignore[operator]
        if op_used == ">=":
            return lhs_value >= rhs  # type: ignore[operator]
        if op_used == "<=":
            return lhs_value <= rhs  # type: ignore[operator]
    except TypeError as exc:
        logger.warning(
            "JSONPath comparison failed for %r: %s; defaulting False", expr, exc
        )
    return False


def _evaluate_condition(node: DAGNode, ctx: DAGExecutionContext) -> bool:
    """
    Evaluate a condition expression stored in *node.data["condition"]*.

    Supports two expression styles:

    1. **JSONPath comparison** — expression starts with ``$.`` or ``$[``:
       ``$.step1.status == "success"`` — parsed into lhs/op/rhs and the
       lhs path is resolved via jsonpath_ng (or dotted-key fallback).

    2. **Python eval** — any other expression is evaluated against a
       restricted namespace containing ``results``, ``True``, ``False``,
       ``len``, ``str``, ``int``, ``float``, ``bool``.

    Returns True if the condition is truthy, False otherwise.  On any
    evaluation error the condition defaults to False and a warning is
    logged.

    Security note: eval is intentionally sandboxed to a read-only namespace
    and cannot import modules or access builtins beyond the allowed set.
    """
    expr: str = node.data.get("condition", "")
    if not expr:
        logger.warning(
            "Condition node %s has empty expression; defaulting False", node.node_id
        )
        return False

    if expr.startswith("$.") or expr.startswith("$["):
        result = _evaluate_jsonpath_expr(expr, ctx)
        logger.debug(
            "Condition node %s (JSONPath): expr=%r → %s", node.node_id, expr, result
        )
        return result

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
        result = eval(expr, safe_globals, safe_locals)  # noqa: S307  # nosec B307
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


def _evaluate_switch(node: DAGNode, ctx: DAGExecutionContext) -> str:
    """
    Resolve the switch discriminant for *node* and return it as a string.

    Reads ``node.data["switch_on"]`` — a variable reference compatible with
    the condition node's safe eval namespace (e.g.
    ``results["step1"]["output"]`` or a bare key name).  Returns
    ``"default"`` on any error so routing always has a valid case to match.
    """
    switch_on: str = node.data.get("switch_on", "")
    if not switch_on:
        logger.warning(
            "Switch node %s has no 'switch_on' key; routing to default", node.node_id
        )
        return "default"

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
        value = eval(switch_on, safe_globals, safe_locals)  # noqa: S307  # nosec B307
        case_value = str(value)
        logger.debug(
            "Switch node %s: switch_on=%r → %r", node.node_id, switch_on, case_value
        )
        return case_value
    except Exception as exc:
        logger.warning(
            "Switch node %s: switch_on=%r raised %s; routing to default",
            node.node_id,
            switch_on,
            exc,
        )
        return "default"


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

    def __init__(
        self,
        step_executor_callback: StepExecutorCallback,
        criteria_evaluator: SuccessCriteriaEvaluator | None = None,
    ) -> None:
        self._execute_step = step_executor_callback
        self._criteria_evaluator = criteria_evaluator

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    async def execute(
        self,
        dag: WorkflowDAG,
        workflow_id: str,
        context: Dict[str, Any] | None = None,
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
            ctx.status = TaskStatus.FAILED.value
            ctx.error = f"Cycle detected in workflow graph: {' → '.join(cycle)}"
            return ctx

        ctx = DAGExecutionContext(workflow_id=workflow_id)
        roots = dag.root_nodes()
        if not roots:
            logger.error("Workflow %s DAG has no root nodes", workflow_id)
            ctx.status = TaskStatus.FAILED.value
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
            await self._visit_nodes(
                [r.node_id for r in roots], dag, ctx, visited, context or {}
            )
        except Exception as exc:
            logger.error("Workflow %s DAG execution raised: %s", workflow_id, exc)
            ctx.status = TaskStatus.FAILED.value
            ctx.error = str(exc)
            return ctx

        if ctx.error is None:
            ctx.status = TaskStatus.COMPLETED.value
        else:
            ctx.status = TaskStatus.PARTIALLY_COMPLETED.value

        if self._criteria_evaluator and context and context.get("structured_criteria"):
            eval_result = await self._criteria_evaluator.evaluate(
                context["structured_criteria"], ctx.step_results
            )
            ctx.criteria_evaluation = eval_result.to_dict()

        logger.info(
            "Workflow %s DAG execution finished: status=%s", workflow_id, ctx.status
        )
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
            next_ids = self._get_next_node_ids(
                node, dag, condition_result=None, skipped=True
            )
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

        if node.node_type == NodeType.SWITCH:
            return await self._execute_switch_node(node, dag, ctx)

        # Issue #3406: distributed_shell has its own fan-out executor
        if node.node_type == NodeType.DISTRIBUTED_SHELL:
            try:
                result = await execute_distributed_shell(node, ctx)
            except Exception as exc:
                logger.error("distributed_shell node %s raised: %s", node.node_id, exc)
                result = {"success": False, "error": str(exc), "node_id": node.node_id}
            ctx.step_results[node.node_id] = result
            return [e.target for e in dag.successors(node.node_id)]

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

        logger.info("Condition node %s evaluated to %s", node.node_id, condition_result)

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

    async def _execute_switch_node(
        self,
        node: DAGNode,
        dag: WorkflowDAG,
        ctx: DAGExecutionContext,
    ) -> List[str]:
        """
        Route execution to the edge whose label matches the switch discriminant.

        Edge matching order:
        1. Edges with ``label == case_value`` (exact string match).
        2. If none, edges with ``label == "default"`` (catch-all).
        3. If still none, log a warning and fall through to all unconditional
           edges (``label is None``) so the workflow is never silently stuck.

        All labeled edges whose label was not selected are passed to
        ``_mark_descendants_skipped`` for branch pruning.
        """
        case_value = _evaluate_switch(node, ctx)
        ctx.step_results[node.node_id] = {
            "success": True,
            "switch_on": node.data.get("switch_on", ""),
            "case_value": case_value,
            "node_id": node.node_id,
        }

        logger.info("Switch node %s evaluated to case %r", node.node_id, case_value)

        labeled_by_case: Dict[str, List[str]] = {}
        unconditional_targets: List[str] = []

        for edge in dag.successors(node.node_id):
            if edge.label is None:
                unconditional_targets.append(edge.target)
            else:
                key = str(edge.label)
                labeled_by_case.setdefault(key, []).append(edge.target)

        taken_targets = labeled_by_case.get(case_value)
        if taken_targets is None:
            taken_targets = labeled_by_case.get("default")
        if taken_targets is None:
            logger.warning(
                "Switch node %s: no edge for case %r and no default; using unconditional targets",
                node.node_id,
                case_value,
            )
            return unconditional_targets

        pruned_targets: List[str] = []
        for key, targets in labeled_by_case.items():
            if targets is not taken_targets:
                pruned_targets.extend(targets)

        self._mark_descendants_skipped(pruned_targets, dag, ctx)
        return taken_targets + unconditional_targets

    def _mark_descendants_skipped(
        self,
        node_ids: List[str],
        dag: WorkflowDAG,
        ctx: DAGExecutionContext,
    ) -> None:
        """BFS-mark descendants as skipped, respecting diamond joins (#7010 cluster 1).

        The initial *node_ids* (immediate not-taken-branch targets) are
        always marked. Their descendants are marked **only if all their
        predecessors are also skipped** — otherwise the descendant is a
        join node where another live path will reach it (e.g. the diamond
        ``cond → (true|false) → end``: ``end`` must execute via
        ``true_branch`` even when ``false_branch`` is pruned).
        """
        initial = set(node_ids)
        queue = list(node_ids)
        while queue:
            nid = queue.pop(0)
            if nid in ctx.skipped_nodes:
                continue
            if nid not in initial:
                # Join check: skip the descendant only if every incoming edge
                # comes from a node that's also skipped. A live predecessor
                # means the descendant will be reached via that path.
                preds = dag.predecessors(nid)
                if not all(p in ctx.skipped_nodes for p in preds):
                    continue
            ctx.skipped_nodes.add(nid)
            for edge in dag.successors(nid):
                queue.append(edge.target)

    def _get_next_node_ids(
        self,
        node: DAGNode,
        dag: WorkflowDAG,
        condition_result: bool | None,
        skipped: bool = False,
    ) -> List[str]:
        """
        Return successor node IDs for a skipped node.

        Skipped nodes propagate the skip to all successors so downstream
        nodes are also pruned.
        """
        return [e.target for e in dag.successors(node.node_id)]


# ---------------------------------------------------------------------------
# Issue #3406: Distributed shell fan-out
# ---------------------------------------------------------------------------


def _build_slm_ssl_context() -> ssl.SSLContext:
    """Create SSL context for SLM HTTP calls (#6702: delegates to shared tls.py)."""
    from autobot_shared.tls import get_internal_tls_context

    return get_internal_tls_context()


async def _execute_on_node(
    slm_url: str,
    auth_token: str,
    node_id: str,
    script: str,
    language: str,
    timeout: int,
) -> Dict[str, Any]:
    """POST /nodes/{node_id}/execute on the SLM backend.

    Returns a per-node result dict compatible with DAGExecutionContext.
    """
    import aiohttp  # lazy import — not available in all environments

    url = f"{slm_url}/api/nodes/{node_id}/execute"
    payload = {"command": script, "language": language, "timeout": timeout}
    headers = {"Authorization": f"Bearer {auth_token}"}
    ssl_ctx = _build_slm_ssl_context()
    connector = aiohttp.TCPConnector(ssl=ssl_ctx)

    try:
        async with aiohttp.ClientSession(
            headers=headers, connector=connector
        ) as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=timeout + 30)
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "node_id": node_id,
                        "exit_code": data.get("exit_code", -1),
                        "stdout": data.get("stdout", ""),
                        "stderr": data.get("stderr", ""),
                        "duration_ms": data.get("duration_ms", 0),
                        "success": data.get("exit_code", -1) == 0,
                    }
                body = await resp.text()
                return {
                    "node_id": node_id,
                    "exit_code": -1,
                    "stdout": "",
                    "stderr": f"HTTP {resp.status}: {body[:500]}",
                    "duration_ms": 0,
                    "success": False,
                }
    except Exception as exc:
        logger.error("distributed_shell: node %s raised %s", node_id, exc)
        return {
            "node_id": node_id,
            "exit_code": -1,
            "stdout": "",
            "stderr": str(exc),
            "duration_ms": 0,
            "success": False,
        }


async def execute_distributed_shell(
    node: DAGNode, ctx: DAGExecutionContext
) -> Dict[str, Any]:
    """Fan out *node.data* shell script to all listed fleet nodes in parallel.

    Expected ``node.data`` schema::

        {
            "nodes":    ["node-id-1", "node-id-2", ...],
            "script":   "echo hello",
            "language": "bash",   # optional, default "bash"
            "timeout":  300,      # optional, default 300
        }

    Returns a result dict whose ``success`` is True only when all nodes
    return exit_code 0.  Per-node details are in ``node_results``.
    """
    slm_url = config.slm_url.rstrip("/")
    auth_token = config.slm_auth_token
    if not slm_url:
        return {
            "success": False,
            "error": "SLM_URL not configured for distributed_shell",
            "node_results": [],
            "node_id": node.node_id,
        }

    target_nodes: List[str] = node.data.get("nodes", [])
    script: str = node.data.get("script", "")
    language: str = node.data.get("language", "bash")
    timeout: int = int(node.data.get("timeout", 300))

    if not target_nodes:
        return {
            "success": False,
            "error": "distributed_shell: 'nodes' list is empty",
            "node_results": [],
            "node_id": node.node_id,
        }
    if not script:
        return {
            "success": False,
            "error": "distributed_shell: 'script' is required",
            "node_results": [],
            "node_id": node.node_id,
        }

    logger.info(
        "distributed_shell %s: fanning out to %d node(s): %s",
        node.node_id,
        len(target_nodes),
        target_nodes,
    )
    t0 = time.monotonic()

    results: List[Dict[str, Any]] = await asyncio.gather(
        *(
            _execute_on_node(slm_url, auth_token, nid, script, language, timeout)
            for nid in target_nodes
        )
    )

    total_ms = int((time.monotonic() - t0) * 1000)
    all_ok = all(r.get("success", False) for r in results)
    failed = [r["node_id"] for r in results if not r.get("success", False)]

    if not all_ok:
        logger.warning(
            "distributed_shell %s: %d/%d node(s) failed: %s",
            node.node_id,
            len(failed),
            len(target_nodes),
            failed,
        )

    return {
        "success": all_ok,
        "node_id": node.node_id,
        "node_results": results,
        "total_duration_ms": total_ms,
        "failed_nodes": failed,
        "error": None if all_ok else f"Nodes failed: {failed}",
    }


# ---------------------------------------------------------------------------
# Convenience helpers used by WorkflowExecutor integration
# ---------------------------------------------------------------------------


def workflow_has_condition_nodes(
    steps: List[Dict[str, Any]], edges: List[Dict[str, Any]]
) -> bool:
    """
    Return True when the step/edge list describes a branching workflow.

    Used by WorkflowExecutor to decide whether to engage DAGExecutor.
    """
    if not edges:
        return False
    node_types = {s.get("type", "step") for s in steps}
    return "condition" in node_types


def build_dag(steps: List[Dict[str, Any]], edges: List[Dict[str, Any]]) -> WorkflowDAG:
    """Construct a WorkflowDAG from workflow API payloads.

    #7010 cluster 3: tolerates both edge shapes —
      - Canonical: ``{"source": ..., "target": ..., "label": ...}``
      - API-facing: ``{"from": ..., "to": ..., "condition": "true"|"false"|None}``

    The API shape is what reaches /api/workflow-automation/execute via the
    #3172 payload contract; translating here lets callers pass the raw
    payload without an explicit adapter.
    """

    def _condition_to_label(value: Any) -> bool | None:
        if value is None or isinstance(value, bool):
            return value
        if isinstance(value, str):
            lower = value.lower()
            if lower in ("true", "yes"):
                return True
            if lower in ("false", "no"):
                return False
        return None

    normalized: List[Dict[str, Any]] = []
    for raw in edges:
        if "source" in raw and "target" in raw:
            normalized.append(raw)
            continue
        if "from" in raw and "to" in raw:
            label = _condition_to_label(raw.get("condition"))
            normalized.append(
                {"source": raw["from"], "target": raw["to"], "label": label}
            )
            continue
        # Malformed entry — let WorkflowDAG's warn-and-skip handle it.
        normalized.append(raw)

    return WorkflowDAG(steps, normalized)
