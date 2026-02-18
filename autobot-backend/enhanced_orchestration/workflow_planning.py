# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Planning Module

Issue #381: Extracted from enhanced_multi_agent_orchestrator.py god class refactoring.
Contains workflow planning, building, and utility functions.
"""

import logging
import re
import uuid
from typing import Any, Dict, List, Set

from .types import AgentCapability, AgentTask, ExecutionStrategy, WorkflowPlan

logger = logging.getLogger(__name__)


class WorkflowPlanner:
    """Handles workflow plan creation and task management."""

    def __init__(self, agent_capabilities: Dict[str, Set[AgentCapability]]):
        """
        Initialize workflow planner.

        Args:
            agent_capabilities: Mapping of agent types to their capabilities
        """
        self.agent_capabilities = agent_capabilities

    def build_workflow_plan(self, goal: str, plan_data: Dict[str, Any]) -> WorkflowPlan:
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
                    logger.debug("Unknown capability %s, skipping", cap_name)

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

    def create_fallback_plan(self, goal: str) -> Dict[str, Any]:
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

    def create_simple_workflow_plan(self, goal: str) -> WorkflowPlan:
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

    def topological_sort_tasks(
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

    def dependencies_met(self, task: AgentTask, results: Dict[str, Any]) -> bool:
        """Check if task dependencies are met"""
        for dep_id in task.dependencies:
            if dep_id not in results or results[dep_id].get("status") != "completed":
                return False
        return True

    def group_pipeline_stages(
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
                # Circular dependency or error - add remaining tasks as final stage
                stage_tasks = [t for t in tasks if t.task_id not in processed]

            stages.append(stage_tasks)
            processed.update(t.task_id for t in stage_tasks)

        return stages

    def enhance_task_for_collaboration(
        self, task: AgentTask, collab_channel: str
    ) -> AgentTask:
        """Enhance task with collaboration metadata"""
        task.metadata["collaboration_channel"] = collab_channel
        task.metadata["enable_sharing"] = True
        return task

    def check_success_criteria(
        self, plan: WorkflowPlan, results: Dict[str, Any]
    ) -> bool:
        """Check if workflow met success criteria"""
        # Basic check: all non-optional tasks completed
        for task in plan.tasks:
            if not task.metadata.get("optional", False):
                result = results.get(task.task_id, {})
                if result.get("status") != "completed":
                    return False

        # Check custom success criteria from the plan
        if plan.success_criteria:
            for criterion in plan.success_criteria:
                if not self.evaluate_success_criterion(criterion, results):
                    logger.warning("Success criterion not met: %s", criterion)
                    return False

        return True

    def evaluate_success_criterion(
        self, criterion: str, results: Dict[str, Any]
    ) -> bool:
        """
        Evaluate a single success criterion against workflow results.

        Supports these criterion patterns:
        - "All tasks completed" - All tasks must have status 'completed'
        - "No failures" - No task should have status 'failed'
        - "Success rate >= X%" - At least X% of tasks must complete
        - "Task:<task_id> completed" - Specific task must complete
        - Default: Returns True (unknown criteria are considered met)
        """
        criterion_lower = criterion.lower().strip()

        # Pattern: "All tasks completed"
        if "all tasks completed" in criterion_lower:
            return all(r.get("status") == "completed" for r in results.values())

        # Pattern: "No failures"
        if "no failure" in criterion_lower:
            return not any(r.get("status") == "failed" for r in results.values())

        # Pattern: "Success rate >= X%"
        if "success rate" in criterion_lower and ">=" in criterion_lower:
            match = re.search(r"(\d+(?:\.\d+)?)\s*%", criterion)
            if match:
                required_rate = float(match.group(1)) / 100
                if results:
                    completed = sum(
                        1 for r in results.values() if r.get("status") == "completed"
                    )
                    actual_rate = completed / len(results)
                    return actual_rate >= required_rate
            return True

        # Pattern: "Task:<task_id> completed"
        if criterion_lower.startswith("task:") and "completed" in criterion_lower:
            # Extract task_id between "task:" and "completed"
            parts = (
                criterion_lower.replace("task:", "").replace("completed", "").strip()
            )
            task_id = parts.strip()
            if task_id in results:
                return results[task_id].get("status") == "completed"
            return False

        # Default: unknown criteria considered met (log for visibility)
        logger.debug("Unknown success criterion pattern: %s", criterion)
        return True

    def summarize_results(self, results: Dict[str, Any]) -> Dict[str, Any]:
        """Summarize workflow results"""
        completed = sum(1 for r in results.values() if r.get("status") == "completed")
        failed = sum(1 for r in results.values() if r.get("status") == "failed")

        return {
            "total_tasks": len(results),
            "completed": completed,
            "failed": failed,
            "success_rate": completed / max(len(results), 1),
        }
