# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
AgentRegistry Protocol — canonical interface for all registry implementations.

Issue #6828: four concrete classes named AgentRegistry existed with no shared
interface, making it impossible to know which one to use for "find an agent
that can do X".  This module promotes the narrow Protocol that was buried in
services/mesh_brain/agent_evolution.py to a first-class shared interface.

Concrete registries and their scopes
--------------------------------------
- orchestration.agent_registry.AgentRegistry
    Static profile registry (AgentProfile + AgentCapability).  Owned by
    orchestrator startup; holds the in-memory catalogue of what each agent
    *can* do.  Orphan from #6820 — not wired to live agents.

- agents.agent_client.AgentRegistry
    Health-tracking registry for running BaseAgent instances.  Owned by
    AgentOrchestrator; tracks reachability of live agents and performs
    health checks.

- services.agent_registry_service.AgentRegistryService
    Central CRUD service (#1754) backed by the agents database table.
    Canonical for persistent agent metadata; used at startup/shutdown.

- agents.agent_orchestration.distributed_management.DistributedAgentManager
    Dynamic registry with circuit-breaker health checks and work-stealing
    (#2109, #4694).  Manages distributed agent lifecycle at runtime.

Only the specialization-update protocol surface needed by AgentEvolutionTracker
is expressed here.  Broader unification (canonical lookup interface) is tracked
in #6828.
"""

from typing import Protocol


class AgentRegistryProtocol(Protocol):
    """Narrow protocol for registries that support specialization updates.

    Implemented (structurally) by any registry that can receive specialization
    update callbacks from AgentEvolutionTracker.  Concrete registries do not
    need to explicitly subclass this; Python's structural subtyping enforces
    the contract at type-check time.
    """

    async def update_specializations(
        self,
        agent_id: str,
        top_types: list[str],
        rates: dict[str, float],
    ) -> None: ...
