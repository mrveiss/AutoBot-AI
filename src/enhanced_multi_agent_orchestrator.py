# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Enhanced Multi-Agent Orchestrator

Advanced orchestration system with improved agent coordination, parallel execution,
intelligent task distribution, and collaborative workflows.
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from src.agents.llm_failsafe_agent import get_robust_llm_response
from src.autobot_types import TaskComplexity
from src.constants.network_constants import NetworkConstants
from src.event_manager import event_manager
from src.utils.redis_client import get_redis_client

logger = logging.getLogger(__name__)


class AgentCapability(Enum):
    """Core agent capabilities"""

    RESEARCH = "research"
    ANALYSIS = "analysis"
    EXECUTION = "execution"
    MONITORING = "monitoring"
    SYNTHESIS = "synthesis"
    VALIDATION = "validation"
    OPTIMIZATION = "optimization"
    SECURITY = "security"


class ExecutionStrategy(Enum):
    """Task execution strategies"""

    SEQUENTIAL = "sequential"  # One after another
    PARALLEL = "parallel"  # All at once
    PIPELINE = "pipeline"  # Output feeds next input
    COLLABORATIVE = "collaborative"  # Agents work together
    ADAPTIVE = "adaptive"  # Strategy changes based on progress


@dataclass
class AgentTask:
    """Enhanced task definition for agents"""

    task_id: str
    agent_type: str
    action: str
    inputs: Dict[str, Any]
    dependencies: List[str] = field(default_factory=list)  # Task IDs this depends on
    priority: int = 5  # 1-10, higher is more important
    timeout: float = 60.0
    retry_count: int = 0
    max_retries: int = 3
    capabilities_required: Set[AgentCapability] = field(default_factory=set)
    outputs: Optional[Dict[str, Any]] = None
    status: str = "pending"  # pending, running, completed, failed
    error: Optional[str] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class WorkflowPlan:
    """Enhanced workflow execution plan"""

    plan_id: str
    goal: str
    strategy: ExecutionStrategy
    tasks: List[AgentTask]
    dependencies_graph: Dict[str, List[str]]  # task_id -> [dependency_ids]
    estimated_duration: float
    resource_requirements: Dict[str, Any]
    success_criteria: List[str]
    fallback_plans: List["WorkflowPlan"] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentPerformance:
    """Track agent performance metrics"""

    agent_type: str
    total_tasks: int = 0
    successful_tasks: int = 0
    failed_tasks: int = 0
    average_execution_time: float = 0.0
    reliability_score: float = 1.0  # 0-1
    capability_scores: Dict[AgentCapability, float] = field(default_factory=dict)
    last_update: float = field(default_factory=time.time)


class EnhancedMultiAgentOrchestrator:
    """
    Advanced orchestration system for multi-agent coordination.

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

    async def create_workflow_plan(
        self, goal: str, context: Optional[Dict[str, Any]] = None
    ) -> WorkflowPlan:
        """
        Create an intelligent workflow plan for a goal.

        Args:
            goal: The user's goal
            context: Optional context information

        Returns:
            Optimized workflow plan
        """
        self.logger.info(f"Creating workflow plan for: {goal}")

        # Use LLM to analyze the goal and create a plan
        planning_prompt = f"""
        You are an expert workflow planner. Analyze this goal and create an execution plan.

        Goal: {goal}

        Available agents and their capabilities:
        {json.dumps({agent: [cap.value for cap in caps] for agent, caps in self.agent_capabilities.items()}, indent=2)}

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

        try:
            # Get robust LLM response
            response = await get_robust_llm_response(planning_prompt, context)

            # Parse the plan
            if response.tier_used.value in ["basic", "emergency"]:
                # Fallback to simple sequential plan
                plan_data = self._create_fallback_plan(goal)
            else:
                # Parse LLM response
                from src.agents.json_formatter_agent import json_formatter

                parse_result = json_formatter.parse_llm_response(response.content)

                if parse_result.success:
                    plan_data = parse_result.data
                else:
                    plan_data = self._create_fallback_plan(goal)

            # Create workflow plan
            plan = self._build_workflow_plan(goal, plan_data)

            # Store active workflow
            self.active_workflows[plan.plan_id] = plan

            return plan

        except Exception as e:
            self.logger.error(f"Failed to create workflow plan: {e}")
            # Return simple fallback plan
            return self._create_simple_workflow_plan(goal)

    async def execute_workflow(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """
        Execute a workflow plan with intelligent coordination.

        Args:
            plan: The workflow plan to execute

        Returns:
            Execution results
        """
        self.logger.info(
            f"Executing workflow {plan.plan_id} with strategy: {plan.strategy.value}"
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

            # Execute based on strategy
            if plan.strategy == ExecutionStrategy.SEQUENTIAL:
                results = await self._execute_sequential(plan)
            elif plan.strategy == ExecutionStrategy.PARALLEL:
                results = await self._execute_parallel(plan)
            elif plan.strategy == ExecutionStrategy.PIPELINE:
                results = await self._execute_pipeline(plan)
            elif plan.strategy == ExecutionStrategy.COLLABORATIVE:
                results = await self._execute_collaborative(plan)
            else:  # ADAPTIVE
                results = await self._execute_adaptive(plan)

            # Check success criteria
            success = self._check_success_criteria(plan, results)

            execution_time = time.time() - start_time

            # Update performance metrics
            await self._update_performance_metrics(plan, results, execution_time)

            # Publish completion event
            await self._publish_workflow_event(
                plan.plan_id,
                "workflow_completed",
                {
                    "success": success,
                    "execution_time": execution_time,
                    "results_summary": self._summarize_results(results),
                },
            )

            return {
                "plan_id": plan.plan_id,
                "success": success,
                "results": results,
                "execution_time": execution_time,
                "strategy_used": plan.strategy.value,
            }

        except Exception as e:
            self.logger.error(f"Workflow execution failed: {e}")

            # Try fallback plans
            if plan.fallback_plans:
                self.logger.info("Attempting fallback plan...")
                for fallback in plan.fallback_plans:
                    try:
                        return await self.execute_workflow(fallback)
                    except Exception as fallback_error:
                        self.logger.error(f"Fallback plan failed: {fallback_error}")
                        continue

            # All plans failed
            return {
                "plan_id": plan.plan_id,
                "success": False,
                "error": str(e),
                "results": results,
            }

    async def _execute_sequential(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks sequentially"""
        results = {}

        # Sort tasks by dependencies and priority
        sorted_tasks = self._topological_sort_tasks(plan.tasks, plan.dependencies_graph)

        for task in sorted_tasks:
            self.logger.info(f"Executing task {task.task_id} ({task.agent_type})")

            # Wait for dependencies
            await self._wait_for_dependencies(task, results)

            # Execute task
            result = await self._execute_single_task(task, results)
            results[task.task_id] = result

            # Check if we should continue
            if result.get("status") == "failed" and not task.metadata.get(
                "optional", False
            ):
                self.logger.error(
                    f"Required task {task.task_id} failed, stopping workflow"
                )
                break

        return results

    async def _execute_parallel(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute independent tasks in parallel"""
        results = {}
        pending_tasks = list(plan.tasks)
        running_tasks = []

        while pending_tasks or running_tasks:
            # Start tasks that have their dependencies met
            ready_tasks = []
            for task in pending_tasks[:]:
                if self._dependencies_met(task, results):
                    ready_tasks.append(task)
                    pending_tasks.remove(task)

            # Start ready tasks (respecting resource limits)
            for task in ready_tasks:
                if len(running_tasks) < self.max_parallel_tasks:
                    self.logger.info(f"Starting parallel task {task.task_id}")
                    task_future = asyncio.create_task(
                        self._execute_single_task(task, results)
                    )
                    running_tasks.append((task, task_future))

            # Wait for any task to complete
            if running_tasks:
                done, pending = await asyncio.wait(
                    [future for _, future in running_tasks],
                    return_when=asyncio.FIRST_COMPLETED,
                )

                # Process completed tasks
                for task, future in running_tasks[:]:
                    if future in done:
                        result = await future
                        results[task.task_id] = result
                        running_tasks.remove((task, future))
                        self.logger.info(f"Completed parallel task {task.task_id}")
            else:
                # No tasks running, wait a bit
                await asyncio.sleep(0.1)

        return results

    async def _execute_pipeline(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks in pipeline mode where outputs feed into next inputs"""
        results = {}

        # Group tasks into pipeline stages
        stages = self._group_pipeline_stages(plan.tasks, plan.dependencies_graph)

        pipeline_data = {}
        for stage_num, stage_tasks in enumerate(stages):
            self.logger.info(f"Executing pipeline stage {stage_num + 1}/{len(stages)}")

            # Execute stage tasks in parallel
            stage_results = await asyncio.gather(
                *[
                    self._execute_single_task(task, {**results, **pipeline_data})
                    for task in stage_tasks
                ]
            )

            # Collect results and prepare pipeline data for next stage
            for task, result in zip(stage_tasks, stage_results):
                results[task.task_id] = result

                # Extract outputs for pipeline
                if result.get("status") == "completed" and "output" in result:
                    pipeline_data.update(result["output"])

        return results

    async def _execute_collaborative(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute tasks collaboratively with inter-agent communication"""
        results = {}

        # Create collaboration channels
        collab_channel = f"{self.coordination_prefix}collab:{plan.plan_id}"

        # Start collaboration coordinator
        coordinator_task = asyncio.create_task(
            self._coordinate_collaboration(plan, collab_channel)
        )

        # Execute tasks with collaboration
        task_futures = []
        for task in plan.tasks:
            enhanced_task = self._enhance_task_for_collaboration(task, collab_channel)
            future = asyncio.create_task(
                self._execute_single_task(enhanced_task, results)
            )
            task_futures.append((task, future))

        # Wait for all tasks
        for task, future in task_futures:
            result = await future
            results[task.task_id] = result

        # Stop coordinator
        coordinator_task.cancel()

        return results

    async def _execute_adaptive(self, plan: WorkflowPlan) -> Dict[str, Any]:
        """Execute with adaptive strategy that changes based on progress"""
        results = {}

        # Start with initial strategy
        current_strategy = plan.strategy

        # Monitor progress and adapt
        completed_tasks = 0
        failed_tasks = 0

        pending_tasks = list(plan.tasks)

        while pending_tasks:
            # Analyze current state
            progress_ratio = completed_tasks / len(plan.tasks)
            failure_ratio = failed_tasks / max(completed_tasks, 1)

            # Adapt strategy based on progress
            if failure_ratio > 0.3:
                # Too many failures, switch to sequential for debugging
                current_strategy = ExecutionStrategy.SEQUENTIAL
                self.logger.info("Adapting to SEQUENTIAL due to high failure rate")
            elif progress_ratio > 0.7 and failure_ratio < 0.1:
                # Good progress, low failures, maximize parallelism
                current_strategy = ExecutionStrategy.PARALLEL
                self.logger.info("Adapting to PARALLEL due to good progress")

            # Execute next batch with current strategy
            if current_strategy == ExecutionStrategy.PARALLEL:
                # Execute multiple tasks
                batch_size = min(self.max_parallel_tasks, len(pending_tasks))
                batch_tasks = pending_tasks[:batch_size]

                batch_results = await asyncio.gather(
                    *[
                        self._execute_single_task(task, results)
                        for task in batch_tasks
                        if self._dependencies_met(task, results)
                    ]
                )

                for task, result in zip(batch_tasks, batch_results):
                    results[task.task_id] = result
                    pending_tasks.remove(task)

                    if result.get("status") == "completed":
                        completed_tasks += 1
                    else:
                        failed_tasks += 1
            else:
                # Sequential execution
                for task in pending_tasks[:]:
                    if self._dependencies_met(task, results):
                        result = await self._execute_single_task(task, results)
                        results[task.task_id] = result
                        pending_tasks.remove(task)

                        if result.get("status") == "completed":
                            completed_tasks += 1
                        else:
                            failed_tasks += 1
                        break

        return results

    async def _execute_single_task(
        self, task: AgentTask, context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute a single agent task"""
        task.start_time = time.time()
        task.status = "running"

        try:
            # Acquire resource semaphore
            async with self.resource_semaphore:
                # Get agent implementation
                agent = await self._get_agent_instance(task.agent_type)

                if not agent:
                    raise Exception(f"Agent {task.agent_type} not available")

                # Prepare inputs with context
                enhanced_inputs = {
                    **task.inputs,
                    "context": context,
                    "task_id": task.task_id,
                    "workflow_metadata": task.metadata,
                }

                # Execute with timeout
                result = await asyncio.wait_for(
                    agent.process_request(
                        {"action": task.action, "payload": enhanced_inputs}
                    ),
                    timeout=task.timeout,
                )

                task.end_time = time.time()
                task.status = "completed"
                task.outputs = result

                # Update performance metrics
                self._update_agent_performance(
                    task.agent_type, True, task.end_time - task.start_time
                )

                return {
                    "status": "completed",
                    "output": result,
                    "execution_time": task.end_time - task.start_time,
                    "agent": task.agent_type,
                }

        except asyncio.TimeoutError:
            task.status = "failed"
            task.error = "Timeout"

            # Retry logic
            if task.retry_count < task.max_retries:
                task.retry_count += 1
                self.logger.warning(
                    f"Task {task.task_id} timed out, retrying ({task.retry_count}/{task.max_retries})"
                )
                return await self._execute_single_task(task, context)

            self._update_agent_performance(task.agent_type, False, task.timeout)

            return {
                "status": "failed",
                "error": "Task execution timed out",
                "agent": task.agent_type,
            }

        except Exception as e:
            task.status = "failed"
            task.error = str(e)

            self._update_agent_performance(
                task.agent_type, False, time.time() - task.start_time
            )

            return {"status": "failed", "error": str(e), "agent": task.agent_type}

    async def get_agent_recommendations(
        self, task_type: str, capabilities_needed: Set[AgentCapability]
    ) -> List[str]:
        """
        Get recommended agents for a task based on capabilities and performance.

        Args:
            task_type: Type of task
            capabilities_needed: Required capabilities

        Returns:
            Ranked list of suitable agents
        """
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

    def _build_workflow_plan(
        self, goal: str, plan_data: Dict[str, Any]
    ) -> WorkflowPlan:
        """Build workflow plan from parsed data"""
        plan_id = str(uuid.uuid4())

        # Create tasks
        tasks = []
        dependencies_graph = {}

        for i, task_data in enumerate(plan_data.get("tasks", [])):
            task_id = f"{plan_id}_task_{i}"

            # Determine required capabilities
            caps_required = set()
            for cap_name in task_data.get("capabilities_required", []):
                try:
                    caps_required.add(AgentCapability(cap_name))
                except ValueError:
                    pass

            task = AgentTask(
                task_id=task_id,
                agent_type=task_data.get("agent", "orchestrator"),
                action=task_data.get("action", "process"),
                inputs=task_data.get("inputs", {}),
                dependencies=task_data.get("dependencies", []),
                priority=task_data.get("priority", 5),
                capabilities_required=caps_required,
            )

            tasks.append(task)
            dependencies_graph[task_id] = task.dependencies

        # Determine strategy
        strategy_name = plan_data.get("strategy", "sequential")
        try:
            strategy = ExecutionStrategy(strategy_name)
        except ValueError:
            strategy = ExecutionStrategy.SEQUENTIAL

        return WorkflowPlan(
            plan_id=plan_id,
            goal=goal,
            strategy=strategy,
            tasks=tasks,
            dependencies_graph=dependencies_graph,
            estimated_duration=plan_data.get("estimated_duration", 60.0),
            resource_requirements=plan_data.get("resource_requirements", {}),
            success_criteria=plan_data.get("success_criteria", ["All tasks completed"]),
        )

    def _create_fallback_plan(self, goal: str) -> Dict[str, Any]:
        """Create a simple fallback plan"""
        return {
            "strategy": "sequential",
            "tasks": [
                {
                    "agent": "classification_agent",
                    "action": "classify_request",
                    "inputs": {"message": goal},
                    "dependencies": [],
                    "priority": 8,
                },
                {
                    "agent": "orchestrator",
                    "action": "process_goal",
                    "inputs": {"goal": goal},
                    "dependencies": [],
                    "priority": 5,
                },
            ],
            "success_criteria": ["Goal processed"],
            "estimated_duration": 30.0,
            "resource_requirements": {},
        }

    def _create_simple_workflow_plan(self, goal: str) -> WorkflowPlan:
        """Create a simple sequential workflow plan"""
        plan_id = str(uuid.uuid4())

        return WorkflowPlan(
            plan_id=plan_id,
            goal=goal,
            strategy=ExecutionStrategy.SEQUENTIAL,
            tasks=[
                AgentTask(
                    task_id=f"{plan_id}_task_0",
                    agent_type="orchestrator",
                    action="process_goal",
                    inputs={"goal": goal},
                    priority=5,
                )
            ],
            dependencies_graph={},
            estimated_duration=30.0,
            resource_requirements={},
            success_criteria=["Task completed"],
        )

    def _topological_sort_tasks(
        self, tasks: List[AgentTask], dependencies: Dict[str, List[str]]
    ) -> List[AgentTask]:
        """Sort tasks based on dependencies"""
        # Create task lookup
        task_map = {task.task_id: task for task in tasks}

        # Kahn's algorithm for topological sort
        in_degree = {task.task_id: 0 for task in tasks}
        for deps in dependencies.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        queue = [task_id for task_id, degree in in_degree.items() if degree == 0]
        sorted_tasks = []

        while queue:
            # Sort by priority within same dependency level
            queue.sort(key=lambda tid: task_map[tid].priority, reverse=True)

            task_id = queue.pop(0)
            sorted_tasks.append(task_map[task_id])

            # Reduce in-degree for dependent tasks
            for other_id, deps in dependencies.items():
                if task_id in deps:
                    in_degree[other_id] -= 1
                    if in_degree[other_id] == 0:
                        queue.append(other_id)

        # Add any remaining tasks (cycles)
        for task in tasks:
            if task not in sorted_tasks:
                sorted_tasks.append(task)

        return sorted_tasks

    def _dependencies_met(self, task: AgentTask, results: Dict[str, Any]) -> bool:
        """Check if task dependencies are met"""
        for dep_id in task.dependencies:
            if dep_id not in results or results[dep_id].get("status") != "completed":
                return False
        return True

    async def _wait_for_dependencies(self, task: AgentTask, results: Dict[str, Any]):
        """Wait for task dependencies to complete"""
        while not self._dependencies_met(task, results):
            await asyncio.sleep(0.5)

    def _group_pipeline_stages(
        self, tasks: List[AgentTask], dependencies: Dict[str, List[str]]
    ) -> List[List[AgentTask]]:
        """Group tasks into pipeline stages"""
        stages = []
        processed = set()

        while len(processed) < len(tasks):
            # Find tasks that can run in current stage
            stage_tasks = []
            for task in tasks:
                if task.task_id not in processed:
                    # Check if all dependencies are in previous stages
                    deps_satisfied = all(dep in processed for dep in task.dependencies)
                    if deps_satisfied:
                        stage_tasks.append(task)

            if not stage_tasks:
                # Circular dependency or error
                # Add remaining tasks as final stage
                stage_tasks = [t for t in tasks if t.task_id not in processed]

            stages.append(stage_tasks)
            processed.update(t.task_id for t in stage_tasks)

        return stages

    def _enhance_task_for_collaboration(
        self, task: AgentTask, collab_channel: str
    ) -> AgentTask:
        """Enhance task with collaboration metadata"""
        task.metadata["collaboration_channel"] = collab_channel
        task.metadata["enable_sharing"] = True
        return task

    async def _coordinate_collaboration(self, plan: WorkflowPlan, collab_channel: str):
        """Coordinate inter-agent collaboration"""
        try:
            # Monitor collaboration channel
            pubsub = self.redis_async.pubsub()
            await pubsub.subscribe(collab_channel)

            shared_context = {}

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])

                        # Update shared context
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
                        self.logger.error(f"Collaboration coordination error: {e}")

        except asyncio.CancelledError:
            await pubsub.unsubscribe(collab_channel)
            raise

    async def _broadcast_to_agents(self, channel: str, data: Dict[str, Any]):
        """Broadcast data to agents on collaboration channel"""
        await self.redis_async.publish(channel, json.dumps(data))

    def _check_success_criteria(
        self, plan: WorkflowPlan, results: Dict[str, Any]
    ) -> bool:
        """Check if workflow met success criteria"""
        # Basic check: all non-optional tasks completed
        for task in plan.tasks:
            if not task.metadata.get("optional", False):
                result = results.get(task.task_id, {})
                if result.get("status") != "completed":
                    return False

        # TODO: Implement custom success criteria checking

        return True

    def _summarize_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize workflow results"""
        completed = sum(1 for r in results.values() if r.get("status") == "completed")
        failed = sum(1 for r in results.values() if r.get("status") == "failed")

        return {
            "total_tasks": len(results),
            "completed": completed,
            "failed": failed,
            "success_rate": completed / max(len(results), 1),
        }

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
        """Get agent instance dynamically"""

        # This would be implemented to actually get agent instances
        # For now, return a mock that processes requests
        class MockAgent:
            async def process_request(self, request):
                await asyncio.sleep(0.5)  # Simulate work
                return {"result": f"Processed by {agent_type}"}

        return MockAgent()

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
