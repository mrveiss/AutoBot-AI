# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent registry protocols — canonical interfaces for the scoped registries.

Issue #6828: four concrete classes named ``AgentRegistry`` existed with no
shared interface, making it impossible to know which one to use for "find an
agent that can do X".  The classes now carry distinct, scope-descriptive names
and this module is the single place that defines their shared surfaces.

Concrete registries and their scopes
--------------------------------------
- orchestration.agent_registry.AgentCapabilityRegistry
    Static profile registry (AgentProfile + AgentCapability).  The canonical
    in-process answer to "find an agent that can do X" — implements
    ``AgentCapabilityLookup`` and ``AgentRegistryProtocol``.  Production-wired:
    orchestrator routing projection (#11251), the chat_workflow tool-dispatch
    boundary via ``resolve_forbidden_tools`` (#11145), and the
    ``/api/agents/status`` + ``/api/agent/agents/available`` endpoints.

- agents.agent_client.AgentHealthRegistry
    Health-tracking registry for running BaseAgent instances.  Tracks
    reachability of live agents and performs health checks.  Documented
    non-implementer of ``AgentCapabilityLookup``: it answers "is this agent
    alive?", not "what can it do?" — capability queries belong to
    AgentCapabilityRegistry.

- services.agent_registry_service.AgentRegistryService
    Central CRUD service (#1754) backed by the agents database table.
    Canonical for persistent agent metadata; seeded at startup
    (initialization/lifespan.py).  Documented non-implementer of
    ``AgentCapabilityLookup``: async/DB-session bound persistence, no
    in-process capability model.

- agents.agent_orchestration.distributed_management.DistributedAgentManager
    Dynamic registry with circuit-breaker health checks and work-stealing
    (#2109, #4694).  Manages distributed agent lifecycle at runtime.
    Documented non-implementer of ``AgentCapabilityLookup``: membership and
    task-liveness, not capability lookup.
"""

from typing import Any, List, Protocol, runtime_checkable


@runtime_checkable
class AgentCapabilityLookup(Protocol):
    """Canonical "find an agent that can do X" lookup surface (#6828).

    Implemented by ``orchestration.agent_registry.AgentCapabilityRegistry``.
    ``capability`` is typed ``Any`` because the concrete capability enum
    (``orchestration.types.AgentCapability``) lives in the backend and shared
    code must not import backend modules; implementers narrow the type.
    """

    def find_by_capability(self, capability: Any) -> List[Any]:
        """Return profiles/agents that advertise *capability*."""
        ...

    def find_available(self) -> List[Any]:
        """Return agents currently available for work (not at capacity)."""
        ...


@runtime_checkable
class AgentRegistryProtocol(Protocol):
    """Narrow protocol for registries that support specialization updates.

    The callback surface AgentEvolutionTracker uses to persist discovered
    specializations.  Implemented by
    ``orchestration.agent_registry.AgentCapabilityRegistry`` (#6828); any
    registry that can receive specialization updates conforms structurally —
    explicit subclassing is not required.
    """

    async def update_specializations(
        self,
        agent_id: str,
        top_types: list[str],
        rates: dict[str, float],
    ) -> None: ...
