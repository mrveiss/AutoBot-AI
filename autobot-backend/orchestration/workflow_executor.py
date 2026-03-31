# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Executor

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains workflow execution, step coordination, and agent interaction handling.

Issue #2168: Added circuit breaker + retry decorators to step execution.
Issue #2172: Added parallel execution for independent workflow steps.
Issue #2140: DAG-based execution with condition evaluation and branch routing.
Issue #2154: Resume-from-failure with per-step error configs and checkpoints.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from circuit_breaker import circuit_breaker_async
from constants.threshold_constants import (
    CircuitBreakerDefaults,
    RetryConfig,
    TimingConstants,
)
from retry_mechanism import RetryStrategy, retry_async

from .dag_executor import DAGExecutor, DAGExecutionContext, DAGNode, build_dag, workflow_has_condition_nodes
from .error_handler import (
    BackoffStrategy,
    ErrorHandlerResult,
    StepErrorAction,
    StepErrorConfig,
    StepErrorHandler,
    WorkflowCheckpointManager,
)
from .types import AgentInteraction, AgentProfile

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """
    Executes workflows with coordinated agent management.

    Handles:
    - Step execution with dependency management
    - Agent reservation and release
    - Performance metric updates
    - Agent interaction recording
    - Per-step error handling (retry, skip, fallback, pause, abort) (#2154)
    - Checkpoint-based resume from the last successful step (#2154)
    """

    def __init__(
        self,
        agent_registry: Dict[str, AgentProfile],
        agent_interactions: List[AgentInteraction],
        reserve_agent_callback: Callable[[str], None],
        release_agent_callback: Callable[[str], None],
        update_performance_callback: Callable[[str, bool, float], None],
        checkpoint_manager: Optional[WorkflowCheckpointManager] = None,
        error_handler: Optional[StepErrorHandler] = None,
    ):
        """
        Initialize the workflow executor.

        Args:
            agent_registry: Registry of available agents
            agent_interactions: List to track agent interactions
            reserve_agent_callback: Function to reserve an agent
            release_agent_callback: Function to release an agent
            update_performance_callback: Function to update agent performance
            checkpoint_manager: Optional checkpoint manager for resume-from-failure.
                Defaults to a new WorkflowCheckpointManager when not provided.
            error_handler: Optional per-step error handler.
                Defaults to a new StepErrorHandler when not provided.
        """
        self.agent_registry = agent_registry
        self.agent_interactions = agent_interactions
        self._reserve_agent = reserve_agent_callback
        self._release_agent = release_agent_callback
        self._update_performance = update_performance_callback
        self._checkpoint_manager = checkpoint_manager or WorkflowCheckpointManager()
        self._error_handler = error_handler or StepErrorHandler()

    def _group_steps_by_dependency(
        self, steps: List[Dict[str, Any]]
    ) -> List[List[Dict[str, Any]]]:
        """
        Group workflow steps for parallel execution.

        Steps with no unmet dependencies form a parallel group. Each group
        runs concurrently; groups are ordered sequentially. Mirrors the
        DependencyAnalyzer.get_parallel_groups pattern from
        tools/parallel/analyzer.py. Issue #2172.

        Args:
            steps: List of workflow steps with optional 'dependencies' field

        Returns:
            Ordered list of groups; steps in each group run concurrently
        """
        step_map = {s["id"]: s for s in steps}
        remaining = [s["id"] for s in steps]
        completed: set = set()
        groups: List[List[Dict[str, Any]]] = []

        while remaining:
            ready_ids = [
                sid
                for sid in remaining
                if all(
                    dep in completed for dep in step_map[sid].get("dependencies", [])
                )
            ]

            if not ready_ids:
                logger.error(
                    "Circular dependency in workflow steps; falling back to sequential"
                )
                for sid in remaining:
                    groups.append([step_map[sid]])
                break

            groups.append([step_map[sid] for sid in ready_ids])
            for sid in ready_ids:
                remaining.remove(sid)
            completed.update(ready_ids)

        return groups

    def _determine_workflow_status(
        self, steps: List[Dict[str, Any]], execution_context: Dict[str, Any]
    ) -> None:
        """Determine overall workflow status from step results (Issue #398: extracted)."""
        successful_steps = sum(1 for step in steps if step.get("status") == "completed")
        total_steps = len(steps)

        if successful_steps == total_steps:
            execution_context["status"] = "completed"
        elif successful_steps > 0:
            execution_context["status"] = "partially_completed"
        else:
            execution_context["status"] = "failed"

        execution_context["success_rate"] = (
            successful_steps / total_steps if total_steps > 0 else 0
        )
        execution_context["agents_involved"] = list(
            execution_context["agents_involved"]
        )

    async def _execute_step_with_agent(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
        checkpoints: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute a single workflow step with agent management.

        Issue #398: extracted.
        Issue #2154: Added checkpoint skip, per-step error config, and retry loop.

        Args:
            step: Step definition dict.
            execution_context: Shared mutable execution state.
            context: Workflow-level context passed down from the caller.
            checkpoints: Pre-loaded checkpoint map for this execution (step_id ->
                StepCheckpoint).  When a step_id is present the step is skipped
                and its previous output is replayed.
        """
        step_id = step["id"]
        step_start_time = time.time()

        # --- Resume: skip already-completed steps (#2154) ---
        if checkpoints and step_id in checkpoints:
            cp = checkpoints[step_id]
            logger.info("Step %s: replaying checkpoint (skipping re-execution)", step_id)
            step["status"] = "completed"
            step["result"] = cp.output
            execution_context["step_results"][step_id] = cp.output
            return

        agent_id = step.get("assigned_agent")
        error_config: StepErrorConfig = step.get("error_config") or StepErrorConfig()
        execution_id: str = execution_context.get("workflow_id", "unknown")

        if agent_id:
            self._reserve_agent(agent_id)

        try:
            step_result = await self._execute_step_with_error_handling(
                step, execution_context, context, error_config, execution_id
            )
            step["status"] = "completed" if step_result.get("success") else "failed"
            step["execution_time"] = time.time() - step_start_time
            step["result"] = step_result
            execution_context["step_results"][step_id] = step_result

            # Persist checkpoint on success (#2154)
            if step_result.get("success"):
                self._checkpoint_manager.save_checkpoint(
                    execution_id, step_id, step_result
                )

            if agent_id:
                execution_context["agents_involved"].add(agent_id)
                self._update_performance(
                    agent_id,
                    step_result.get("success", False),
                    time.time() - step_start_time,
                )
        finally:
            if agent_id:
                self._release_agent(agent_id)

    async def _execute_step_with_error_handling(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
        error_config: StepErrorConfig,
        execution_id: str,
    ) -> Dict[str, Any]:
        """Run one step, consulting the StepErrorConfig on each failure.

        Implements the retry loop for RETRY action so that the circuit-breaker
        decorator on _execute_coordinated_step can still fire on individual
        attempts.  Non-retryable actions (SKIP, FALLBACK, PAUSE, ABORT) exit
        after the first failure.

        Issue #2154.

        Args:
            step: Step definition dict.
            execution_context: Shared mutable execution state.
            context: Workflow-level context.
            error_config: Per-step error handling policy.
            execution_id: Workflow execution id (used for pause/abort logging).

        Returns:
            Step result dict with at least a ``"success"`` key.
        """
        step_id = step["id"]
        attempt = 0
        last_error: Optional[Exception] = None

        while True:
            attempt += 1
            try:
                result = await self._execute_coordinated_step(
                    step, execution_context, context
                )
                return result
            except Exception as exc:
                last_error = exc
                handler_result: ErrorHandlerResult = await self._error_handler.handle_error(
                    step_id, exc, error_config, attempt
                )

                if handler_result.action == StepErrorAction.SKIP:
                    return {
                        "success": False,
                        "skipped": True,
                        "error": str(exc),
                        "step_id": step_id,
                    }

                if handler_result.action == StepErrorAction.FALLBACK:
                    execution_context["fallback_step_id"] = handler_result.fallback_step_id
                    return {
                        "success": False,
                        "fallback": handler_result.fallback_step_id,
                        "error": str(exc),
                        "step_id": step_id,
                    }

                if handler_result.action == StepErrorAction.PAUSE:
                    execution_context["status"] = "paused"
                    logger.warning(
                        "Workflow %s paused at step %s", execution_id, step_id
                    )
                    return {
                        "success": False,
                        "paused": True,
                        "error": str(exc),
                        "step_id": step_id,
                    }

                if not handler_result.should_continue:
                    # ABORT or RETRY exhausted
                    return {
                        "success": False,
                        "error": handler_result.error_message or str(exc),
                        "step_id": step_id,
                    }

                # RETRY: handler already slept; loop back for the next attempt

    async def execute_coordinated_workflow(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
        edges: Optional[List[Dict[str, Any]]] = None,
        execution_id: Optional[str] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute workflow with coordinated agent management.

        When the step list contains condition nodes (or explicit edges are
        provided), delegates to DAGExecutor for branch-aware execution.
        Plain linear workflows continue to use the existing dependency-group
        path for full backward compatibility.  Issue #2140.

        Issue #2154: Added ``resume`` and ``execution_id`` parameters.  When
        ``resume=True`` the checkpoint manager is queried for already-completed
        steps; those steps are replayed from their saved outputs without being
        re-executed.  On successful completion all checkpoints are cleared.

        Args:
            workflow_id: Workflow identifier
            steps: List of enhanced workflow steps
            context: Workflow context
            edges: Optional list of DAG edge dicts.  When provided together
                   with condition-type steps, DAG execution is used.
            execution_id: Stable identifier for this execution run.  Defaults
                to ``workflow_id`` when not supplied.  Used as the checkpoint
                namespace so retries share the same checkpoint bucket.
            resume: When True, load existing checkpoints and skip completed steps.

        Returns:
            Execution context with results
        """
        exec_id = execution_id or workflow_id
        effective_edges = edges or []

        # Load checkpoints for resume (#2154)
        checkpoints = self._checkpoint_manager.load_checkpoints(exec_id) if resume else {}
        if checkpoints:
            logger.info(
                "Workflow %s: resuming from %d checkpoint(s): %s",
                exec_id,
                len(checkpoints),
                sorted(checkpoints.keys()),
            )

        if workflow_has_condition_nodes(steps, effective_edges):
            logger.info(
                "Workflow %s: condition nodes detected — using DAG executor (#2140)",
                workflow_id,
            )
            return await self._execute_dag_workflow(workflow_id, steps, effective_edges, context)

        execution_context = {
            "workflow_id": exec_id,
            "agents_involved": set(),
            "interactions": [],
            "step_results": {},
            "status": "in_progress",
        }

        try:
            # Execute steps in dependency-ordered parallel groups (Issue #2172)
            groups = self._group_steps_by_dependency(steps)
            logger.info(
                "Workflow %s: %d steps in %d parallel group(s)",
                workflow_id,
                len(steps),
                len(groups),
            )

            for group in groups:
                await self._execute_step_group(group, execution_context, context, checkpoints)

                # Stop processing if a step paused or aborted the workflow (#2154)
                if execution_context.get("status") in ("paused", "failed"):
                    break

            self._determine_workflow_status(steps, execution_context)

            # Clear checkpoints after a fully successful run (#2154)
            if execution_context.get("status") == "completed":
                self._checkpoint_manager.clear_checkpoints(exec_id)

            return execution_context

        except Exception as e:
            logger.error("Workflow %s execution failed: %s", workflow_id, e)
            execution_context["status"] = "failed"
            execution_context["error"] = str(e)
            return execution_context

    async def _execute_dag_workflow(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a branching workflow via DAGExecutor.

        Builds a WorkflowDAG from *steps* + *edges*, runs it, then
        converts the DAGExecutionContext back into the legacy
        execution_context dict shape so callers stay oblivious to the
        execution path.  Issue #2140.
        """
        dag = build_dag(steps, edges)
        executor = DAGExecutor(step_executor_callback=self._dag_step_adapter)
        dag_ctx = await executor.execute(dag, workflow_id, context)
        return self._dag_ctx_to_execution_context(dag_ctx)

    async def _dag_step_adapter(
        self,
        node: DAGNode,
        dag_ctx: DAGExecutionContext,
    ) -> Dict[str, Any]:
        """
        Bridge between DAGExecutor and the existing _execute_coordinated_step path.

        Converts a DAGNode back into the dict shape expected by
        _execute_coordinated_step, runs it, and returns the result.
        Issue #2140.
        """
        step = dict(node.data)
        step.setdefault("id", node.node_id)

        # Build a minimal execution_context that _execute_step_with_agent can update
        local_ctx: Dict[str, Any] = {
            "workflow_id": dag_ctx.workflow_id,
            "agents_involved": dag_ctx.agents_involved,
            "interactions": dag_ctx.interactions,
            "step_results": dag_ctx.step_results,
            "status": "in_progress",
        }

        await self._execute_step_with_agent(step, local_ctx, {})
        return step.get("result", {"success": step.get("status") == "completed"})

    @staticmethod
    def _dag_ctx_to_execution_context(dag_ctx: DAGExecutionContext) -> Dict[str, Any]:
        """
        Convert a DAGExecutionContext into the legacy execution_context dict shape.

        Issue #2140: Keeps the API surface of execute_coordinated_workflow
        stable regardless of which executor ran.
        """
        return {
            "workflow_id": dag_ctx.workflow_id,
            "agents_involved": list(dag_ctx.agents_involved),
            "interactions": dag_ctx.interactions,
            "step_results": dag_ctx.step_results,
            "status": dag_ctx.status,
            "branches_taken": dag_ctx.branches_taken,
            "skipped_nodes": list(dag_ctx.skipped_nodes),
            **({"error": dag_ctx.error} if dag_ctx.error else {}),
        }

    async def _execute_step_group(
        self,
        group: List[Dict[str, Any]],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
        checkpoints: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Execute a group of steps concurrently using asyncio.gather.

        Steps within a group have no inter-dependencies and are safe to run
        in parallel.  Issue #2172.  Issue #2204: collect results per-step and
        merge after gather to avoid concurrent mutation of shared sets/lists.
        Issue #2154: checkpoints forwarded to _execute_step_with_agent so that
        already-completed steps are skipped.
        """
        if len(group) == 1:
            await self._execute_step_with_agent(group[0], execution_context, context, checkpoints)
            return

        logger.info(
            "Executing %d steps in parallel: %s",
            len(group),
            [s["id"] for s in group],
        )
        # Issue #2204: each step writes to its own isolated context, merged after.
        isolated_contexts = [
            {
                "step_results": {},
                "agents_involved": set(),
                "interactions": [],
                "workflow_id": execution_context.get("workflow_id", ""),
            }
            for _ in group
        ]
        await asyncio.gather(
            *(
                self._execute_step_with_agent(step, iso_ctx, context, checkpoints)
                for step, iso_ctx in zip(group, isolated_contexts)
            )
        )
        for iso_ctx in isolated_contexts:
            execution_context["step_results"].update(iso_ctx["step_results"])
            execution_context["agents_involved"].update(iso_ctx["agents_involved"])
            execution_context["interactions"].extend(iso_ctx["interactions"])
            # Propagate pause/abort status from any parallel step (#2154)
            if iso_ctx.get("status") in ("paused", "failed"):
                execution_context["status"] = iso_ctx["status"]

    def _create_agent_interaction(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
    ) -> AgentInteraction:
        """
        Create and record an agent interaction for a workflow step.

        Args:
            step: The step being executed
            execution_context: Current execution context

        Returns:
            The created AgentInteraction object. Issue #620.
        """
        agent_id = step.get("assigned_agent")
        interaction = AgentInteraction(
            interaction_id=str(uuid.uuid4()),
            timestamp=datetime.now(),
            source_agent="orchestrator",
            target_agent=agent_id,
            interaction_type="request",
            message={
                "step_id": step["id"],
                "action": step["action"],
                "inputs": step["inputs"],
            },
            context={"workflow_id": execution_context["workflow_id"]},
        )
        self.agent_interactions.append(interaction)
        execution_context["interactions"].append(interaction)
        return interaction

    def _build_step_success_result(
        self,
        result: Dict[str, Any],
        agent_id: Optional[str],
        step_id: str,
    ) -> Dict[str, Any]:
        """
        Build success result dict for a completed step.

        Extracted from _execute_coordinated_step() to reduce function length. Issue #620.

        Args:
            result: The step execution result
            agent_id: Agent that executed the step
            step_id: Step identifier

        Returns:
            Success result dict
        """
        return {
            "success": True,
            "result": result,
            "agent_id": agent_id,
            "step_id": step_id,
        }

    def _build_step_failure_result(
        self,
        error: Exception,
        agent_id: Optional[str],
        step_id: str,
    ) -> Dict[str, Any]:
        """
        Build failure result dict for a failed step.

        Extracted from _execute_coordinated_step() to reduce function length. Issue #620.

        Args:
            error: The exception that occurred
            agent_id: Agent that attempted the step
            step_id: Step identifier

        Returns:
            Failure result dict
        """
        return {
            "success": False,
            "error": str(error),
            "agent_id": agent_id,
            "step_id": step_id,
        }

    @circuit_breaker_async(
        "workflow_step_execution",
        failure_threshold=CircuitBreakerDefaults.LLM_FAILURE_THRESHOLD,
        recovery_timeout=CircuitBreakerDefaults.LLM_RECOVERY_TIMEOUT,
    )
    @retry_async(
        max_attempts=RetryConfig.MIN_RETRIES, strategy=RetryStrategy.EXPONENTIAL_BACKOFF
    )
    async def _execute_coordinated_step(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a single workflow step with agent coordination.

        Issue #620: Refactored to use extracted helper methods.
        Issue #2168: Protected by circuit breaker and retry decorator.

        Args:
            step: The step to execute
            execution_context: Current execution context
            context: Workflow context

        Returns:
            Step execution result
        """
        agent_id = step.get("assigned_agent")
        step_id = step["id"]

        logger.info("Executing step %s with agent %s", step_id, agent_id)

        interaction: Optional[AgentInteraction] = None
        if agent_id:
            interaction = self._create_agent_interaction(step, execution_context)

        try:
            result = await self._simulate_step_execution(step, context)
            if interaction:
                interaction.outcome = "success"
                interaction.message["result"] = result
            return self._build_step_success_result(result, agent_id, step_id)

        except Exception as e:
            logger.error("Step %s execution failed: %s", step_id, e)
            if interaction:
                interaction.outcome = "failed"
                interaction.message["error"] = str(e)
            return self._build_step_failure_result(e, agent_id, step_id)

    async def _simulate_step_execution(
        self,
        step: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Placeholder — actual agent delegation is not implemented.

        Issue #2869: Replace this method body with a real agent dispatch call.
        Until then, raise explicitly so workflows fail loudly rather than
        returning fake results that look like real work.

        Args:
            step: The step to execute
            context: Workflow context
        """
        step_id = step.get("id", "<unknown>")
        action = step.get("action", "<unknown>")
        logger.warning(
            "Workflow step %s (action=%s) cannot be executed: "
            "agent dispatch is not implemented. (#2869)",
            step_id,
            action,
        )
        raise NotImplementedError(
            f"Workflow step '{step_id}' (action='{action}'): "
            "agent execution is not implemented. "
            "Wire _simulate_step_execution to the agent dispatcher. (#2869)"
        )

    def _log_plan_details(self, workflow_id: str, plan_summary: Dict[str, Any]) -> None:
        """
        Log workflow plan details for visibility.

        Args:
            workflow_id: ID of the workflow
            plan_summary: Plan summary containing steps and estimates. Issue #620.
        """
        logger.info(
            "Workflow %s plan: %d steps, estimated %.1fs total",
            workflow_id,
            plan_summary["total_steps"],
            plan_summary["estimated_total_duration"],
        )
        for step in plan_summary["steps"]:
            logger.info(
                "  Step %s: %s (agent: %s, ~%.1fs)",
                step["id"],
                step["action"],
                step["assigned_agent"],
                step["estimated_duration"],
            )

    async def request_plan_approval(
        self,
        workflow_id: str,
        user_request: str,
        plan_summary: Dict[str, Any],
        approval_callback: Optional[callable] = None,
    ) -> Dict[str, Any]:
        """
        Request approval for the workflow plan before execution.

        Args:
            workflow_id: ID of the workflow
            user_request: Original user request
            plan_summary: Plan summary for approval
            approval_callback: Optional async callback to get approval

        Returns:
            Dict with 'approved' (bool), 'reason' (str), and 'plan' (dict)
        """
        if approval_callback:
            try:
                approved, reason = await approval_callback(plan_summary)
                return {"approved": approved, "reason": reason, "plan": plan_summary}
            except Exception as e:
                logger.error("Plan approval callback failed: %s", e)
                return {
                    "approved": False,
                    "reason": f"Approval callback error: {str(e)}",
                    "plan": plan_summary,
                }

        self._log_plan_details(workflow_id, plan_summary)
        return {
            "approved": True,
            "reason": "Auto-approved (no approval callback provided)",
            "plan": plan_summary,
        }
