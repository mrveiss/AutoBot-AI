# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Executor

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains workflow execution, step coordination, and agent interaction handling.
"""

import asyncio
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from constants.threshold_constants import TimingConstants

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
    ) -> None:
        """Execute a single workflow step with agent management (Issue #398: extracted)."""
        step_start_time = time.time()
        agent_id = step.get("assigned_agent")

        if agent_id:
            self._reserve_agent(agent_id)

        try:
            step_result = await self._execute_coordinated_step(
                step, execution_context, context
            )

            step["status"] = "completed" if step_result.get("success") else "failed"
            step["execution_time"] = time.time() - step_start_time
            step["result"] = step_result
            execution_context["step_results"][step["id"]] = step_result

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

    async def execute_coordinated_workflow(
        self,
        workflow_id: str,
        steps: List[Dict[str, Any]],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute workflow with coordinated agent management.

        Args:
            workflow_id: Workflow identifier
            steps: List of enhanced workflow steps
            context: Workflow context

        Returns:
            Execution context with results
        """
        execution_context = {
            "workflow_id": workflow_id,
            "agents_involved": set(),
            "interactions": [],
            "step_results": {},
            "status": "in_progress",
        }

        try:
            # Execute steps with dependency management (Issue #398: refactored)
            for step in steps:
                if not await self._check_step_dependencies(
                    step, execution_context["step_results"]
                ):
                    logger.warning("Step %s dependencies not met, skipping", step["id"])
                    step["status"] = "skipped"
                    continue

                await self._execute_step_with_agent(step, execution_context, context)

            self._determine_workflow_status(steps, execution_context)
            return execution_context

        except Exception as e:
            logger.error("Workflow %s execution failed: %s", workflow_id, e)
            execution_context["status"] = "failed"
            execution_context["error"] = str(e)
            return execution_context

    async def _check_step_dependencies(
        self,
        step: Dict[str, Any],
        completed_results: Dict[str, Any],
    ) -> bool:
        """
        Check if step dependencies are satisfied.

        Args:
            step: The step to check
            completed_results: Results of completed steps

        Returns:
            True if all dependencies are satisfied
        """
        dependencies = step.get("dependencies", [])

        if not dependencies:
            return True  # No dependencies

        for dep_id in dependencies:
            if dep_id not in completed_results:
                return False

            if not completed_results[dep_id].get("success", False):
                return False

        return True

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

    async def _execute_coordinated_step(
        self,
        step: Dict[str, Any],
        execution_context: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute a single workflow step with agent coordination.

        Issue #620: Refactored to use extracted helper methods.

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
        Simulate step execution (placeholder for actual agent execution).

        In real implementation, this would delegate to actual agents.

        Args:
            step: The step to execute
            context: Workflow context

        Returns:
            Execution result
        """
        action = step["action"]

        # Add small delay to simulate work
        await asyncio.sleep(TimingConstants.MICRO_DELAY)

        return {
            "action_completed": action,
            "timestamp": time.time(),
            "simulated": True,
        }

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
