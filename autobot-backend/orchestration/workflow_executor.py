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
Issue #2141: Structured variable piping — ${steps.<id>.output} resolved before
             each step executes; completed step results stored as StepOutput.
Issue #2154: Step-level error handlers (retry/skip/fallback/pause/abort) and
             workflow resume-from-checkpoint via Redis.
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
    StepCheckpoint,
    StepErrorAction,
    StepErrorHandler,
    WorkflowCheckpointManager,
)
from .execution_modes import DebugController, DryRunValidator, ExecutionMode
from .types import AgentInteraction, AgentProfile
from .variable_resolver import StepOutput, VariableResolver

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """
    Executes workflows with coordinated agent management.

    Handles:
    - Step execution with dependency management
    - Agent reservation and release
    - Performance metric updates
    - Agent interaction recording
    """

    def __init__(
        self,
        agent_registry: Dict[str, AgentProfile],
        agent_interactions: List[AgentInteraction],
        reserve_agent_callback: Callable[[str], None],
        release_agent_callback: Callable[[str], None],
        update_performance_callback: Callable[[str, bool, float], None],
    ):
        """
        Initialize the workflow executor.

        Args:
            agent_registry: Registry of available agents
            agent_interactions: List to track agent interactions
            reserve_agent_callback: Function to reserve an agent
            release_agent_callback: Function to release an agent
            update_performance_callback: Function to update agent performance
        """
        self.agent_registry = agent_registry
        self.agent_interactions = agent_interactions
        self._reserve_agent = reserve_agent_callback
        self._release_agent = release_agent_callback
        self._update_performance = update_performance_callback
        # Issue #2141: variable resolver for ${steps…} piping between steps
        self._variable_resolver = VariableResolver()
        # Issue #2154: checkpoint manager and error handler
        self._checkpoint_manager = WorkflowCheckpointManager()
        self._error_handler = StepErrorHandler()

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

    def _resolve_step_variables(
        self, step: Dict[str, Any], step_outputs: Dict[str, StepOutput]
    ) -> None:
        """
        Resolve ``${steps.<id>.<accessor>}`` tokens in *step* in-place.

        Mutates the step dict's ``command`` (str) and ``inputs`` (dict of str
        values) fields so the step executes with fully-substituted values.
        Fields that contain no variable tokens are left untouched.

        Issue #2141.
        """
        command = step.get("command")
        if isinstance(command, str):
            resolved = self._variable_resolver.resolve(command, step_outputs)
            if resolved != command:
                logger.debug(
                    "Step %s: resolved command variables (#2141)", step.get("id")
                )
                step["command"] = resolved

        inputs = step.get("inputs")
        if isinstance(inputs, dict):
            for key, value in inputs.items():
                if isinstance(value, str):
                    resolved_value = self._variable_resolver.resolve(value, step_outputs)
                    if resolved_value != value:
                        logger.debug(
                            "Step %s: resolved input '%s' variable (#2141)",
                            step.get("id"),
                            key,
                        )
                        inputs[key] = resolved_value

    async def _execute_step_with_agent(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        """Execute a single workflow step with agent management.

        Issue #398: extracted from execute_coordinated_workflow.
        Issue #2141: resolves ${steps…} variables in step command/inputs before
        execution, then stores a StepOutput for downstream steps to reference.
        Issue #2154: checkpoints successful steps; consults error handler on failure.
        """
        step_start_time = time.time()
        agent_id = step.get("assigned_agent")
        step_id = step["id"]

        # Issue #2141: Resolve variable references using outputs from prior steps.
        step_outputs: Dict[str, StepOutput] = execution_context.get("step_outputs", {})
        self._resolve_step_variables(step, step_outputs)

        if agent_id:
            self._reserve_agent(agent_id)

        try:
            step_result = await self._execute_step_with_retry(
                step, execution_context, context
            )
            elapsed = time.time() - step_start_time

            step["status"] = "completed" if step_result.get("success") else "failed"
            step["execution_time"] = elapsed
            step["result"] = step_result
            execution_context["step_results"][step_id] = step_result

            # Issue #2141: Record typed StepOutput so later steps can reference it.
            if "step_outputs" in execution_context:
                execution_context["step_outputs"][step_id] = StepOutput.from_step_result(
                    step_result
                )

            # Issue #2154: Checkpoint after successful completion.
            if step_result.get("success"):
                self._save_checkpoint(execution_context.get("workflow_id", ""), step_id, step_result)

            if agent_id:
                execution_context["agents_involved"].add(agent_id)
                self._update_performance(
                    agent_id,
                    step_result.get("success", False),
                    elapsed,
                )
        finally:
            if agent_id:
                self._release_agent(agent_id)

    async def _execute_step_with_retry(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute *step* and apply error_config on failure.

        Handles RETRY (with backoff), SKIP, FALLBACK, PAUSE, and ABORT.
        Returns a step result dict with ``success`` True/False.

        Issue #2154.
        """
        attempt = 1
        while True:
            try:
                return await self._execute_coordinated_step(step, execution_context, context)
            except Exception as exc:
                outcome = await self._error_handler.handle_error(
                    step, exc, attempt, execution_context
                )
                action = outcome["action"]

                if action == StepErrorAction.RETRY:
                    attempt += 1
                    continue

                if action == StepErrorAction.SKIP:
                    step["status"] = "skipped"
                    logger.info("Step %s skipped due to error_config", step.get("id"))
                    return {"success": True, "skipped": True, "step_id": step.get("id")}

                if action == StepErrorAction.FALLBACK:
                    return await self._execute_fallback_step(
                        outcome["fallback_id"], step, execution_context, context
                    )

                if action == StepErrorAction.PAUSE:
                    execution_context["status"] = "paused"
                    execution_context["paused_at_step"] = step.get("id")
                    return {
                        "success": False,
                        "paused": True,
                        "step_id": step.get("id"),
                        "error": outcome["reason"],
                    }

                # ABORT — propagate so the caller marks the workflow failed.
                raise

    async def _execute_fallback_step(
        self,
        fallback_step_id: str,
        original_step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Look up and execute the fallback step for *original_step*.

        If the fallback step is not found in the execution context's step
        registry, abort with an error rather than silently returning success.

        Issue #2154.
        """
        step_registry: Dict[str, Dict[str, Any]] = execution_context.get("step_registry", {})
        fallback_step = step_registry.get(fallback_step_id)

        if fallback_step is None:
            logger.error(
                "Step %s: fallback step '%s' not found in step_registry — ABORT",
                original_step.get("id"),
                fallback_step_id,
            )
            raise ValueError(
                f"Fallback step '{fallback_step_id}' not found in workflow "
                f"(original step: {original_step.get('id')})"
            )

        logger.info(
            "Executing fallback step %s for failed step %s",
            fallback_step_id,
            original_step.get("id"),
        )
        try:
            result = await self._execute_coordinated_step(
                fallback_step, execution_context, context
            )
            result["fallback_for"] = original_step.get("id")
            return result
        except Exception as exc:
            logger.error(
                "Fallback step %s also failed: %s", fallback_step_id, exc
            )
            raise

    def _save_checkpoint(self, workflow_id: str, step_id: str, step_result: Dict[str, Any]) -> None:
        """
        Persist a checkpoint for *step_id* after successful execution.

        Silently skips when *workflow_id* is empty (e.g. DAG adapter calls).

        Issue #2154.
        """
        if not workflow_id:
            return
        checkpoint = StepCheckpoint(
            step_id=step_id,
            status="completed",
            output=step_result,
        )
        self._checkpoint_manager.save(workflow_id, checkpoint)

    async def execute_coordinated_workflow(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
        edges: Optional[List[Dict[str, Any]]] = None,
        resume_from_checkpoint: bool = False,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        debug_controller: Optional[DebugController] = None,
    ) -> Dict[str, Any]:
        """
        Execute workflow with coordinated agent management.

        When the step list contains condition nodes (or explicit edges are
        provided), delegates to DAGExecutor for branch-aware execution.
        Plain linear workflows continue to use the existing dependency-group
        path for full backward compatibility.  Issue #2140.

        Issue #2154: Pass ``resume_from_checkpoint=True`` to skip steps that
        already have a persisted checkpoint and continue from the first
        incomplete step.  Checkpoints are cleared on full completion.

        Args:
            workflow_id:             Workflow identifier.
            steps:                   List of enhanced workflow steps.
            context:                 Workflow context.
            edges:                   Optional DAG edge dicts.
            resume_from_checkpoint:  When True, load prior checkpoints and skip
                                     already-completed steps.

        Returns:
            Execution context with results.
        """
        # Issue #2148: dry-run returns a validation report without executing.
        if mode == ExecutionMode.DRY_RUN:
            validator = DryRunValidator()
            report = validator.validate(workflow_id, steps, edges)
            return {"status": "dry_run_complete", "mode": "dry_run", "dry_run_report": report.to_dict()}

        effective_edges = edges or []
        if workflow_has_condition_nodes(steps, effective_edges):
            logger.info(
                "Workflow %s: condition nodes detected — using DAG executor (#2140)",
                workflow_id,
            )
            return await self._execute_dag_workflow(workflow_id, steps, effective_edges, context)

        # Issue #2154: build a step registry so fallback resolution works.
        step_registry = {s["id"]: s for s in steps}

        execution_context = {
            "workflow_id": workflow_id,
            "agents_involved": set(),
            "interactions": [],
            "step_results": {},
            # Issue #2141: typed StepOutput objects for variable resolution
            "step_outputs": {},
            "status": "in_progress",
            # Issue #2154: registry for fallback step lookup
            "step_registry": step_registry,
        }

        # Issue #2154: pre-populate results from persisted checkpoints.
        if resume_from_checkpoint:
            self._apply_checkpoints(workflow_id, steps, execution_context)

        try:
            # Execute steps in dependency-ordered parallel groups (Issue #2172)
            groups = self._group_steps_by_dependency(steps)
            logger.info(
                "Workflow %s: %d steps in %d parallel group(s)%s",
                workflow_id,
                len(steps),
                len(groups),
                " (resuming)" if resume_from_checkpoint else "",
            )

            for group in groups:
                # Issue #2154: skip groups where all steps are already checkpointed.
                pending = [s for s in group if s.get("status") != "completed"]
                if not pending:
                    logger.debug(
                        "Workflow %s: skipping fully-checkpointed group %s",
                        workflow_id,
                        [s["id"] for s in group],
                    )
                    continue
                await self._execute_step_group(pending, execution_context, context)

                # Issue #2154: stop if a step triggered a PAUSE.
                if execution_context.get("status") == "paused":
                    logger.info(
                        "Workflow %s paused at step %s",
                        workflow_id,
                        execution_context.get("paused_at_step"),
                    )
                    return execution_context

            self._determine_workflow_status(steps, execution_context)

            # Issue #2154: clear checkpoints on full success.
            if execution_context.get("status") == "completed":
                self._checkpoint_manager.clear(workflow_id)

            return execution_context

        except Exception as e:
            logger.error("Workflow %s execution failed: %s", workflow_id, e)
            execution_context["status"] = "failed"
            execution_context["error"] = str(e)
            return execution_context

    def _apply_checkpoints(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        execution_context: Dict[str, Any],
    ) -> None:
        """
        Load checkpoints from Redis and mark already-completed steps.

        Mutates *steps* in-place (sets ``status="completed"``) and populates
        ``execution_context["step_results"]`` and ``execution_context["step_outputs"]``
        so variable resolution works correctly for resumed steps.

        Issue #2154.
        """
        checkpoints = self._checkpoint_manager.load_all(workflow_id)
        if not checkpoints:
            return

        logger.info(
            "Workflow %s: resuming with %d checkpointed steps: %s",
            workflow_id,
            len(checkpoints),
            list(checkpoints.keys()),
        )

        for step in steps:
            step_id = step["id"]
            cp = checkpoints.get(step_id)
            if cp is None:
                continue
            step["status"] = "completed"
            execution_context["step_results"][step_id] = cp.output
            execution_context["step_outputs"][step_id] = StepOutput.from_step_result(cp.output)

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

        # Build a minimal execution_context that _execute_step_with_agent can update.
        # Issue #2141: share step_outputs from dag_ctx so variable references resolve
        # across DAG branches that have already executed.
        local_ctx: Dict[str, Any] = {
            "workflow_id": dag_ctx.workflow_id,
            "agents_involved": dag_ctx.agents_involved,
            "interactions": dag_ctx.interactions,
            "step_results": dag_ctx.step_results,
            "step_outputs": dag_ctx.step_outputs,
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
            # Issue #2141: expose typed step outputs to callers
            "step_outputs": dag_ctx.step_outputs,
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
    ) -> None:
        """Execute a group of steps concurrently using asyncio.gather.

        Steps within a group have no inter-dependencies and are safe to run
        in parallel.  Issue #2172.  Issue #2204: collect results per-step and
        merge after gather to avoid concurrent mutation of shared sets/lists.
        """
        if len(group) == 1:
            await self._execute_step_with_agent(group[0], execution_context, context)
            return

        logger.info(
            "Executing %d steps in parallel: %s",
            len(group),
            [s["id"] for s in group],
        )
        # Issue #2204: each step writes to its own isolated context, merged after.
        # Issue #2141: share a snapshot of current step_outputs so parallel steps
        # can resolve references from prior groups; each step writes its own
        # StepOutput to a local dict that is merged back below.
        shared_prior_outputs = dict(execution_context.get("step_outputs", {}))
        isolated_contexts = [
            {
                "step_results": {},
                "agents_involved": set(),
                "interactions": [],
                # Shallow copy: prior-group outputs are readable; writes are isolated.
                "step_outputs": dict(shared_prior_outputs),
            }
            for _ in group
        ]
        await asyncio.gather(
            *(
                self._execute_step_with_agent(step, iso_ctx, context)
                for step, iso_ctx in zip(group, isolated_contexts)
            )
        )
        for iso_ctx in isolated_contexts:
            execution_context["step_results"].update(iso_ctx["step_results"])
            execution_context["agents_involved"].update(iso_ctx["agents_involved"])
            execution_context["interactions"].extend(iso_ctx["interactions"])
            # Merge new step outputs written during this group into the main context.
            if "step_outputs" in execution_context:
                new_outputs = {
                    k: v
                    for k, v in iso_ctx["step_outputs"].items()
                    if k not in shared_prior_outputs
                }
                execution_context["step_outputs"].update(new_outputs)

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
