# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
DAG-to-AutoBotGraph adapter.

Issue #3228: migrate the DAG workflow executor to use the unified
``AutoBotGraph`` / ``GraphRunner`` engine so checkpoint and step-event
logic is shared rather than duplicated.
Issue #6826: #3228 was closed prematurely; the migration is ongoing.
Executor fragmentation scope: this adapter is the bridge layer intended
to replace direct ``DAGExecutor`` usage in production once parallel
fan-out support is complete (tracked in #6826).

This module provides ``build_dag_graph`` which converts a ``WorkflowDAG``
into an ``AutoBotGraph``.  Each DAG node becomes a graph node whose
``run(state)`` implementation delegates to ``DAGExecutor._execute_node``
semantics.  The resulting ``CompiledGraph`` can be executed via
``GraphRunner`` just like any other ``AutoBotGraph``.

``DAGGraphExecutor`` is the public integration class that replaces the
``DAGExecutor`` call-site in ``WorkflowExecutor._execute_dag_workflow``
while preserving the same result shape (``DAGExecutionContext``).

State shape
-----------
The intermediate graph state used during DAG execution is a plain dict
with the following keys that map to ``DAGExecutionContext`` fields:

    dag_ctx       : DAGExecutionContext (mutable, pre-populated by runner)
    dag           : WorkflowDAG (read-only)
    step_executor : StepExecutorCallback (read-only)
    visited       : set[str]   — nodes already executed (join deduplication)
    extra_context : dict       — opaque caller context forwarded to each step

After the graph finishes, the caller extracts ``dag_ctx`` from the final
state and converts it back to the legacy execution_context dict shape.
"""

from __future__ import annotations

from typing import Any, Dict, Set

from autobot_shared.logging_manager import get_logger

from .dag_executor import (
    DAGExecutionContext,
    DAGNode,
    NodeType,
    StepExecutorCallback,
    WorkflowDAG,
    _evaluate_condition,
    execute_distributed_shell,
)
from .graph_runner import (
    END,
    AutoBotGraph,
    CompiledGraph,
    GraphRunner,
    NodeRetryConfig,
    StepEventEmitter,
)

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Node wrappers
# ---------------------------------------------------------------------------


def _make_dag_node_fn(
    dag_node: DAGNode,
    dag: WorkflowDAG,
) -> Any:
    """Return an async node function for *dag_node* compatible with GraphRunner.

    The function signature is ``async (state, **kwargs) -> partial_state``.
    It reads ``state["dag_ctx"]`` and ``state["step_executor"]``, executes the
    DAG node, and returns a partial state update that mutates ``dag_ctx`` via
    its reference (dicts are passed by reference so in-place mutation is safe).
    """

    async def _run(state: Dict[str, Any], **kwargs: Any) -> Dict[str, Any]:
        ctx: DAGExecutionContext = state["dag_ctx"]
        step_executor: StepExecutorCallback = state["step_executor"]

        # Mirror DAGExecutor._execute_node logic.
        if dag_node.node_type == NodeType.CONDITION:
            condition_result = _evaluate_condition(dag_node, ctx)
            ctx.branches_taken[dag_node.node_id] = condition_result
            ctx.step_results[dag_node.node_id] = {
                "success": True,
                "condition": dag_node.data.get("condition", ""),
                "result": condition_result,
                "node_id": dag_node.node_id,
            }
            logger.info(
                "DAGGraph condition node %s evaluated to %s",
                dag_node.node_id,
                condition_result,
            )
            # Mark pruned branch descendants as skipped.
            true_targets = [e.target for e in dag.successors(dag_node.node_id) if e.label is True]
            false_targets = [e.target for e in dag.successors(dag_node.node_id) if e.label is False]
            pruned = false_targets if condition_result else true_targets
            _mark_descendants_skipped(pruned, dag, ctx)
            return {}  # dag_ctx mutated in-place

        if dag_node.node_type == NodeType.DISTRIBUTED_SHELL:
            try:
                result = await execute_distributed_shell(dag_node, ctx)
            except Exception as exc:
                logger.error(
                    "DAGGraph distributed_shell node %s raised: %s",
                    dag_node.node_id,
                    exc,
                )
                result = {
                    "success": False,
                    "error": str(exc),
                    "node_id": dag_node.node_id,
                }
            ctx.step_results[dag_node.node_id] = result
            return {}

        # Regular STEP / PARALLEL node.
        try:
            result = await step_executor(dag_node, ctx)
        except Exception as exc:
            logger.error("DAGGraph step node %s raised: %s", dag_node.node_id, exc)
            result = {
                "success": False,
                "error": str(exc),
                "node_id": dag_node.node_id,
            }

        ctx.step_results[dag_node.node_id] = result
        agent_id = dag_node.data.get("assigned_agent") or result.get("agent_id")
        if agent_id:
            ctx.agents_involved.add(str(agent_id))

        return {}  # dag_ctx mutated in-place

    return _run


def _mark_descendants_skipped(
    node_ids: list[str],
    dag: WorkflowDAG,
    ctx: DAGExecutionContext,
) -> None:
    """BFS-mark all descendants of *node_ids* as skipped (mirrors DAGExecutor)."""
    queue = list(node_ids)
    while queue:
        nid = queue.pop(0)
        if nid in ctx.skipped_nodes:
            continue
        ctx.skipped_nodes.add(nid)
        for edge in dag.successors(nid):
            queue.append(edge.target)


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_dag_graph(
    dag: WorkflowDAG,
    step_executor: StepExecutorCallback,
    retry_config: NodeRetryConfig | None = None,
) -> CompiledGraph:
    """Convert *dag* into a ``CompiledGraph`` executable by ``GraphRunner``.

    Args:
        dag:           The workflow DAG to convert.
        step_executor: Async callback ``(node, ctx) -> result_dict`` used for
                       STEP and PARALLEL nodes (same signature as DAGExecutor).
        retry_config:  Optional per-node retry configuration applied uniformly
                       to all nodes.  Pass ``None`` for no retry (default).

    Returns:
        A compiled graph ready for ``GraphRunner``.

    Raises:
        ValueError: When the DAG has no root nodes (empty graph).
    """
    roots = dag.root_nodes()
    if not roots:
        raise ValueError("DAG has no root nodes — cannot build graph.")

    builder: AutoBotGraph[Dict[str, Any]] = AutoBotGraph()
    effective_retry = retry_config or NodeRetryConfig()

    # Topological order via BFS from roots.
    ordered: list[str] = []
    seen: Set[str] = set()
    queue = [r.node_id for r in roots]
    while queue:
        nid = queue.pop(0)
        if nid in seen:
            continue
        seen.add(nid)
        ordered.append(nid)
        for edge in dag.successors(nid):
            queue.append(edge.target)

    # Register a node function for each DAG node.
    for nid in ordered:
        dag_node = dag.nodes[nid]
        fn = _make_dag_node_fn(dag_node, dag)
        builder.add_node(nid, fn, retry=effective_retry)

    # Wire edges.  For CONDITION nodes, the router reads ctx.branches_taken
    # to return the correct branch (already resolved during node execution).
    for nid in ordered:
        dag_node = dag.nodes[nid]
        successors = dag.successors(nid)

        if not successors:
            # Leaf node — unconditional edge to END.
            builder.add_edge(nid, END)
            continue

        if dag_node.node_type == NodeType.CONDITION:
            # Conditional edges: branch is resolved *after* node execution
            # since the node populates ctx.branches_taken.
            true_targets = [e.target for e in successors if e.label is True]
            false_targets = [e.target for e in successors if e.label is False]
            unconditional = [e.target for e in successors if e.label is None]

            condition_node_id = nid  # capture for closure

            def _make_condition_router(
                true_t: list[str],
                false_t: list[str],
                unconditional_t: list[str],
                cnode_id: str,
            ) -> Any:
                def _router(state: Dict[str, Any]) -> str:
                    ctx: DAGExecutionContext = state["dag_ctx"]
                    branch_taken = ctx.branches_taken.get(cnode_id, False)
                    candidates = (true_t if branch_taken else false_t) + unconditional_t
                    if not candidates:
                        return END
                    # Return first non-skipped candidate.
                    for target in candidates:
                        if target not in ctx.skipped_nodes:
                            return target
                    return END

                return _router

            builder.add_conditional_edges(
                nid,
                _make_condition_router(true_targets, false_targets, unconditional, condition_node_id),
            )
        else:
            # Non-condition node: unconditional edges to all successors.
            # If multiple successors exist, they run sequentially through the
            # linear GraphRunner.  True parallel fan-out can be achieved by
            # adding a PARALLEL wrapper node in future work.
            if len(successors) == 1:
                target = successors[0].target
                builder.add_edge(nid, target if target in dag.nodes else END)
            else:
                # Multiple successors: chain first unconditional, then the rest.
                # This linearises the fan-out; for true concurrency use DAGExecutor
                # directly or a future parallel node type.
                for edge in successors:
                    target = edge.target if edge.target in dag.nodes else END
                    builder.add_edge(nid, target)
                    break  # GraphRunner follows the first matching edge

    # Set entry point to first root.
    first_root = roots[0].node_id
    builder.set_entry_point(first_root)

    return builder.compile()


# ---------------------------------------------------------------------------
# DAGGraphExecutor (integration class)
# ---------------------------------------------------------------------------


class DAGGraphExecutor:
    """Drop-in replacement for ``DAGExecutor`` that uses ``GraphRunner`` internally.

    ``WorkflowExecutor._execute_dag_workflow`` currently instantiates
    ``DAGExecutor`` and calls ``executor.execute(dag, workflow_id, context)``.
    Replacing that with ``DAGGraphExecutor`` keeps the same call contract while
    delegating execution to the unified ``GraphRunner`` engine.

    Differences from ``DAGExecutor``:
    - Checkpoint save/load handled by ``GraphRunner`` (not duplicated here).
    - Step events emitted via ``StepEventEmitter`` (pluggable sinks).
    - Retry configured per-node via ``NodeRetryConfig``.

    Limitation (known):
    - True parallel fan-out (multiple successors executed concurrently) is
      linearised in this implementation.  The original ``DAGExecutor`` uses
      ``asyncio.gather`` for independent branches.  Full parallel fan-out
      support is tracked as a follow-up enhancement in issue #6826.
    """

    def __init__(
        self,
        step_executor_callback: StepExecutorCallback,
        emitter: StepEventEmitter | None = None,
        retry_config: NodeRetryConfig | None = None,
        enable_checkpoints: bool = True,
    ) -> None:
        self._step_executor = step_executor_callback
        self._emitter = emitter or StepEventEmitter()
        self._retry_config = retry_config
        self._enable_checkpoints = enable_checkpoints

    async def execute(
        self,
        dag: WorkflowDAG,
        workflow_id: str,
        context: Dict[str, Any] | None = None,
    ) -> DAGExecutionContext:
        """Execute *dag* using ``GraphRunner``.

        Args:
            dag:         The workflow graph to execute.
            workflow_id: Identifier for logging and checkpointing.
            context:     Optional extra context forwarded to step executor.

        Returns:
            Populated ``DAGExecutionContext`` after all reachable nodes finish.
        """
        from constants.status_enums import TaskStatus

        cycle = dag.detect_cycle()
        if cycle:
            logger.error(
                "DAGGraphExecutor %s: cycle detected (%s); aborting",
                workflow_id,
                " → ".join(cycle),
            )
            ctx = DAGExecutionContext(workflow_id=workflow_id)
            ctx.status = TaskStatus.FAILED.value
            ctx.error = f"Cycle detected in workflow graph: {' → '.join(cycle)}"
            return ctx

        roots = dag.root_nodes()
        if not roots:
            logger.error("DAGGraphExecutor %s: DAG has no root nodes", workflow_id)
            ctx = DAGExecutionContext(workflow_id=workflow_id)
            ctx.status = TaskStatus.FAILED.value
            ctx.error = "DAG has no root nodes"
            return ctx

        ctx = DAGExecutionContext(workflow_id=workflow_id)

        try:
            compiled = build_dag_graph(dag, self._step_executor, self._retry_config)
        except ValueError as exc:
            logger.error("DAGGraphExecutor %s: graph build failed: %s", workflow_id, exc)
            ctx.status = TaskStatus.FAILED.value
            ctx.error = str(exc)
            return ctx

        initial_state: Dict[str, Any] = {
            "dag_ctx": ctx,
            "dag": dag,
            "step_executor": self._step_executor,
            "visited": set(),
            "extra_context": context or {},
        }

        runner = GraphRunner(
            graph=compiled,
            graph_id=workflow_id,
            emitter=self._emitter,
            enable_checkpoints=self._enable_checkpoints,
        )

        logger.info(
            "DAGGraphExecutor %s: starting execution from %d root node(s): %s",
            workflow_id,
            len(roots),
            [r.node_id for r in roots],
        )

        try:
            await runner.run(initial_state)
        except Exception as exc:
            logger.error("DAGGraphExecutor %s: execution raised: %s", workflow_id, exc)
            ctx.status = TaskStatus.FAILED.value
            ctx.error = str(exc)
            return ctx

        ctx.status = TaskStatus.COMPLETED.value if ctx.error is None else TaskStatus.PARTIALLY_COMPLETED.value
        logger.info(
            "DAGGraphExecutor %s: finished: status=%s",
            workflow_id,
            ctx.status,
        )
        return ctx
