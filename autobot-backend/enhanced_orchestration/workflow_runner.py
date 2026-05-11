# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Multi-agent workflow execution engine extracted from Orchestrator (#5058).

Structural refactor (#6393/#6392): collaboration and agent-routing responsibilities
moved to CollaborationCoordinator and AgentRouter collaborators respectively.
"""

import asyncio
import time
from typing import Any, Dict, List, Optional, Set

from autobot_shared.logging_manager import get_logger
from enhanced_orchestration.agent_router import AgentRouter
from enhanced_orchestration.collaboration_coordinator import CollaborationCoordinator
from enhanced_orchestration.execution_strategies import ExecutionStrategyHandler
from enhanced_orchestration.success_criteria import SuccessCriteriaEvaluator
from enhanced_orchestration.types import AgentTask, WorkflowDependencies, WorkflowPlan
from enhanced_orchestration.workflow_planning import StrategyPlanner
from event_manager import get_event_manager as _get_event_manager
from orchestration.performance_tracker import PerformanceTracker

logger = get_logger("workflow_runner")


class WorkflowRunner:
    """Executes WorkflowPlan objects via the multi-agent strategy engine.

    Delegates to injected collaborators:
    - AgentRouter    — agent selection, resolution, capability coverage (#6392/#6393)
    - CollaborationCoordinator — Redis pub/sub between agents (#6393)
    - PerformanceTracker — per-agent success/failure metrics (#5058)
    """

    def __init__(
        self,
        strategy_planner: StrategyPlanner,
        performance_tracker: PerformanceTracker,
        active_workflows: Dict[str, WorkflowPlan],
        collaboration: CollaborationCoordinator,
        agent_router: AgentRouter,
        max_parallel_tasks: int = 5,
        criteria_evaluator: Optional[SuccessCriteriaEvaluator] = None,
    ) -> None:
        self._strategy_planner = strategy_planner
        self._perf = performance_tracker
        self.active_workflows = active_workflows
        self._collab = collaboration
        self._agent_router = agent_router
        self.max_parallel_tasks = max_parallel_tasks
        self.resource_semaphore: asyncio.Semaphore = asyncio.Semaphore(max_parallel_tasks)
        self._criteria_evaluator = criteria_evaluator or SuccessCriteriaEvaluator()
        self._strategy_handler: Optional[ExecutionStrategyHandler] = None

    # ------------------------------------------------------------------ helpers

    def _get_strategy_handler(self) -> ExecutionStrategyHandler:
        if self._strategy_handler is None:
            self._strategy_handler = ExecutionStrategyHandler(
                max_parallel_tasks=self.max_parallel_tasks,
                resource_semaphore=self.resource_semaphore,
                deps=WorkflowDependencies(
                    execute_single_task=self._execute_single_agent_task,
                    topological_sort_tasks=self._strategy_planner.topological_sort_tasks,
                    dependencies_met=self._strategy_planner.dependencies_met,
                    group_pipeline_stages=self._strategy_planner.group_pipeline_stages,
                    enhance_task_for_collaboration=self._strategy_planner.enhance_task_for_collaboration,
                    coordinate_collaboration=self._collab.coordinate_collaboration,
                ),
            )
        return self._strategy_handler

    # ----------------------------------------------------------------- public

    async def execute_workflow(self, plan: WorkflowPlan, _depth: int = 0) -> Dict[str, Any]:
        """Execute a WorkflowPlan through the strategy handler."""
        logger.info("Executing workflow %s strategy=%s", plan.plan_id, plan.strategy.value)
        start_time = time.time()
        results: Dict[str, Any] = {}
        try:
            await self._publish_workflow_event(
                plan.plan_id,
                "workflow_started",
                {"goal": plan.goal, "strategy": plan.strategy.value, "task_count": len(plan.tasks)},
            )
            results = await self._get_strategy_handler().execute_by_strategy(plan)
            return await self._handle_workflow_execution_success(plan, results, start_time)
        except Exception as e:
            return await self._handle_workflow_execution_failure(plan, e, results, _depth)

    async def get_agent_recommendations(self, capabilities_needed: Set) -> List[str]:
        return await self._agent_router.get_agent_recommendations(capabilities_needed)

    def get_performance_report(self) -> Dict[str, Any]:
        return {
            "agent_performance": self._perf.report(),
            "active_workflows": len(self.active_workflows),
            "capabilities_coverage": self._agent_router.calculate_capability_coverage(),
        }

    # ------------------------------------------------------ execution internals

    async def _evaluate_workflow_criteria(self, plan: WorkflowPlan, results: Dict[str, Any]) -> Dict[str, Any]:
        if plan.structured_criteria:
            eval_result = await self._criteria_evaluator.evaluate(plan.structured_criteria, results)
            return eval_result.to_dict()
        binary_pass = self._strategy_planner.check_success_criteria(plan, results)
        return {
            "overall": "full" if binary_pass else "failed",
            "score": 1.0 if binary_pass else 0.0,
            "results": [],
        }

    async def _handle_workflow_execution_success(
        self,
        plan: WorkflowPlan,
        results: Dict[str, Any],
        start_time: float,
    ) -> Dict[str, Any]:
        criteria_eval = await self._evaluate_workflow_criteria(plan, results)
        success = criteria_eval["overall"] in ("full", "partial")
        execution_time = time.time() - start_time
        self._perf.update_from_plan(plan, results)
        await self._publish_workflow_event(
            plan.plan_id,
            "workflow_completed",
            {
                "success": success,
                "execution_time": execution_time,
                "results_summary": self._strategy_planner.summarize_results(results),
                "criteria_evaluation": criteria_eval,
            },
        )
        return {
            "plan_id": plan.plan_id,
            "success": success,
            "results": results,
            "execution_time": execution_time,
            "strategy_used": plan.strategy.value,
            "criteria_evaluation": criteria_eval,
        }

    async def _handle_workflow_execution_failure(
        self, plan: WorkflowPlan, error: Exception, results: Dict[str, Any], _depth: int = 0
    ) -> Dict[str, Any]:
        logger.error("Workflow execution failed: %s", error)
        if _depth >= 5:
            logger.error("Max fallback depth (5) reached, aborting fallback chain")
            return {"plan_id": plan.plan_id, "success": False, "error": str(error), "results": results}
        for fallback in plan.fallback_plans or []:
            try:
                return await self.execute_workflow(fallback, _depth + 1)
            except Exception as fe:
                logger.error("Fallback plan failed: %s", fe)
        return {"plan_id": plan.plan_id, "success": False, "error": str(error), "results": results}

    async def _handle_task_timeout(self, task: AgentTask, context: Dict[str, Any]) -> Dict[str, Any]:
        task.fail_execution("Timeout")
        if task.can_retry():
            task.increment_retry()
            logger.warning(
                "Task %s timed out, retrying (%d/%d)",
                task.task_id,
                task.retry_count,
                task.max_retries,
            )
            return await self._execute_single_agent_task(task, context)
        self._perf.update(task.agent_type, False, time.time() - (task.start_time or time.time()))
        return task.to_failed_result("Task execution timed out")

    def _handle_task_exception(self, task: AgentTask, error: Exception) -> Dict[str, Any]:
        task.fail_execution(str(error))
        execution_time = time.time() - (task.start_time or time.time())
        self._perf.update(task.agent_type, False, execution_time)
        return task.to_failed_result(str(error))

    async def _execute_single_agent_task(self, task: AgentTask, context: Dict[str, Any]) -> Dict[str, Any]:
        task.start_execution()
        try:
            async with self.resource_semaphore:
                # #7430 Phase 2: if StrategyPlanner bound a skill at plan time
                # (#7268 Phase 1), dispatch via SkillRegistry instead of the
                # capability-based agent path. ADR-006 default: skill-bound
                # execution **replaces** agent dispatch — the skill is the
                # concrete implementation. Removed/disabled skill at execute
                # time fails the step (don't silently re-route at execute time;
                # plans should re-plan instead, per #7431 Q3).
                if task.skill_name:
                    return await self._dispatch_via_skill(task, context)
                agent = await self._agent_router.get_agent_instance(task.agent_type)
                if not agent:
                    raise Exception(f"Agent {task.agent_type} not available")
                enhanced_inputs = task.get_enhanced_inputs(context)
                result = await asyncio.wait_for(
                    agent.process_request({"action": task.action, "payload": enhanced_inputs}),
                    timeout=task.timeout_seconds,
                )
                task.complete_execution(result)
                self._perf.update(task.agent_type, True, task.get_execution_time())
                return task.to_completed_result(result)
        except asyncio.TimeoutError:
            return await self._handle_task_timeout(task, context)
        except Exception as e:
            return self._handle_task_exception(task, e)

    async def _dispatch_via_skill(self, task: AgentTask, context: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch task via the bound skill (#7430 Phase 2 of #7268 / ADR-006).

        Caller already holds ``self.resource_semaphore`` and called
        ``task.start_execution()``. We enforce the same timeout behavior as
        the legacy agent path so resource accounting + perf metrics stay
        consistent.

        Failure modes:
        - Skill not registered (or registered but disabled) → raise
          ``RuntimeError`` so the existing ``_handle_task_exception`` path
          surfaces it as a failed task. This is the explicit ADR-006 choice
          per #7431 Q3 — fail the step, don't re-route at execute time.
        - Skill ``execute`` raises → propagate up; same handler.
        - Skill ``execute`` times out → propagate ``asyncio.TimeoutError``;
          same handler.
        """
        # Lazy import — avoids circular dep if skills imports orchestration
        from skills.registry import get_skill_registry

        registry = get_skill_registry()
        skill = registry.get(task.skill_name)
        if skill is None:
            raise RuntimeError(
                f"Skill '{task.skill_name}' bound at plan time is not registered "
                f"(registry may have been mutated between plan and execute). "
                f"Failing step per ADR-006 'fail-don't-reroute' policy."
            )
        if not skill.enabled:
            raise RuntimeError(
                f"Skill '{task.skill_name}' is registered but disabled at execute time. "
                f"Failing step per ADR-006 'fail-don't-reroute' policy."
            )

        enhanced_inputs = task.get_enhanced_inputs(context)
        action = task.skill_action or "execute"
        result = await asyncio.wait_for(
            skill.execute(action, enhanced_inputs),
            timeout=task.timeout_seconds,
        )
        task.complete_execution(result)
        # Perf-tracker key uses skill_name — agent_type may still be set on
        # the task for legacy reasons but the actual dispatch was the skill.
        self._perf.update(f"skill:{task.skill_name}", True, task.get_execution_time())
        return task.to_completed_result(result)

    async def _publish_workflow_event(self, workflow_id: str, event_type: str, data: Dict[str, Any]) -> None:
        await _get_event_manager().publish(
            "workflow_event",
            {"workflow_id": workflow_id, "event_type": event_type, "timestamp": time.time(), "data": data},
        )
