# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
from __future__ import annotations

"""
Workflow Executor

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains workflow execution, step coordination, and agent interaction handling.

Executor scope (#6826): WorkflowExecutor is the **main linear/parallel workflow
engine**.  It handles step dependency grouping, variable resolution, sub-workflow
delegation, error handlers, and notifications.  For DAG/condition workflows it
delegates to DAGExecutor; checkpoint logic delegates to CheckpointResumer (#6827).
The long-term migration path (replacing DAGExecutor with GraphRunner) is tracked
in #6826.

Issue #2168: Added circuit breaker + retry decorators to step execution.
Issue #2172: Added parallel execution for independent workflow steps.
Issue #2140: DAG-based execution with condition evaluation and branch routing.
Issue #2141: Structured variable piping — ${steps.<id>.output} resolved before
             each step executes; completed step results stored as StepOutput.
Issue #2154: Step-level error handlers (retry/skip/fallback/pause/abort) and
             workflow resume-from-checkpoint via Redis.
Issue #2143: Sub-workflow composition — a step with type="sub_workflow" delegates
             to SubWorkflowExecutor, which executes the child workflow and stores
             its result as a StepOutput under the caller's step_outputs registry.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List

from autobot_shared.logging_manager import get_logger
from circuit_breaker import circuit_breaker_async
from constants.status_enums import TaskStatus
from constants.threshold_constants import (
    CircuitBreakerDefaults,
    RetryConfig,
)
from retry_mechanism import RetryStrategy, retry_async

from .checkpoint_resumer import CheckpointResumer
from .dag_executor import (
    DAGExecutionContext,
    DAGExecutor,
    DAGNode,
    build_dag,
    workflow_has_condition_nodes,
)
from .error_handler import (
    StepErrorAction,
    StepErrorHandler,
)
from .execution_modes import DebugController, DryRunValidator, ExecutionMode
from .sub_workflow import (
    SubWorkflowExecutor,
    extract_sub_workflow_step,
    is_sub_workflow_step,
)
from .success_criteria import SuccessCriteriaEvaluator
from .types import AgentInteraction, AgentProfile
from .variable_resolver import StepOutput, VariableResolver
from .workflow_memory import WorkflowMemory

# Issue #3101: lazy import to avoid circular deps at module level
_notification_service = None

logger = get_logger(__name__)


def _get_notification_service():
    """Lazy-load NotificationService singleton (#3101)."""
    global _notification_service  # noqa: PLW0603
    if _notification_service is None:
        from services.notification_service import NotificationService

        _notification_service = NotificationService()
    return _notification_service


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
        workflow_fetcher: Callable[[str], Dict[str, Any] | None] | None = None,
        memory: WorkflowMemory | None = None,
        criteria_evaluator: SuccessCriteriaEvaluator | None = None,
    ):
        """
        Initialize the workflow executor.

        Args:
            agent_registry:              Registry of available agents.
            agent_interactions:          List to track agent interactions.
            reserve_agent_callback:      Function to reserve an agent.
            release_agent_callback:      Function to release an agent.
            update_performance_callback: Function to update agent performance.
            workflow_fetcher:            Optional callable ``(workflow_id) → workflow_dict``
                                         used to load child workflows for sub-workflow
                                         composition (Issue #2143).  When None, sub-workflow
                                         steps raise ``ValueError`` at execution time.
            memory:                      Optional shared WorkflowMemory for multi-agent
                                         collaboration state (Issue #3009).  When provided,
                                         parallel step agents can read and write a common
                                         KV store scoped to this workflow execution.
            criteria_evaluator:          Optional SuccessCriteriaEvaluator (GH #6832).
                                         When provided, evaluates structured_criteria in
                                         execution_context after status is determined.
        """
        self.agent_registry = agent_registry
        self.agent_interactions = agent_interactions
        self._reserve_agent = reserve_agent_callback
        self._release_agent = release_agent_callback
        self._update_performance = update_performance_callback
        # Issue #3009: shared KV memory for multi-agent collaboration
        self.memory = memory
        # Issue #2141: variable resolver for ${steps…} piping between steps
        self._variable_resolver = VariableResolver()
        # Issue #2154 / #6827: checkpoint logic delegated to CheckpointResumer.
        self._checkpoint_resumer = CheckpointResumer()
        self._error_handler = StepErrorHandler()
        # Issue #2143: sub-workflow executor (None when fetcher not provided)
        self._sub_workflow_executor: SubWorkflowExecutor | None = (
            SubWorkflowExecutor(workflow_executor=self, workflow_fetcher=workflow_fetcher)
            if workflow_fetcher is not None
            else None
        )
        # GH #6832: optional success criteria evaluator
        self._criteria_evaluator = criteria_evaluator

    def _group_steps_by_dependency(self, steps: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
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
                sid for sid in remaining if all(dep in completed for dep in step_map[sid].get("dependencies", []))
            ]

            if not ready_ids:
                logger.error("Circular dependency in workflow steps; falling back to sequential")
                for sid in remaining:
                    groups.append([step_map[sid]])
                break

            groups.append([step_map[sid] for sid in ready_ids])
            for sid in ready_ids:
                remaining.remove(sid)
            completed.update(ready_ids)

        return groups

    def _determine_workflow_status(self, steps: List[Dict[str, Any]], execution_context: Dict[str, Any]) -> None:
        """Determine overall workflow status from step results (Issue #398: extracted)."""
        successful_steps = sum(1 for step in steps if step.get("status") == TaskStatus.COMPLETED.value)
        total_steps = len(steps)

        if successful_steps == total_steps:
            execution_context["status"] = TaskStatus.COMPLETED.value
        elif successful_steps > 0:
            execution_context["status"] = TaskStatus.PARTIALLY_COMPLETED.value
        else:
            execution_context["status"] = TaskStatus.FAILED.value

        execution_context["success_rate"] = successful_steps / total_steps if total_steps > 0 else 0
        execution_context["agents_involved"] = list(execution_context["agents_involved"])

    def _resolve_notification_config(self, workflow_id: str, execution_context: Dict[str, Any]):
        """Resolve the workflow's NotificationConfig (#3168).

        Looks for ``notification_config`` in ``execution_context`` (injected
        by the workflow manager).  Returns None when no config is present,
        which causes notification methods to skip silently.
        """
        from services.notification_service import NotificationConfig

        raw = execution_context.get("notification_config")
        if raw is None:
            return None
        if isinstance(raw, NotificationConfig):
            return raw
        if isinstance(raw, dict):
            # #7010 cluster 3: caller-provided dict may itself contain a
            # `workflow_id` key (e.g., chat_workflow snapshots the config
            # before passing it down). Drop it before spreading so we don't
            # raise "got multiple values for keyword argument 'workflow_id'".
            kwargs = {k: v for k, v in raw.items() if k != "workflow_id"}
            return NotificationConfig(workflow_id=workflow_id, **kwargs)
        return None

    async def _send_workflow_notification(self, workflow_id: str, execution_context: Dict[str, Any]) -> None:
        """Fire a notification for a terminal workflow status (#3101, #3168)."""
        from services.notification_service import NotificationEvent

        config = self._resolve_notification_config(workflow_id, execution_context)
        if config is None:
            return

        status = execution_context.get("status", "")
        event_map = {
            TaskStatus.COMPLETED.value: NotificationEvent.WORKFLOW_COMPLETED,
            TaskStatus.FAILED.value: NotificationEvent.WORKFLOW_FAILED,
        }
        event = event_map.get(status)
        if event is None:
            return
        try:
            svc = _get_notification_service()
            payload = {
                "workflow_id": workflow_id,
                "status": status,
                "error": execution_context.get("error", ""),
            }
            await svc.send(event, workflow_id, payload, config)
        except Exception:
            logger.warning(
                "Failed to send %s notification for workflow %s",
                status,
                workflow_id,
                exc_info=True,
            )

    async def _send_step_failure_notification(
        self,
        workflow_id: str,
        step_id: str,
        error: str,
        execution_context: Dict[str, Any] | None = None,
    ) -> None:
        """Fire a STEP_FAILED notification (#3101, #3168)."""
        from services.notification_service import NotificationEvent

        config = self._resolve_notification_config(workflow_id, execution_context or {})
        if config is None:
            return

        try:
            svc = _get_notification_service()
            payload = {
                "workflow_id": workflow_id,
                "step_name": step_id,
                "error": error,
            }
            await svc.send(NotificationEvent.STEP_FAILED, workflow_id, payload, config)
        except Exception:
            logger.warning(
                "Failed to send step-failure notification for %s/%s",
                workflow_id,
                step_id,
                exc_info=True,
            )

    def _resolve_step_variables(self, step: Dict[str, Any], step_outputs: Dict[str, StepOutput]) -> None:
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
                logger.debug("Step %s: resolved command variables (#2141)", step.get("id"))
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

        # Issue #2143: sub-workflow steps are handled before agent reservation.
        if is_sub_workflow_step(step):
            await self._execute_sub_workflow_step(step, execution_context, context)
            return

        if agent_id:
            self._reserve_agent(agent_id)

        try:
            step_result = await self._execute_step_with_retry(step, execution_context, context)
            elapsed = time.time() - step_start_time

            step["status"] = TaskStatus.COMPLETED.value if step_result.get("success") else TaskStatus.FAILED.value
            step["execution_time"] = elapsed
            step["result"] = step_result
            execution_context["step_results"][step_id] = step_result

            # Issue #3101/#3168: notify on step failure.
            if not step_result.get("success"):
                await self._send_step_failure_notification(
                    execution_context.get("workflow_id", ""),
                    step_id,
                    step_result.get("error", "unknown"),
                    execution_context=execution_context,
                )

            # Issue #2141: Record typed StepOutput so later steps can reference it.
            if "step_outputs" in execution_context:
                execution_context["step_outputs"][step_id] = StepOutput.from_step_result(step_result)

            # Issue #2154: Checkpoint after successful completion.
            # Issue #3825: Checkpoint failure must never surface as a step failure.
            if step_result.get("success"):
                try:
                    self._save_checkpoint(execution_context.get("workflow_id", ""), step_id, step_result)
                except Exception as exc:
                    logger.warning("Checkpoint save failed for step %s (non-fatal): %s", step_id, exc)

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

    async def _execute_sub_workflow_step(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
    ) -> None:
        """
        Execute a sub-workflow invocation step and store its result.

        Delegates to SubWorkflowExecutor, then stores the child execution
        context as a StepOutput in ``execution_context["step_outputs"]`` under
        the step's ID, so parent steps can reference child results via the
        standard ``${steps.<id>.output.*}`` variable syntax.

        Issue #2143.

        Args:
            step:              The sub-workflow step dict (type="sub_workflow").
            execution_context: Parent workflow's execution context (mutated in-place).
            context:           Parent workflow's input context forwarded to the child.
        """
        step_id = step["id"]
        step_start_time = time.time()

        if self._sub_workflow_executor is None:
            logger.error(
                "Sub-workflow step %s: no workflow_fetcher configured — cannot execute",
                step_id,
            )
            step["status"] = TaskStatus.FAILED.value
            step["result"] = {
                "success": False,
                "step_id": step_id,
                "error": "WorkflowExecutor was not initialised with a workflow_fetcher; "
                "sub-workflow steps cannot be executed.",
            }
            execution_context["step_results"][step_id] = step["result"]
            return

        sub_step = extract_sub_workflow_step(step)
        parent_step_outputs: Dict[str, StepOutput] = execution_context.get("step_outputs", {})

        try:
            step_result = await self._sub_workflow_executor.execute(
                sub_step=sub_step,
                parent_context=context,
                parent_step_outputs=parent_step_outputs,
            )
        except Exception as exc:
            elapsed = time.time() - step_start_time
            logger.error("Sub-workflow step %s failed: %s", step_id, exc)
            step["status"] = TaskStatus.FAILED.value
            step["execution_time"] = elapsed
            step["result"] = {"success": False, "step_id": step_id, "error": str(exc)}
            execution_context["step_results"][step_id] = step["result"]
            return

        elapsed = time.time() - step_start_time
        step["status"] = TaskStatus.COMPLETED.value if step_result.get("success") else TaskStatus.FAILED.value
        step["execution_time"] = elapsed
        step["result"] = step_result
        execution_context["step_results"][step_id] = step_result

        # Store the child's execution context as a StepOutput for variable piping.
        if "step_outputs" in execution_context:
            child_ctx = step_result.get("sub_workflow_result", {})
            stdout = ""
            execution_context["step_outputs"][step_id] = StepOutput(
                status=TaskStatus.COMPLETED.value if step_result.get("success") else TaskStatus.FAILED.value,
                stdout=stdout,
                parsed_json=child_ctx if isinstance(child_ctx, dict) else None,
                metadata={"output_key": sub_step.output_key, "execution_time": elapsed},
            )
            logger.debug(
                "Sub-workflow step %s: stored child result under step_outputs[%s]",
                step_id,
                step_id,
            )

        # Issue #2154: checkpoint after successful completion.
        # Issue #3825: Checkpoint failure must never surface as a step failure.
        if step_result.get("success"):
            try:
                self._save_checkpoint(execution_context.get("workflow_id", ""), step_id, step_result)
            except Exception as exc:
                logger.warning("Checkpoint save failed for step %s (non-fatal): %s", step_id, exc)

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
                outcome = await self._error_handler.handle_error(step, exc, attempt, execution_context)
                action = outcome["action"]

                if action == StepErrorAction.RETRY:
                    attempt += 1
                    continue

                if action == StepErrorAction.SKIP:
                    step["status"] = TaskStatus.SKIPPED.value
                    logger.info("Step %s skipped due to error_config", step.get("id"))
                    return {"success": True, "skipped": True, "step_id": step.get("id")}

                if action == StepErrorAction.FALLBACK:
                    return await self._execute_fallback_step(outcome["fallback_id"], step, execution_context, context)

                if action == StepErrorAction.PAUSE:
                    execution_context["status"] = TaskStatus.PAUSED.value
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
            result = await self._execute_coordinated_step(fallback_step, execution_context, context)
            result["fallback_for"] = original_step.get("id")
            return result
        except Exception as exc:
            logger.error("Fallback step %s also failed: %s", fallback_step_id, exc)
            raise

    def _save_checkpoint(self, workflow_id: str, step_id: str, step_result: Dict[str, Any]) -> None:
        """Delegate to CheckpointResumer.save (#6827)."""
        self._checkpoint_resumer.save(workflow_id, step_id, step_result)

    async def execute_coordinated_workflow(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
        edges: List[Dict[str, Any]] | None = None,
        resume_from_checkpoint: bool = False,
        mode: ExecutionMode = ExecutionMode.NORMAL,
        debug_controller: DebugController | None = None,
        notification_config: Any | None = None,
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

        Issue #3172: ``notification_config`` is injected into the
        execution_context so ``_resolve_notification_config`` can find it and
        fire notifications at terminal workflow states.  Accepts either a
        ``NotificationConfig`` instance or a plain dict (the resolver handles
        both).

        Args:
            workflow_id:          Workflow identifier.
            steps:                List of enhanced workflow steps.
            context:              Workflow context.
            edges:                Optional DAG edge dicts.
            resume_from_checkpoint: When True, load prior checkpoints and skip
                                  already-completed steps.
            notification_config:  Optional NotificationConfig (or equivalent
                                  dict) for this workflow's notifications.

        Returns:
            Execution context with results.
        """
        # Issue #2148: dry-run returns a validation report without executing.
        # #7010 cluster 3: tests expect report fields (valid / issues /
        # warnings / execution_plan) at the top level alongside workflow_id
        # and mode — flatten the report dict so result["valid"] etc. work.
        if mode == ExecutionMode.DRY_RUN:
            validator = DryRunValidator()
            report = validator.validate(workflow_id, steps, edges)
            return {
                "status": "dry_run_complete",
                "mode": "dry_run",
                "workflow_id": workflow_id,
                **report.to_dict(),
            }

        # #7206: DEBUG mode wiring (Issue #2148 finalisation).
        # When the caller requests DEBUG without a controller, log a warning
        # and fall through to the NORMAL execution path. With a controller,
        # delegate to the debug-aware loop that consults the controller
        # before each step.
        if mode == ExecutionMode.DEBUG:
            if debug_controller is None:
                logger.warning(
                    "ExecutionMode.DEBUG requested but debug_controller is " "None — falling back to NORMAL execution"
                )
                # Fall through — execute the rest of the function as NORMAL.
            else:
                return await self._execute_debug_workflow(
                    workflow_id,
                    steps,
                    context,
                    debug_controller,
                    notification_config,
                )

        effective_edges = edges or []
        if workflow_has_condition_nodes(steps, effective_edges):
            logger.info(
                "Workflow %s: condition nodes detected — using DAG executor (#2140)",
                workflow_id,
            )
            return await self._execute_dag_workflow(
                workflow_id,
                steps,
                effective_edges,
                context,
                notification_config=notification_config,
            )

        # Issue #2154: build a step registry so fallback resolution works.
        step_registry = {s["id"]: s for s in steps}

        # Issue #3019: shared KV store for in-flight collaboration between
        # parallel steps.  Exposed via execution_context["shared_memory"] so
        # step executors can read/write without knowing workflow internals.
        shared_memory = WorkflowMemory(workflow_id=workflow_id)

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
            # Issue #3019: shared memory for parallel-step collaboration
            "shared_memory": shared_memory,
            # Issue #3172: notification routing config so _resolve_notification_config
            # can fire notifications at terminal workflow states.
            "notification_config": notification_config,
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
                pending = [s for s in group if s.get("status") != TaskStatus.COMPLETED.value]
                if not pending:
                    logger.debug(
                        "Workflow %s: skipping fully-checkpointed group %s",
                        workflow_id,
                        [s["id"] for s in group],
                    )
                    continue
                await self._execute_step_group(pending, execution_context, context)

                # Issue #2154: stop if a step triggered a PAUSE.
                if execution_context.get("status") == TaskStatus.PAUSED.value:
                    logger.info(
                        "Workflow %s paused at step %s",
                        workflow_id,
                        execution_context.get("paused_at_step"),
                    )
                    return execution_context

            self._determine_workflow_status(steps, execution_context)

            # GH #6832: optional success criteria evaluation
            if self._criteria_evaluator and execution_context.get("structured_criteria"):
                eval_result = await self._criteria_evaluator.evaluate(
                    execution_context["structured_criteria"], execution_context
                )
                execution_context["criteria_evaluation"] = eval_result.to_dict()

            # Issue #2154: clear checkpoints on full success.
            # Issue #3019: also clear shared memory — no longer needed once the
            # workflow reaches a terminal state.
            if execution_context.get("status") == TaskStatus.COMPLETED.value:
                self._checkpoint_resumer.clear(workflow_id)
                shared_memory.clear()

            # Issue #3101: fire notification on terminal status.
            await self._send_workflow_notification(workflow_id, execution_context)

            return execution_context

        except Exception as e:
            logger.error("Workflow %s execution failed: %s", workflow_id, e)
            execution_context["status"] = TaskStatus.FAILED.value
            execution_context["error"] = str(e)
            # Issue #3101: fire failure notification.
            await self._send_workflow_notification(workflow_id, execution_context)
            return execution_context

    def _apply_checkpoints(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        execution_context: Dict[str, Any],
    ) -> None:
        """Delegate to CheckpointResumer.apply (#6827)."""
        self._checkpoint_resumer.apply(workflow_id, steps, execution_context)

    async def _execute_debug_workflow(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
        controller: DebugController,
        notification_config: Any | None = None,
    ) -> Dict[str, Any]:
        """Step-by-step execution gated by an external DebugController.

        Before each step, blocks on ``controller.wait_for_resume(step_id)``
        and reacts to the returned signal:

        - ``RESUME``: execute the step normally via ``_execute_coordinated_step``.
        - ``SKIP``:   record the step as skipped and advance.
        - ``RETRY``:  re-execute the most recent step (one rewind).

        Returns the same execution_context shape as the NORMAL path so
        downstream callers (notification helpers, caller assertions) need
        no special handling.

        #7206 / Issue #2148.
        """
        execution_context: Dict[str, Any] = {
            "workflow_id": workflow_id,
            "mode": "debug",
            "step_results": {},
            "agents_involved": set(),
            "interactions": [],
            "status": TaskStatus.RUNNING.value,
            "notification_config": notification_config,
        }

        i = 0
        while i < len(steps):
            step = steps[i]
            step_id = step["id"]
            signal = await controller.wait_for_resume(step_id)

            if signal == DebugController.Signal.SKIP:
                execution_context["step_results"][step_id] = {
                    "skipped": True,
                    "step_id": step_id,
                    "reason": "debug_skip",
                }
                i += 1
                continue

            if signal == DebugController.Signal.RETRY and i > 0:
                # Rewind to the previous step. Clear its prior result so
                # the re-execution overwrites cleanly.
                i -= 1
                prior = steps[i]["id"]
                execution_context["step_results"].pop(prior, None)
                continue

            # RESUME (or RETRY at i=0) — execute normally.
            try:
                result = await self._execute_coordinated_step(step, execution_context, context)
                execution_context["step_results"][step_id] = result
            except Exception as exc:
                logger.error("Debug step %s failed: %s", step_id, exc, exc_info=True)
                execution_context["step_results"][step_id] = {
                    "success": False,
                    "error": str(exc),
                    "step_id": step_id,
                }
            i += 1

        # Determine final status from individual step results
        any_failed = any(
            r.get("success") is False for r in execution_context["step_results"].values() if isinstance(r, dict)
        )
        execution_context["status"] = TaskStatus.FAILED.value if any_failed else TaskStatus.COMPLETED.value

        # #3172 parity: notify on terminal status from DEBUG path too.
        await self._send_workflow_notification(workflow_id, execution_context)

        return execution_context

    async def _execute_dag_workflow(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        edges: List[Dict[str, Any]],
        context: Dict[str, Any],
        notification_config: Any | None = None,
    ) -> Dict[str, Any]:
        """
        Execute a branching workflow via DAGExecutor.

        Builds a WorkflowDAG from *steps* + *edges*, runs it, then
        converts the DAGExecutionContext back into the legacy
        execution_context dict shape so callers stay oblivious to the
        execution path.  Issue #2140.

        Issue #3172: ``notification_config`` is forwarded into the returned
        execution_context so the notification helpers can locate it.
        """
        dag = build_dag(steps, edges)
        executor = DAGExecutor(step_executor_callback=self._dag_step_adapter)
        dag_ctx = await executor.execute(dag, workflow_id, context)
        result = self._dag_ctx_to_execution_context(dag_ctx)
        result["notification_config"] = notification_config
        # Issue #3172: fire notification for terminal states, mirroring the
        # linear execution path (execute_coordinated_workflow lines 727/738).
        await self._send_workflow_notification(workflow_id, result)
        return result

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
        return step.get("result", {"success": step.get("status") == TaskStatus.COMPLETED.value})

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
            *(self._execute_step_with_agent(step, iso_ctx, context) for step, iso_ctx in zip(group, isolated_contexts))
        )
        for iso_ctx in isolated_contexts:
            execution_context["step_results"].update(iso_ctx["step_results"])
            execution_context["agents_involved"].update(iso_ctx["agents_involved"])
            execution_context["interactions"].extend(iso_ctx["interactions"])
            # Merge new step outputs written during this group into the main context.
            if "step_outputs" in execution_context:
                new_outputs = {k: v for k, v in iso_ctx["step_outputs"].items() if k not in shared_prior_outputs}
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
            timestamp=datetime.now(tz=timezone.utc),
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
        agent_id: str | None,
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
        agent_id: str | None,
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
    @retry_async(max_attempts=RetryConfig.MIN_RETRIES, strategy=RetryStrategy.EXPONENTIAL_BACKOFF)
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

        interaction: AgentInteraction | None = None
        if agent_id:
            interaction = self._create_agent_interaction(step, execution_context)

        # Issue #3099: Auto-inject prior agent findings from shared memory
        # into both the context dict and the step command/prompt so downstream
        # agents receive the information without needing to read context explicitly.
        shared_memory = execution_context.get("shared_memory")
        if shared_memory:
            prior_findings = shared_memory.get_all()
            if prior_findings:
                context["prior_agent_findings"] = prior_findings
                findings_section = "\n\n## Prior Agent Findings\n"
                for key, value in prior_findings.items():
                    findings_section += f"- **{key}**: {value}\n"
                command = step.get("command", "")
                if isinstance(command, str) and command:
                    step["command"] = command + findings_section

        try:
            result = await self._simulate_step_execution(step, context)
            if interaction:
                interaction.outcome = "success"
                interaction.message["result"] = result
            return self._build_step_success_result(result, agent_id, step_id)

        except NotImplementedError:
            # #7010 cluster 5: NotImplementedError marks a stub / unwired
            # codepath (e.g., #2869 agent dispatcher not implemented yet).
            # Propagate to the caller so the workflow halts loudly instead
            # of silently treating the unwired step as "failed". Test
            # fixtures rely on this propagation to verify intermediate
            # state was updated before the unimplemented call ran.
            raise
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
            "Workflow step %s (action=%s) cannot be executed: " "agent dispatch is not implemented. (#2869)",
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
        approval_callback: callable | None = None,
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
