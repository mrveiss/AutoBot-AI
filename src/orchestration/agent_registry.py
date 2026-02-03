# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Registry Management

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains agent registration, lookup, and management functionality.
"""

import logging
from typing import Dict, List, Optional, Set

from .types import AgentCapability, AgentProfile

logger = logging.getLogger(__name__)


def get_default_agents() -> List[AgentProfile]:
    """
    Get the list of default agent profiles.

    Returns:
        List of pre-configured AgentProfile instances
    """
    return [
        AgentProfile(
            agent_id="research_agent",
            agent_type="research",
            capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
            specializations=[
                "web_search",
                "data_analysis",
                "information_synthesis",
            ],
            max_concurrent_tasks=5,
            preferred_task_types=["research", "information_gathering", "analysis"],
        ),
        AgentProfile(
            agent_id="documentation_agent",
            agent_type="librarian",
            capabilities={
                AgentCapability.DOCUMENTATION,
                AgentCapability.KNOWLEDGE_MANAGEMENT,
            },
            specializations=[
                "auto_documentation",
                "knowledge_extraction",
                "content_organization",
            ],
            max_concurrent_tasks=3,
            preferred_task_types=["documentation", "knowledge_management"],
        ),
        AgentProfile(
            agent_id="system_agent",
            agent_type="system_commands",
            capabilities={
                AgentCapability.SYSTEM_OPERATIONS,
                AgentCapability.CODE_GENERATION,
            },
            specializations=[
                "command_execution",
                "system_administration",
                "automation",
            ],
            max_concurrent_tasks=2,
            preferred_task_types=["system_operations", "command_execution"],
        ),
        AgentProfile(
            agent_id="coordination_agent",
            agent_type="orchestrator",
            capabilities={
                AgentCapability.WORKFLOW_COORDINATION,
                AgentCapability.ANALYSIS,
            },
            specializations=[
                "workflow_management",
                "resource_allocation",
                "decision_making",
            ],
            max_concurrent_tasks=10,
            preferred_task_types=["coordination", "planning", "optimization"],
        ),
    ]


class AgentRegistry:
    """
    Manages agent registration and lookup.

    Provides methods to register, find, and manage agent profiles
    for the orchestration system.
    """

    def __init__(self, initialize_defaults: bool = True):
        """
        Initialize the agent registry.

        Args:
            initialize_defaults: Whether to populate with default agents
        """
        self._agents: Dict[str, AgentProfile] = {}

        if initialize_defaults:
            self._initialize_default_agents()

    def _initialize_default_agents(self) -> None:
        """Initialize default agent profiles."""
        for agent in get_default_agents():
            self._agents[agent.agent_id] = agent

    def register(self, agent_profile: AgentProfile) -> bool:
        """
        Register a new agent with the registry.

        Args:
            agent_profile: The agent profile to register

        Returns:
            True if registration successful
        """
        try:
            if agent_profile.agent_id in self._agents:
                logger.warning(
                    "Agent %s already registered, updating profile",
                    agent_profile.agent_id
                )

            self._agents[agent_profile.agent_id] = agent_profile
            logger.info(
                "Agent %s registered with capabilities: %s",
                agent_profile.agent_id,
                agent_profile.capabilities
            )
            return True

        except Exception as e:
            logger.error("Failed to register agent %s: %s", agent_profile.agent_id, e)
            return False

    def get(self, agent_id: str) -> Optional[AgentProfile]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def get_all(self) -> Dict[str, AgentProfile]:
        """Get all registered agents."""
        return self._agents.copy()

    def find_by_capability(
        self, capability: AgentCapability
    ) -> List[AgentProfile]:
        """Find all agents with a specific capability."""
        return [
            agent for agent in self._agents.values()
            if capability in agent.capabilities
        ]

    def find_available(self) -> List[AgentProfile]:
        """Find all available agents (not at max capacity)."""
        return [
            agent for agent in self._agents.values()
            if agent.current_workload < agent.max_concurrent_tasks
            and agent.availability_status == "available"
        ]

    def find_best_for_task(
        self,
        task_type: str,
        required_capabilities: Optional[Set[AgentCapability]] = None,
    ) -> Optional[str]:
        """
        Find the best agent for a specific task.

        Args:
            task_type: Type of task to be performed
            required_capabilities: Set of required capabilities

        Returns:
            Agent ID of best matching agent, or None
        """
        best_agent = None
        best_score = -1

        for agent_id, agent in self._agents.items():
            # Skip if at capacity
            if agent.current_workload >= agent.max_concurrent_tasks:
                continue

            # Skip if missing required capabilities
            if required_capabilities and not required_capabilities.issubset(
                agent.capabilities
            ):
                continue

            # Calculate score based on preferences and performance
            score = 0.0

            # Prefer agents with matching task type
            if task_type in agent.preferred_task_types:
                score += 10.0

            # Factor in success rate
            score += agent.success_rate * 5.0

            # Factor in available capacity
            capacity_ratio = 1.0 - (
                agent.current_workload / agent.max_concurrent_tasks
            )
            score += capacity_ratio * 3.0

            if score > best_score:
                best_score = score
                best_agent = agent_id

        return best_agent

    def reserve(self, agent_id: str) -> bool:
        """
        Reserve an agent by incrementing its workload.

        Args:
            agent_id: ID of agent to reserve

        Returns:
            True if reservation successful
        """
        if agent_id not in self._agents:
            return False

        agent = self._agents[agent_id]
        if agent.current_workload >= agent.max_concurrent_tasks:
            return False

        agent.current_workload += 1
        return True

    def release(self, agent_id: str) -> bool:
        """
        Release an agent by decrementing its workload.

        Args:
            agent_id: ID of agent to release

        Returns:
            True if release successful
        """
        if agent_id not in self._agents:
            return False

        agent = self._agents[agent_id]
        if agent.current_workload > 0:
            agent.current_workload -= 1
        return True

    def update_performance(
        self,
        agent_id: str,
        success: bool,
        execution_time: float,
    ) -> None:
        """
        Update agent performance metrics after task completion.

        Args:
            agent_id: ID of agent to update
            success: Whether the task was successful
            execution_time: Time taken to complete task
        """
        if agent_id not in self._agents:
            return

        agent = self._agents[agent_id]

        # Update success rate (exponential moving average)
        alpha = 0.1
        success_value = 1.0 if success else 0.0
        agent.success_rate = (
            alpha * success_value + (1 - alpha) * agent.success_rate
        )

        # Update average completion time
        if agent.average_completion_time == 0:
            agent.average_completion_time = execution_time
        else:
            agent.average_completion_time = (
                alpha * execution_time
                + (1 - alpha) * agent.average_completion_time
            )

    def __len__(self) -> int:
        """Return number of registered agents."""
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        """Check if agent is registered."""
        return agent_id in self._agents
