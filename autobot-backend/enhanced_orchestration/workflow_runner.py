# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Multi-agent workflow execution engine extracted from Orchestrator (#5058)."""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional, Set

from autobot_shared.logging_manager import get_logger
from autobot_shared.redis_client import get_async_redis_client
from enhanced_orchestration.execution_strategies import ExecutionStrategyHandler
from enhanced_orchestration.success_criteria import SuccessCriteriaEvaluator
from enhanced_orchestration.types import AgentTask, WorkflowPlan
from enhanced_orchestration.workflow_planning import WorkflowPlanner as StrategyPlanner
from event_manager import get_event_manager as _get_event_manager
from orchestration import AgentCapability
from orchestration.performance_tracker import PerformanceTracker

logger = get_logger("workflow_runner")


class WorkflowRunner:
    """Executes WorkflowPlan objects via the multi-agent strategy engine.

    Houses all execution-engine methods that were previously inlined in
    Orchestrator.  Orchestrator instantiates one WorkflowRunner and delegates
    execute_workflow / get_agent_recommendations / get_performance_report to it.
    """

    def __init__(
        self,
        strategy_planner: StrategyPlanner,
        agent_capabilities: Dict[str, Set],
        performance_tracker: PerformanceTracker,
        active_workflows: Dict[str, WorkflowPlan],
        max_parallel_tasks: int = 5,
    ) -> None:
        self._strategy_planner = strategy_planner
        self.agent_capabilities = agent_capabilities
        self._perf = performance_tracker
        self.active_workflows = active_workflows
        self.max_parallel_tasks = max_parallel_tasks
        self.resource_semaphore: asyncio.Semaphore = asyncio.Semaphore(max_parallel_tasks)
        self._redis_async = None
        self._strategy_handler: Optional[ExecutionStrategyHandler] = None

        from agents.agent_client import AgentRegistry as AgentClientRegistry
        self._agent_client_registry = AgentClientRegistry()

    # ------------------------------------------------------------------ helpers

    async def _ensure_redis(self) -> None:
        """Lazy-init async Redis client for collaboration channels (#2725)."""
        if self._redis_async is None:
            self._redis_async = await get_async_redis_client()
        if self._redis_async is None:
            raise RuntimeError("Redis unavailable — collaboration channel requires Redis")

    def _get_strategy_handler(self) -> ExecutionStrategyHandler:
        if self._strategy_handler is None:
            self._strategy_handler = ExecutionStrategyHandler(
                max_parallel_tasks=self.max_parallel_tasks,
                resource_semaphore=self.resource_semaphore,
                execute_single_task=self._execute_single_agent_task,
                topological_sort_tasks=self._strategy_planner.topological_sort_tasks,
                dependencies_met=self._strategy_planner.dependencies_met,
                group_pipeline_stages=self._strategy_planner.group_pipeline_stages,
                enhance_task_for_collaboration=self._strategy_planner.enhance_task_for_collaboration,
                coordinate_collaboration=self._coordinate_collaboration,
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

    async def get_agent_recommendations(
        self, capabilities_needed: Set
    ) -> List[str]:
        suitable = []
        for agent, caps in self.agent_capabilities.items():
            if not capabilities_needed.issubset(caps):
                continue
            perf = self._perf.agent_performance.get(agent)
            if perf is None:
                continue
            score = (
                perf.reliability_score * 0.5
                + len(capabilities_needed.intersection(caps)) / len(capabilities_needed) * 0.3
                + min(perf.total_tasks / 100, 1.0) * 0.2
            )
            suitable.append((agent, score))
        suitable.sort(key=lambda x: x[1], reverse=True)
        return [a for a, _ in suitable]

    def get_performance_report(self) -> Dict[str, Any]:
        return {
            "agent_performance": self._perf.report(),
            "active_workflows": len(self.active_workflows),
            "capabilities_coverage": self._calculate_capability_coverage(),
        }

    # ------------------------------------------------------ execution internals

    async def _evaluate_workflow_criteria(
        self, plan: WorkflowPlan, results: Dict[str, Any]
    ) -> Dict[str, Any]:
        if plan.structured_criteria:
            evaluator = SuccessCriteriaEvaluator()
            eval_result = await evaluator.evaluate(plan.structured_criteria, results)
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
        for fallback in (plan.fallback_plans or []):
            try:
                return await self.execute_workflow(fallback, _depth + 1)
            except Exception as fe:
                logger.error("Fallback plan failed: %s", fe)
        return {"plan_id": plan.plan_id, "success": False, "error": str(error), "results": results}

    async def _handle_task_timeout(
        self, task: AgentTask, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        task.fail_execution("Timeout")
        if task.can_retry():
            task.increment_retry()
            logger.warning(
                "Task %s timed out, retrying (%d/%d)",
                task.task_id, task.retry_count, task.max_retries,
            )
            return await self._execute_single_agent_task(task, context)
        self._perf.update(task.agent_type, False, time.time() - (task.start_time or time.time()))
        return task.to_failed_result("Task execution timed out")

    def _handle_task_exception(self, task: AgentTask, error: Exception) -> Dict[str, Any]:
        task.fail_execution(str(error))
        execution_time = time.time() - (task.start_time or time.time())
        self._perf.update(task.agent_type, False, execution_time)
        return task.to_failed_result(str(error))

    async def _execute_single_agent_task(
        self, task: AgentTask, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        task.start_execution()
        try:
            async with self.resource_semaphore:
                agent = await self._get_agent_instance(task.agent_type)
                if not agent:
                    raise Exception(f"Agent {task.agent_type} not available")
                enhanced_inputs = task.get_enhanced_inputs(context)
                result = await asyncio.wait_for(
                    agent.process_request({"action": task.action, "payload": enhanced_inputs}),
                    timeout=task.timeout,
                )
                task.complete_execution(result)
                self._perf.update(task.agent_type, True, task.get_execution_time())
                return task.to_completed_result(result)
        except asyncio.TimeoutError:
            return await self._handle_task_timeout(task, context)
        except Exception as e:
            return self._handle_task_exception(task, e)

    async def _coordinate_collaboration(
        self, plan: WorkflowPlan, collab_channel: str
    ) -> None:
        await self._ensure_redis()
        try:
            pubsub = self._redis_async.pubsub()
            await pubsub.subscribe(collab_channel)
            shared_context: Dict[str, Any] = {}
            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue
                try:
                    data = json.loads(message["data"])
                except json.JSONDecodeError as e:
                    logger.error("Collaboration message decode error: %s", e)
                    continue
                if data.get("type") == "share_insight":
                    shared_context[f"{data.get('agent')}_insight"] = data.get("insight")
                    await self._broadcast_to_agents(
                        collab_channel,
                        {"type": "context_update", "shared_context": shared_context},
                    )
        except asyncio.CancelledError:
            await pubsub.unsubscribe(collab_channel)
            raise

    async def _broadcast_to_agents(self, channel: str, data: Dict[str, Any]) -> None:
        await self._ensure_redis()
        await self._redis_async.publish(channel, json.dumps(data))

    async def _publish_workflow_event(
        self, workflow_id: str, event_type: str, data: Dict[str, Any]
    ) -> None:
        await _get_event_manager().publish(
            "workflow_event",
            {"workflow_id": workflow_id, "event_type": event_type, "timestamp": time.time(), "data": data},
        )

    async def _get_agent_instance(self, agent_type: str) -> Optional[Any]:
        agent = self._agent_client_registry.get_agent(agent_type)
        if agent is not None:
            await self._agent_client_registry.update_agent_health(agent_type)
            return agent
        logger.warning(
            "Agent '%s' not found. Available: %s",
            agent_type, self._agent_client_registry.list_agents(),
        )
        return None

    def _calculate_capability_coverage(self) -> Dict[str, float]:
        coverage: Dict[str, float] = {}
        n_agents = max(len(self.agent_capabilities), 1)
        for capability in AgentCapability:
            agents_with_cap = sum(
                1 for caps in self.agent_capabilities.values() if capability in caps
            )
            coverage[capability.value] = agents_with_cap / n_agents
        return coverage
