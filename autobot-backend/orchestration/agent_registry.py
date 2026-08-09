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
from autobot_shared.tool_catalogue import INFRA_AND_SHELL_TOOLS, match_tool_name

from .types import AgentCapability, AgentProfile

logger = get_logger(__name__)


# GH#11139: infra/shell tools that non-executor agents may not invoke. The system
# agent is the designated executor and is intentionally excluded from this boundary.
# GH#11206: composed from the canonical tool catalogue (SSOT).
_INFRA_AND_SHELL_TOOLS: List[str] = list(INFRA_AND_SHELL_TOOLS)


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
        unbounded=True,
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


# #11251 Part 1: the orchestrator's capability-routing map keys on these ids.
# Giving each a first-class AgentProfile lets orchestrator.agent_capabilities be a
# pure projection of this registry (no parallel hardcoded capability dict). The
# capabilities below MUST match the historical routing map exactly (no routing
# regression); a test asserts the projection equals the previous literal.
# Boundaries (decision: proper hardening): read/analysis/synthesis routing agents
# forbid infra+shell; ``system_commands`` is the routing executor, allowed
# infra/shell like ``system_agent``.
_ROUTING_PROFILE_SPECS = [
    (
        "classification_agent",
        "classifier",
        {AgentCapability.ANALYSIS, AgentCapability.VALIDATION},
        ["intent_classification", "input_validation"],
    ),
    (
        "kb_librarian",
        "librarian",
        {AgentCapability.RESEARCH, AgentCapability.SYNTHESIS},
        ["knowledge_retrieval", "context_synthesis"],
    ),
    (
        "security_scanner",
        "security",
        {AgentCapability.SECURITY, AgentCapability.VALIDATION},
        ["vulnerability_scan", "policy_validation"],
    ),
    (
        "npu_code_search",
        "search",
        {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
        ["code_search", "npu_acceleration"],
    ),
    (
        "development_speedup",
        "optimizer",
        {AgentCapability.ANALYSIS, AgentCapability.OPTIMIZATION},
        ["dev_optimization"],
    ),
    (
        "json_formatter",
        "formatter",
        {AgentCapability.VALIDATION, AgentCapability.SYNTHESIS},
        ["json_formatting", "schema_validation"],
    ),
    ("llm_failsafe", "failsafe", {AgentCapability.SYNTHESIS}, ["fallback_synthesis"]),
]

# The full routing-agent id set (the 7 above + the executor + research_agent).
ROUTING_AGENT_IDS = frozenset([spec[0] for spec in _ROUTING_PROFILE_SPECS] + ["system_commands", "research_agent"])


def _create_routing_profiles() -> List[AgentProfile]:
    """Build first-class profiles for the orchestrator routing ids (#11251 P1)."""
    profiles = [
        AgentProfile(
            agent_id=agent_id,
            agent_type=agent_type,
            capabilities=set(caps),
            specializations=list(specs),
            forbidden_work=list(_INFRA_AND_SHELL_TOOLS),
        )
        for agent_id, agent_type, caps, specs in _ROUTING_PROFILE_SPECS
    ]
    # system_commands is the routing executor — allowed infra/shell (mirrors system_agent).
    profiles.append(
        AgentProfile(
            agent_id="system_commands",
            agent_type="executor",
            capabilities={AgentCapability.EXECUTION, AgentCapability.MONITORING},
            specializations=["command_execution", "system_monitoring"],
            allowed_work=list(_INFRA_AND_SHELL_TOOLS),
            unbounded=True,
        )
    )
    return profiles


def get_default_agents() -> List[AgentProfile]:
    """
    Get the list of default agent profiles.

    Returns:
        List of pre-configured AgentProfile instances.
        Issue #620: Refactored to use helper functions for each agent.
        #11251 P1: routing-map agents get first-class profiles too.
    """
    return _create_routing_profiles() + [
        _create_research_agent(),
        _create_documentation_agent(),
        _create_system_agent(),
        _create_coordination_agent(),
    ]


def match_forbidden_tool(tool_name: str, forbidden: "frozenset[str]") -> "str | None":
    """Return the ``forbidden_work`` pattern matching *tool_name*, else None (GH#11145).

    Thin wrapper over the canonical ``match_tool_name`` (GH#11206) so the agent loop
    and the production tool-dispatch seam share one exact/prefix rule. Case-insensitive;
    a manifest entry matches by exact name or as a name prefix (``deploy`` blocks
    ``deploy_service``).
    """
    return match_tool_name(tool_name, forbidden)


class AgentCapabilityRegistry:
    """Static profile registry for orchestration agent capabilities.

    Scope (#6828): holds in-memory AgentProfile + AgentCapability catalogue
    populated at orchestrator startup from DEFAULT_AGENT_CONFIGS.  This is
    the **what-can-each-agent-do** registry — it does not track live health or
    database persistence.  It is the canonical implementer of the shared
    ``AgentCapabilityLookup`` ("find an agent that can do X") and
    ``AgentRegistryProtocol`` (specialization updates) protocols in
    ``autobot_shared.agent_registry_protocol``.  See also:
    - agents.agent_client.AgentHealthRegistry — health-tracking runtime registry
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

        Raw accessor: unknown agents return an empty set. **Enforcement seams must
        call ``resolve_forbidden_tools`` instead** (GH#13588) — it recognises the
        other agent-id namespace and falls closed on an id neither namespace knows,
        which this method cannot distinguish from a declared executor.
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

    async def update_specializations(
        self,
        agent_id: str,
        top_types: List[str],
        rates: Dict[str, float],
    ) -> None:
        """Persist discovered specializations onto an agent's profile (#6828).

        Concrete implementation of the shared ``AgentRegistryProtocol`` — the
        callback surface ``AgentEvolutionTracker`` uses to report emergent
        specializations.  Discovered types are promoted to the front of the
        profile's ``specializations`` (existing ones retained, deduplicated);
        per-type success rates are recorded in ``performance_metrics`` under
        ``specialization:<task_type>`` keys.
        """
        agent = self._agents.get(agent_id)
        if agent is None:
            logger.warning("update_specializations: unknown agent %s — ignored", agent_id)
            return
        agent.specializations = list(top_types) + [s for s in agent.specializations if s not in top_types]
        agent.performance_metrics.update({f"specialization:{task_type}": rate for task_type, rate in rates.items()})
        logger.info("Agent %s specializations updated: %s", agent_id, top_types)

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
_default_registry: "AgentCapabilityRegistry | None" = None


def get_default_capability_registry() -> AgentCapabilityRegistry:
    """Return the process-wide default AgentCapabilityRegistry (#6828).

    The canonical read entry point for "find an agent that can do X" against
    the default profiles — API fallbacks (api/agent_org, api/agent) and the
    tool-dispatch boundary (``resolve_forbidden_tools``) share this instance
    instead of constructing ad-hoc registries per call.
    """
    global _default_registry  # noqa: PLW0603
    if _default_registry is None:
        _default_registry = AgentCapabilityRegistry(initialize_defaults=True)
    return _default_registry


# GH#13588: the boundary an unrecognised agent id falls back to. Every bounded
# profile in the registry declares exactly this manifest, so an unknown id lands on
# the same restriction its intended profile would have imposed — a typo or a
# wrong-namespace id costs precision, never containment.
DEFAULT_FORBIDDEN_TOOLS: "frozenset[str]" = frozenset(_INFRA_AND_SHELL_TOOLS)

_agent_type_aliases: "Dict[str, str] | None" = None


def agent_type_aliases() -> "Dict[str, str]":
    """``agent_type`` → ``agent_id`` for unambiguous **bounded** profiles (GH#13588).

    AutoBot carries two agent-id namespaces: capability profiles here, and the DB
    seed in ``api/agent_config.py``. Where they disagree they usually disagree by
    *naming style only* — the DB's ``research`` is this registry's ``research_agent``,
    whose ``agent_type`` is literally ``research``. Resolving through ``agent_type``
    reconciles those pairs from data already in the profiles, so there is no
    hand-written map to drift out of date.

    Two exclusions keep this from becoming a privilege-escalation seam:

    - an ``agent_type`` shared by more than one profile is dropped (ambiguous —
      ``librarian`` names both ``documentation_agent`` and ``kb_librarian``);
    - ``unbounded`` profiles never get an alias, so an executor's boundary-free
      manifest is reachable only by naming that executor's exact ``agent_id``.
    """
    global _agent_type_aliases  # noqa: PLW0603
    if _agent_type_aliases is None:
        by_type: Dict[str, List[AgentProfile]] = {}
        for profile in get_default_agents():
            by_type.setdefault(profile.agent_type, []).append(profile)
        _agent_type_aliases = {
            agent_type: profiles[0].agent_id
            for agent_type, profiles in by_type.items()
            if len(profiles) == 1 and not profiles[0].unbounded
        }
    return _agent_type_aliases


def resolve_agent_id(agent_id: str) -> "str | None":
    """Return the registered profile id *agent_id* denotes, or ``None`` (GH#13588)."""
    if agent_id in get_default_capability_registry():
        return agent_id
    return agent_type_aliases().get(agent_id)


def resolve_forbidden_tools(agent_id: "str | None") -> "frozenset[str]":
    """Resolve *agent_id*'s ``forbidden_work`` manifest from the default profiles.

    Cached, read-only lookup reused by both the agent loop and the production tool
    dispatch (GH#11145).

    Three outcomes, deliberately distinct (GH#13588):

    - ``None``/empty — the plain, ungoverned chat agent. No boundary, and that is
      the documented intent: there is no agent identity to bound.
    - a **registered** id — that profile's declared manifest, empty only when the
      profile declares ``unbounded`` (the designated executors).
    - anything else — ``DEFAULT_FORBIDDEN_TOOLS``, and a WARNING naming the id.

    The third case used to return an empty set, which made a typo'd or
    wrong-namespace id *indistinguishable from an executor grant* — the boundary
    looked configured and was not. It now fails closed. Note this cannot strand a
    correctly configured session: the trusted producer, ``session_role.set_role``,
    already refuses any id outside this same registry, so every id it can pin
    resolves here. Only the unvalidated producers — a client-supplied
    ``context["agent_id"]`` and the ``delegate`` tool's LLM-chosen ``agent_type`` —
    can reach this branch, and for those, restricting is the safe direction.
    """
    if not agent_id:
        return frozenset()
    resolved = resolve_agent_id(agent_id)
    if resolved is None:
        logger.warning(
            "agent_registry: unregistered agent id %r — applying the default tool boundary "
            "instead of running unbounded (GH#13588)",
            agent_id,
        )
        return DEFAULT_FORBIDDEN_TOOLS
    return get_default_capability_registry().forbidden_tools(resolved)
