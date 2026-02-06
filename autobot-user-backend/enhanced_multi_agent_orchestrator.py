# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Multi-Agent Orchestrator

Issue #381: This file has been refactored into the enhanced_orchestration/ package.
This thin facade maintains backward compatibility while delegating to focused modules.

See: src/enhanced_orchestration/
- types.py: Enums and dataclasses (AgentCapability, ExecutionStrategy, etc.)
- execution_strategies.py: Strategy implementations
- workflow_planning.py: Workflow planning and utilities

Advanced orchestration system with improved agent coordination, parallel execution,
intelligent task distribution, and collaborative workflows.
"""

import asyncio
import json
import logging
import time
from typing import Any, Dict, List, Optional, Set

from src.agents.agent_client import AgentRegistry as AgentClientRegistry
from src.agents.llm_failsafe_agent import get_robust_llm_response

# Re-export all public API from the package for backward compatibility
from src.enhanced_orchestration import (
    FALLBACK_TIERS,
    AgentCapability,
    AgentPerformance,
    AgentTask,
    ExecutionStrategy,
    ExecutionStrategyHandler,
    WorkflowPlan,
    WorkflowPlanner,
)
from src.event_manager import event_manager
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)

# Backward compatibility alias
_FALLBACK_TIERS = FALLBACK_TIERS

__all__ = [
    "AgentCapability",
    "ExecutionStrategy",
    "AgentTask",
    "WorkflowPlan",
    "AgentPerformance",
    "EnhancedMultiAgentOrchestrator",
    "enhanced_orchestrator",
    "create_and_execute_workflow",
    "FALLBACK_TIERS",
    "_FALLBACK_TIERS",
]


class EnhancedMultiAgentOrchestrator:
    """
    Advanced orchestration system for multi-agent coordination.

    Issue #381: Refactored to delegate to enhanced_orchestration package components.

    Features:
    - Intelligent task distribution based on agent capabilities
    - Parallel execution with dependency management
    - Dynamic strategy adaptation
    - Agent performance tracking and optimization
    - Collaborative workflows with agent communication
    - Fault tolerance and recovery
    - Resource optimization
    """

    def __init__(self):
        """Initialize the enhanced orchestrator"""
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # Redis for distributed coordination
        self.redis_client = get_redis_client(async_client=False)
        self.redis_async = get_redis_client(async_client=True)

        # Agent registry with capabilities
        self.agent_capabilities = {
            "research_agent": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
            "classification_agent": {
                AgentCapability.ANALYSIS,
                AgentCapability.VALIDATION,
            },
            "kb_librarian": {AgentCapability.RESEARCH, AgentCapability.SYNTHESIS},
            "system_commands": {AgentCapability.EXECUTION, AgentCapability.MONITORING},
            "security_scanner": {AgentCapability.SECURITY, AgentCapability.VALIDATION},
            "npu_code_search": {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
            "development_speedup": {
                AgentCapability.ANALYSIS,
                AgentCapability.OPTIMIZATION,
            },
            "json_formatter": {AgentCapability.VALIDATION, AgentCapability.SYNTHESIS},
            "llm_failsafe": {AgentCapability.SYNTHESIS},
        }

        # Performance tracking
        self.agent_performance: Dict[str, AgentPerformance] = {}
        for agent in self.agent_capabilities:
            self.agent_performance[agent] = AgentPerformance(agent_type=agent)

        # Active workflows
        self.active_workflows: Dict[str, WorkflowPlan] = {}
        self.task_queue = asyncio.Queue()
        self.running_tasks: Dict[str, AgentTask] = {}

        # Coordination channels
        self.coordination_prefix = "autobot:orchestrator:coord:"
        self.result_prefix = "autobot:orchestrator:results:"

        # Resource management
        self.max_parallel_tasks = 5
        self.resource_semaphore = asyncio.Semaphore(self.max_parallel_tasks)

        # Initialize planner and strategy handler
        self._planner = WorkflowPlanner(self.agent_capabilities)
        self._strategy_handler = None  # Lazy initialization

        # Agent client registry for actual agent instances
        self._agent_client_registry = AgentClientRegistry()

    def _get_strategy_handler(self) -> ExecutionStrategyHandler:
        """Lazy initialization of strategy handler."""
        if self._strategy_handler is None:
            self._strategy_handler = ExecutionStrategyHandler(
                max_parallel_tasks=self.max_parallel_tasks,
                resource_semaphore=self.resource_semaphore,
                execute_single_task=self._execute_single_task,
                topological_sort_tasks=self._planner.topological_sort_tasks,
                dependencies_met=self._planner.dependencies_met,
                group_pipeline_stages=self._planner.group_pipeline_stages,
                enhance_task_for_collaboration=self._planner.enhance_task_for_collaboration,
                coordinate_collaboration=self._coordinate_collaboration,
            )
        return self._strategy_handler

    def _build_planning_prompt(self, goal: str) -> str:
        """
        Build the LLM prompt for workflow planning (Issue #665: extracted helper).

        Args:
            goal: The user's goal to plan for

        Returns:
            Formatted planning prompt string
        """
        capabilities_json = json.dumps(
            {
                agent: [cap.value for cap in caps]
                for agent, caps in self.agent_capabilities.items()
            },
            indent=2,
        )

        return f"""
        You are an expert workflow planner. Analyze this goal and create an execution plan.

        Goal: {goal}

        Available agents and their capabilities:
        {capabilities_json}

        Create a workflow plan with:
        1. Required agents and their specific tasks
        2. Task dependencies (which tasks must complete before others)
        3. Execution strategy (sequential, parallel, pipeline, collaborative)
        4. Success criteria
        5. Estimated duration and resource requirements

        Respond in JSON format:
        {{
            "strategy": "parallel|sequential|pipeline|collaborative",
            "tasks": [
                {{
                    "agent": "agent_type",
                    "action": "specific_action",
                    "inputs": {{}},
                    "dependencies": ["task_ids"],
                    "priority": 1-10,
                    "capabilities_required": ["capability_names"]
                }}
            ],
            "success_criteria": ["criteria1", "criteria2"],
            "estimated_duration": 60.0,
            "resource_requirements": {{}}
        }}
        """

    def _parse_planning_response(self, response, goal: str) -> Dict[str, Any]:
        """
        Parse LLM planning response with fallback (Issue #665: extracted helper).

        Args:
            response: LLM response object
            goal: Original goal for fallback

        Returns:
            Parsed plan data dict
        """
        if response.tier_used.value in FALLBACK_TIERS:
            return self._planner.create_fallback_plan(goal)

        from src.agents.json_formatter_agent import json_formatter

        parse_result = json_formatter.parse_llm_response(response.content)

        if parse_result.success:
            return parse_result.data
        return self._planner.create_fallback_plan(goal)

    async def create_workflow_plan(
        self, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> WorkflowPlan:
        """
        Create an intelligent workflow plan for a goal.

        Issue #665: Refactored to use extracted helpers for prompt building
        and response parsing.

        Args:
            goal: The user's goal
            context: Optional context information

        Returns:
            Optimized workflow plan
        """
        self.logger.info("Creating workflow plan for: %s", goal)

        try:
            # Build prompt and get LLM response (Issue #665: uses helper)
            planning_prompt = self._build_planning_prompt(goal)
            response = await get_robust_llm_response(planning_prompt, context)

            # Parse the plan (Issue #665: uses helper)
            plan_data = self._parse_planning_response(response, goal)

            # Create workflow plan
            plan = self._planner.build_workflow_plan(goal, plan_data)

            # Store active workflow
            self.active_workflows[plan.plan_id] = plan

            return plan

        except Exception as e:
            self.logger.error("Failed to create workflow plan: %s", e)
            return self._planner.create_simple_workflow_plan(goal)

    async def _handle_workflow_success(
        self,
        plan: WorkflowPlan,
        results: Dict[str, Any],
        start_time: float,
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from execute_workflow to reduce function length.

        Handle successful workflow completion including metrics update and event publishing.
        """
        success = self._planner.check_success_criteria(plan, results)
        execution_time = time.time() - start_time

        await self._update_performance_metrics(plan, results, execution_time)

        await self._publish_workflow_event(
            plan.plan_id,
            "workflow_completed",
            {
                "success": success,
                "execution_time": execution_time,
                "results_summary": self._planner.summarize_results(results),
            },
        )

        return {
            "plan_id": plan.plan_id,
            "success": success,
            "results": results,
            "execution_time": execution_time,
            "strategy_used": plan.strategy.value,
        }

    async def _handle_workflow_failure(
        self,
        plan: WorkflowPlan,
        error: Exception,
        results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Issue #665: Extracted from execute_workflow to reduce function length.

        Handle workflow failure including fallback plan execution.
        """
        self.logger.error("Workflow execution failed: %s", error)

        if plan.fallback_plans:
            self.logger.info("Attempting fallback plan...")
            for fallback in plan.fallback_plans:
                try:
                    return await self.execute_workflow(fallback)
                except Exception as fallback_error:
                    self.logger.error("Fallback plan failed: %s", fallback_error)

        return {
            "plan_id": plan.plan_id,
            "success": False,
            "error": str(error),
            "results": results,
        }

    async def execute_workflow(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute a workflow plan with intelligent coordination."""
        self.logger.info(
            "Executing workflow %s with strategy: %s",
            plan.plan_id,
            plan.strategy.value,
        )

        start_time = time.time()
        results = {}

        try:
            # Publish workflow start event
            await self._publish_workflow_event(
                plan.plan_id,
                "workflow_started",
                {
                    "goal": plan.goal,
                    "strategy": plan.strategy.value,
                    "task_count": len(plan.tasks),
                },
            )

            # Execute using strategy handler
            results = await self._get_strategy_handler().execute_by_strategy(plan)

            # Handle success: metrics, events, and return result
            return await self._handle_workflow_success(plan, results, start_time)

        except Exception as e:
            return await self._handle_workflow_failure(plan, e, results)

    async def _handle_task_timeout(
        self, task: AgentTask, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Handle task timeout with retry logic.

        Issue #620.
        """
        task.fail_execution("Timeout")

        if task.can_retry():
            task.increment_retry()
            self.logger.warning(
                "Task %s timed out, retrying (%d/%d)",
                task.task_id,
                task.retry_count,
                task.max_retries,
            )
            return await self._execute_single_task(task, context)

        self._update_agent_performance(task.agent_type, False, task.timeout)
        return task.to_failed_result("Task execution timed out")

    def _handle_task_exception(
        self, task: AgentTask, error: Exception
    ) -> Dict[str, Any]:
        """
        Handle task execution exception.

        Issue #620.
        """
        task.fail_execution(str(error))
        execution_time = time.time() - (task.start_time or time.time())
        self._update_agent_performance(task.agent_type, False, execution_time)
        return task.to_failed_result(str(error))

    async def _execute_single_task(
        self, task: AgentTask, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single agent task. Issue #620: Refactored with helpers."""
        task.start_execution()

        try:
            async with self.resource_semaphore:
                agent = await self._get_agent_instance(task.agent_type)

                if not agent:
                    raise Exception(f"Agent {task.agent_type} not available")

                enhanced_inputs = task.get_enhanced_inputs(context)

                result = await asyncio.wait_for(
                    agent.process_request(
                        {"action": task.action, "payload": enhanced_inputs}
                    ),
                    timeout=task.timeout,
                )

                task.complete_execution(result)
                self._update_agent_performance(
                    task.agent_type, True, task.get_execution_time()
                )
                return task.to_completed_result(result)

        except asyncio.TimeoutError:
            return await self._handle_task_timeout(task, context)

        except Exception as e:
            return self._handle_task_exception(task, e)

    async def get_agent_recommendations(
        self, task_type: str, capabilities_needed: Set[AgentCapability]
    ) -> List[str]:
        """Get recommended agents for a task based on capabilities and performance."""
        suitable_agents = []

        for agent, caps in self.agent_capabilities.items():
            # Check if agent has required capabilities
            if capabilities_needed.issubset(caps):
                performance = self.agent_performance[agent]

                # Calculate suitability score
                reliability = performance.reliability_score
                capability_match = len(capabilities_needed.intersection(caps)) / len(
                    capabilities_needed
                )

                # Boost score for agents with relevant experience
                experience_boost = min(performance.total_tasks / 100, 1.0)

                score = (
                    (reliability * 0.5)
                    + (capability_match * 0.3)
                    + (experience_boost * 0.2)
                )

                suitable_agents.append((agent, score))

        # Sort by score
        suitable_agents.sort(key=lambda x: x[1], reverse=True)

        return [agent for agent, _ in suitable_agents]

    async def _coordinate_collaboration(self, plan: WorkflowPlan, collab_channel: str):
        """Coordinate inter-agent collaboration"""
        try:
            pubsub = self.redis_async.pubsub()
            await pubsub.subscribe(collab_channel)
            shared_context = {}

            async for message in pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    if data.get("type") == "share_insight":
                        agent = data.get("agent")
                        insight = data.get("insight")
                        shared_context[f"{agent}_insight"] = insight

                        # Broadcast to other agents
                        await self._broadcast_to_agents(
                            collab_channel,
                            {
                                "type": "context_update",
                                "shared_context": shared_context,
                            },
                        )
                except Exception as e:
                    self.logger.error("Collaboration coordination error: %s", e)

        except asyncio.CancelledError:
            await pubsub.unsubscribe(collab_channel)
            raise

    async def _broadcast_to_agents(self, channel: str, data: Dict[str, Any]):
        """Broadcast data to agents on collaboration channel"""
        await self.redis_async.publish(channel, json.dumps(data))

    async def _update_performance_metrics(
        self, plan: WorkflowPlan, results: Dict[str, Any], execution_time: float
    ):
        """Update agent performance metrics"""
        for task in plan.tasks:
            result = results.get(task.task_id, {})
            if result:
                agent_type = task.agent_type
                success = result.get("status") == "completed"
                task_time = result.get("execution_time", 0)

                self._update_agent_performance(agent_type, success, task_time)

    def _update_agent_performance(
        self, agent_type: str, success: bool, execution_time: float
    ):
        """Update performance metrics for an agent"""
        if agent_type in self.agent_performance:
            perf = self.agent_performance[agent_type]

            perf.total_tasks += 1
            if success:
                perf.successful_tasks += 1
            else:
                perf.failed_tasks += 1

            # Update average execution time
            perf.average_execution_time = (
                perf.average_execution_time * (perf.total_tasks - 1) + execution_time
            ) / perf.total_tasks

            # Update reliability score
            perf.reliability_score = perf.successful_tasks / perf.total_tasks

            perf.last_update = time.time()

    async def _publish_workflow_event(
        self, workflow_id: str, event_type: str, data: Dict[str, Any]
    ):
        """Publish workflow event"""
        await event_manager.publish(
            "workflow_event",
            {
                "workflow_id": workflow_id,
                "event_type": event_type,
                "timestamp": time.time(),
                "data": data,
            },
        )

    async def _get_agent_instance(self, agent_type: str):
        """
        Get agent instance dynamically from the agent registry.

        Args:
            agent_type: The type of agent to retrieve

        Returns:
            Agent instance if found and available, None otherwise
        """
        # First, try to get from agent client registry
        agent = self._agent_client_registry.get_agent(agent_type)

        if agent is not None:
            # Update health status before returning
            await self._agent_client_registry.update_agent_health(agent_type)
            return agent

        # Agent not registered - log and return None
        # The caller already handles None case with proper error
        self.logger.warning(
            "Agent '%s' not found in registry. Available agents: %s",
            agent_type,
            self._agent_client_registry.list_agents(),
        )
        return None

    def get_performance_report(self) -> Dict[str, Any]:
        """Get comprehensive performance report"""
        return {
            "agent_performance": {
                agent: {
                    "total_tasks": perf.total_tasks,
                    "success_rate": perf.reliability_score,
                    "average_time": perf.average_execution_time,
                    "last_update": perf.last_update,
                }
                for agent, perf in self.agent_performance.items()
            },
            "active_workflows": len(self.active_workflows),
            "capabilities_coverage": self._calculate_capability_coverage(),
        }

    def _calculate_capability_coverage(self) -> Dict[str, float]:
        """Calculate coverage for each capability across agents"""
        coverage = {}

        for capability in AgentCapability:
            agents_with_cap = sum(
                1 for caps in self.agent_capabilities.values() if capability in caps
            )
            coverage[capability.value] = agents_with_cap / len(self.agent_capabilities)

        return coverage


# Global instance for easy access
enhanced_orchestrator = EnhancedMultiAgentOrchestrator()


async def create_and_execute_workflow(
    goal: str, context: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Convenience function to create and execute a workflow.

    Args:
        goal: The user's goal
        context: Optional context

    Returns:
        Execution results
    """
    plan = await enhanced_orchestrator.create_workflow_plan(goal, context)
    return await enhanced_orchestrator.execute_workflow(plan)
