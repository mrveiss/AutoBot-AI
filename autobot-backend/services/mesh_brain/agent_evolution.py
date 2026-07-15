# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Evolution Tracker (#2138)

Tracks emergent agent specializations from task outcomes.
Analyzes task history per agent to discover which task types
each agent excels at and updates agent profiles accordingly.
"""

from dataclasses import dataclass
from typing import Protocol

from autobot_shared.agent_registry_protocol import AgentRegistryProtocol
from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)


@dataclass
class AgentSpecialization:
    """Discovered specialization for a single agent/task-type pair."""

    agent_id: str
    task_type: str
    success_rate: float
    task_count: int


class AgentSpecializationDB(Protocol):
    """Protocol for the database layer used by AgentEvolutionTracker."""

    async def get_agent_specializations(self, agent_id: str, min_tasks: int, days: int) -> list[dict]: ...

    async def get_all_agent_ids(self) -> list[str]: ...


# Issue #6828: the registry Protocol lives in autobot_shared/agent_registry_protocol.py
# (AgentRegistryProtocol); its canonical concrete implementer is
# orchestration.agent_registry.AgentCapabilityRegistry.update_specializations.
# The legacy `AgentRegistry = AgentRegistryProtocol` compat alias was retired after
# a repo-wide importer audit found zero consumers — the bare name was the last
# remnant of the 4-way AgentRegistry naming collision this issue resolved.
# NOTE (wire-in): AgentEvolutionTracker itself has no production scheduler/caller
# yet — parked pending a wire-in issue (see #6828 closure report).


class AgentEvolutionTracker:
    """Tracks emergent agent specializations from task outcomes.

    Analyzes task history per agent to discover which task types
    each agent excels at. Updates agent profiles with discovered
    specializations.
    """

    def __init__(self, db: AgentSpecializationDB, registry: AgentRegistryProtocol | None = None) -> None:
        self.db = db
        self.registry = registry

    async def evaluate(self, agent_id: str, min_tasks: int = 5, days: int = 30) -> list[AgentSpecialization]:
        """Analyze an agent's task history and return discovered specializations."""
        stats = await self.db.get_agent_specializations(agent_id, min_tasks, days)
        specializations = _build_specializations(agent_id, stats)

        if self.registry and specializations:
            await self._update_registry(agent_id, specializations)

        return specializations

    async def evaluate_all(self) -> dict[str, list[AgentSpecialization]]:
        """Evaluate all agents and return specializations per agent."""
        agents = await self.db.get_all_agent_ids()
        results: dict[str, list[AgentSpecialization]] = {}
        for agent_id in agents:
            specs = await self.evaluate(agent_id)
            if specs:
                results[agent_id] = specs
        return results

    async def _update_registry(self, agent_id: str, specializations: list[AgentSpecialization]) -> None:
        """Update agent profile with top specializations."""
        top_types = [s.task_type for s in specializations[:3]]
        rates = {s.task_type: s.success_rate for s in specializations}
        await self.registry.update_specializations(agent_id, top_types, rates)  # type: ignore[union-attr]  # noqa: E501
        logger.info(
            "Updated specializations for agent %s: %s",
            agent_id,
            top_types,
        )


def _build_specializations(agent_id: str, stats: list[dict]) -> list[AgentSpecialization]:
    """Convert raw DB rows into AgentSpecialization dataclasses."""
    return [
        AgentSpecialization(
            agent_id=agent_id,
            task_type=s["task_type"],
            success_rate=s["success_rate"],
            task_count=s["task_count"],
        )
        for s in stats
    ]
