# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Workflow Planner

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains workflow planning, step estimation, and capability determination.
"""

import logging
from typing import Any, Dict, List, Optional, Set

# Issue #673: Import from autobot_types to avoid circular import with src.orchestrator
from src.autobot_types import TaskComplexity

from .types import AgentCapability, AgentProfile

logger = logging.getLogger(__name__)


class WorkflowPlanner:
    """
    Plans workflow steps with intelligent agent assignment.

    Handles:
    - Enhanced workflow step planning
    - Capability determination for steps
    - Duration estimation based on agent performance
    """

    # Capability mapping for action types
    CAPABILITY_MAPPING = {
        "research": {AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
        "search": {AgentCapability.RESEARCH},
        "analyze": {AgentCapability.ANALYSIS, AgentCapability.DATA_PROCESSING},
        "document": {
            AgentCapability.DOCUMENTATION,
            AgentCapability.KNOWLEDGE_MANAGEMENT,
        },
        "execute": {AgentCapability.SYSTEM_OPERATIONS},
        "coordinate": {AgentCapability.WORKFLOW_COORDINATION},
        "generate": {AgentCapability.CODE_GENERATION},
        "process": {AgentCapability.DATA_PROCESSING},
    }

    # Agent type to capability mapping
    AGENT_CAPABILITY_MAP = {
        "research": {AgentCapability.RESEARCH},
        "librarian": {
            AgentCapability.KNOWLEDGE_MANAGEMENT,
            AgentCapability.DOCUMENTATION,
        },
        "system_commands": {AgentCapability.SYSTEM_OPERATIONS},
        "orchestrator": {AgentCapability.WORKFLOW_COORDINATION},
    }

    # Base duration estimates by action type
    BASE_DURATIONS = {
        "research": 30.0,
        "search": 15.0,
        "analyze": 20.0,
        "document": 25.0,
        "execute": 10.0,
        "coordinate": 5.0,
    }

    def __init__(
        self,
        base_orchestrator: Any,
        agent_registry: Dict[str, AgentProfile],
        find_best_agent_callback: callable,
    ):
        """
        Initialize the workflow planner.

        Args:
            base_orchestrator: Base orchestrator for step planning
            agent_registry: Registry of available agents
            find_best_agent_callback: Function to find best agent for a task
        """
        self.base_orchestrator = base_orchestrator
        self.agent_registry = agent_registry
        self._find_best_agent = find_best_agent_callback

    async def plan_enhanced_workflow_steps(
        self,
        user_request: str,
        complexity: TaskComplexity,
        context: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Plan workflow steps with intelligent agent assignment.

        Args:
            user_request: The user's request to plan
            complexity: Classified task complexity
            context: Additional context for planning

        Returns:
            List of enhanced workflow steps with agent assignments
        """
        # Get base workflow steps from original orchestrator
        base_steps = self.base_orchestrator.plan_workflow_steps(
            user_request, complexity
        )

        enhanced_steps = []

        for step in base_steps:
            # Determine required capabilities for each step
            required_capabilities = self.determine_step_capabilities(
                step.action, step.agent_type
            )

            # Find best agent for this step
            assigned_agent = self._find_best_agent(
                task_type=step.agent_type,
                required_capabilities=required_capabilities,
            )

            enhanced_step = {
                "id": step.id,
                "agent_type": step.agent_type,
                "assigned_agent": assigned_agent,
                "action": step.action,
                "inputs": step.inputs,
                "user_approval_required": step.user_approval_required,
                "dependencies": step.dependencies or [],
                "required_capabilities": list(required_capabilities),
                "estimated_duration": self.estimate_step_duration(
                    step.action, assigned_agent
                ),
                "status": "planned",
            }

            enhanced_steps.append(enhanced_step)

        return enhanced_steps

    def determine_step_capabilities(
        self, action: str, agent_type: str
    ) -> Set[AgentCapability]:
        """
        Determine required capabilities for a workflow step.

        Args:
            action: Step action description
            agent_type: Type of agent for the step

        Returns:
            Set of required AgentCapabilities
        """
        required_capabilities: Set[AgentCapability] = set()

        # Check action keywords
        for keyword, capabilities in self.CAPABILITY_MAPPING.items():
            if keyword in action.lower():
                required_capabilities.update(capabilities)

        # Agent type specific requirements
        if agent_type in self.AGENT_CAPABILITY_MAP:
            required_capabilities.update(self.AGENT_CAPABILITY_MAP[agent_type])

        # Default capability if none determined
        return required_capabilities or {AgentCapability.ANALYSIS}

    def estimate_step_duration(
        self, action: str, agent_id: Optional[str]
    ) -> float:
        """
        Estimate duration for a workflow step.

        Args:
            action: Step action description
            agent_id: ID of assigned agent (optional)

        Returns:
            Estimated duration in seconds
        """
        # Get base duration from action type
        estimated_duration = 30.0  # Default

        for action_type, duration in self.BASE_DURATIONS.items():
            if action_type in action.lower():
                estimated_duration = duration
                break

        # Adjust based on agent performance
        if agent_id and agent_id in self.agent_registry:
            agent = self.agent_registry[agent_id]
            if agent.average_completion_time > 0:
                # Use agent's historical performance
                performance_factor = (
                    agent.average_completion_time / estimated_duration
                )
                # Cap at 2x base duration
                estimated_duration *= min(performance_factor, 2.0)

        return estimated_duration

    def get_plan_summary(
        self,
        user_request: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Get workflow plan summary without executing.

        Args:
            user_request: The user's request to plan
            context: Additional context

        Returns:
            Plan summary with steps and estimates
        """
        context = context or {}

        # Classify complexity
        complexity = self.base_orchestrator.classify_request_complexity(
            user_request
        )

        # Get base steps synchronously (no agent assignment yet)
        base_steps = self.base_orchestrator.plan_workflow_steps(
            user_request, complexity
        )

        return {
            "request": user_request,
            "complexity": complexity.value,
            "total_steps": len(base_steps),
            "steps": [
                {
                    "id": step.id,
                    "action": step.action,
                    "agent_type": step.agent_type,
                    "requires_approval": step.user_approval_required,
                    "dependencies": step.dependencies or [],
                }
                for step in base_steps
            ],
        }

    def create_plan_summary_for_approval(
        self,
        workflow_id: str,
        user_request: str,
        enhanced_steps: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Create plan summary for user approval.

        Args:
            workflow_id: Workflow identifier
            user_request: Original user request
            enhanced_steps: Planned workflow steps

        Returns:
            Plan summary dictionary
        """
        return {
            "workflow_id": workflow_id,
            "request": user_request,
            "total_steps": len(enhanced_steps),
            "estimated_total_duration": sum(
                step.get("estimated_duration", 10.0) for step in enhanced_steps
            ),
            "steps": [
                {
                    "id": step.get("id"),
                    "action": step.get("action"),
                    "agent_type": step.get("agent_type"),
                    "assigned_agent": step.get("assigned_agent"),
                    "estimated_duration": step.get("estimated_duration"),
                    "requires_approval": step.get("user_approval_required", False),
                    "dependencies": step.get("dependencies", []),
                }
                for step in enhanced_steps
            ],
            "agents_involved": list(
                set(
                    step.get("assigned_agent")
                    for step in enhanced_steps
                    if step.get("assigned_agent")
                )
            ),
        }
