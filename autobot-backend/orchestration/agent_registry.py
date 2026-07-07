# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Registry Management

Issue #381: Extracted from enhanced_orchestrator.py god class refactoring.
Contains agent registration, lookup, and management functionality.
"""

from typing import Dict, List, Set

from autobot_shared.logging_manager import get_logger

from .types import AgentCapability, AgentProfile

logger = get_logger(__name__)


# GH#11139: infra/shell tools that non-executor agents may not invoke. The system
# agent is the designated executor and is intentionally excluded from this boundary.
_INFRA_AND_SHELL_TOOLS: List[str] = [
    "bash",
    "shell",
    "execute_command",
    "run_command",
    "system_exec",
    "deploy",
    "ansible",
    "docker",
    "kubectl",
    "helm",
    "terraform",
]


def _create_research_agent() -> AgentProfile:
    """Create the research agent profile. Issue #620."""
    return AgentProfile(
        agent_id="research_agent",
        agent_type="research",
        capabilities={AgentCapability.RESEARCH, AgentCapability.ANALYSIS},
        specializations=["web_search", "data_analysis", "information_synthesis"],
        max_concurrent_tasks=5,
        preferred_task_types=["research", "information_gathering", "analysis"],
        allowed_work=["web_search", "http_get", "read_file"],
        forbidden_work=list(_INFRA_AND_SHELL_TOOLS),
    )


def _create_documentation_agent() -> AgentProfile:
    """Create the documentation agent profile. Issue #620."""
    return AgentProfile(
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
        allowed_work=["write_file", "edit_file", "read_file"],
        forbidden_work=list(_INFRA_AND_SHELL_TOOLS),
    )


def _create_system_agent() -> AgentProfile:
    """Create the system agent profile. Issue #620.

    The designated executor — no ``forbidden_work`` boundary; shell/infra tools
    remain gated by the loop's global SENSITIVE_TOOLS approval flow (GH#11139).
    """
    return AgentProfile(
        agent_id="system_agent",
        agent_type="system_commands",
        capabilities={
            AgentCapability.SYSTEM_OPERATIONS,
            AgentCapability.CODE_GENERATION,
        },
        specializations=["command_execution", "system_administration", "automation"],
        max_concurrent_tasks=2,
        preferred_task_types=["system_operations", "command_execution"],
        allowed_work=list(_INFRA_AND_SHELL_TOOLS),
    )


def _create_coordination_agent() -> AgentProfile:
    """Create the coordination agent profile. Issue #620.

    Plans and routes; it must not execute infra/shell tools itself (GH#11139).
    """
    return AgentProfile(
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
        forbidden_work=list(_INFRA_AND_SHELL_TOOLS),
    )


def get_default_agents() -> List[AgentProfile]:
    """
    Get the list of default agent profiles.

    Returns:
        List of pre-configured AgentProfile instances.
        Issue #620: Refactored to use helper functions for each agent.
    """
    return [
        _create_research_agent(),
        _create_documentation_agent(),
        _create_system_agent(),
        _create_coordination_agent(),
    ]


def match_forbidden_tool(tool_name: str, forbidden: "frozenset[str]") -> "str | None":
    """Return the ``forbidden_work`` pattern matching *tool_name*, else None (GH#11145).

    Single source for forbidden-tool matching — the agent loop and the production
    tool-dispatch seam both call this so the exact/prefix rule lives in one place.
    Matching is case-insensitive; a manifest entry matches by exact name or as a
    name prefix (e.g. ``deploy`` blocks ``deploy_service``).
    """
    if not forbidden:
        return None
    name = tool_name.lower()
    if name in forbidden:
        return name
    for pattern in forbidden:
        if name.startswith(pattern):
            return pattern
    return None


class AgentRegistry:
    """Static profile registry for orchestration agent capabilities.

    Scope (#6828): holds in-memory AgentProfile + AgentCapability catalogue
    populated at orchestrator startup from DEFAULT_AGENT_CONFIGS.  This is
    the **what-can-each-agent-do** registry — it does not track live health or
    database persistence.  See also:
    - agents.agent_client.AgentRegistry — health-tracking runtime registry
    - services.agent_registry_service.AgentRegistryService — DB-backed CRUD
    - agents.agent_orchestration.distributed_management.DistributedAgentManager — dynamic/distributed
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
                    agent_profile.agent_id,
                )

            self._agents[agent_profile.agent_id] = agent_profile
            logger.info(
                "Agent %s registered with capabilities: %s",
                agent_profile.agent_id,
                agent_profile.capabilities,
            )
            return True

        except Exception as e:
            logger.error("Failed to register agent %s: %s", agent_profile.agent_id, e)
            return False

    def get(self, agent_id: str) -> AgentProfile | None:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def get_all(self) -> Dict[str, AgentProfile]:
        """Get all registered agents."""
        return self._agents.copy()

    def forbidden_tools(self, agent_id: str) -> "frozenset[str]":
        """Return the tool names *agent_id* is forbidden to invoke (GH#11139).

        Reads the declarative ``forbidden_work`` manifest off the agent's profile.
        Unknown agents return an empty set (no boundary → falls back to the loop's
        global SENSITIVE_TOOLS approval gate).
        """
        agent = self._agents.get(agent_id)
        return frozenset(agent.forbidden_work) if agent is not None else frozenset()

    def work_boundary(self, agent_id: str) -> "tuple[List[str], List[str]]":
        """Return ``(allowed_work, forbidden_work)`` for *agent_id* (GH#11139).

        The single query point for an agent's capability boundary — callers read
        this instead of reconstructing the boundary from RBAC + sensitive-tool +
        vault state separately.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            return ([], [])
        return (list(agent.allowed_work), list(agent.forbidden_work))

    def find_by_capability(self, capability: AgentCapability) -> List[AgentProfile]:
        """Find all agents with a specific capability."""
        return [agent for agent in self._agents.values() if capability in agent.capabilities]

    def find_available(self) -> List[AgentProfile]:
        """Find all available agents (not at max capacity)."""
        return [
            agent
            for agent in self._agents.values()
            if agent.current_workload < agent.max_concurrent_tasks and agent.availability_status == "available"
        ]

    def find_best_for_task(
        self,
        task_type: str,
        required_capabilities: Set[AgentCapability] | None = None,
    ) -> str | None:
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
            if required_capabilities and not required_capabilities.issubset(agent.capabilities):
                continue

            # Calculate score based on preferences and performance
            score = 0.0

            # Prefer agents with matching task type
            if task_type in agent.preferred_task_types:
                score += 10.0

            # Factor in success rate
            score += agent.success_rate * 5.0

            # Factor in available capacity
            capacity_ratio = 1.0 - (agent.current_workload / agent.max_concurrent_tasks)
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
        agent.success_rate = alpha * success_value + (1 - alpha) * agent.success_rate

        # Update average completion time
        if agent.average_completion_time == 0:
            agent.average_completion_time = execution_time
        else:
            agent.average_completion_time = alpha * execution_time + (1 - alpha) * agent.average_completion_time

    def __len__(self) -> int:
        """Return number of registered agents."""
        return len(self._agents)

    def __contains__(self, agent_id: str) -> bool:
        """Check if agent is registered."""
        return agent_id in self._agents


# GH#11145: process-wide read-only registry of the default capability manifests,
# seeded once from get_default_agents() (the same SSOT the orchestrator uses, so
# no drift). Lets the production tool-dispatch seam resolve an agent's boundary
# cheaply without constructing an Orchestrator on every tool call.
_default_registry: "AgentRegistry | None" = None


def resolve_forbidden_tools(agent_id: "str | None") -> "frozenset[str]":
    """Resolve *agent_id*'s ``forbidden_work`` manifest from the default profiles.

    Cached, read-only lookup reused by both the agent loop and the production tool
    dispatch (GH#11145). An unknown or ``None`` ``agent_id`` returns an empty set —
    no boundary — so callers no-op safely for the plain (profile-less) chat agent.
    """
    if not agent_id:
        return frozenset()
    global _default_registry  # noqa: PLW0603
    if _default_registry is None:
        _default_registry = AgentRegistry(initialize_defaults=True)
    return _default_registry.forbidden_tools(agent_id)
