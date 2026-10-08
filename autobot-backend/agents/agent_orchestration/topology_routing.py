# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Topology-Aware Router (#2138)

Extends routing with topology-based collaboration selection.
For complex/multi-step tasks, queries AgentTopology to find
collaborator agents that have historically succeeded together.
"""

from typing import Any, Protocol

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_COMPLEX_PATTERNS = frozenset({"complex", "multi_hop", "multi_step"})


class RoutableConnection(Protocol):
    """The ONE field this router needs from a connection: where it points.

    Named for the capability, not for the class it happens to describe. It was
    `AgentConnection`, which is also the concrete `@dataclass` in `topology.py`
    (#12771) — so the same name meant two different things in one package: a
    seven-field record and a one-field structural view of it. A reader could not
    tell which they had, and the narrow Protocol is deliberately NOT the dataclass:
    depending on `to_agent` alone is what keeps this module independent of it.
    """

    to_agent: str


class CollaboratorSource(Protocol):
    """Whatever can answer `get_collaborators`, which is all this router asks for.

    Was `AgentTopology`, colliding with the concrete class of that name in
    `topology.py` for the same reason.
    """

    async def get_collaborators(
        self,
        agent_id: str,
        task_type: str | None,
        limit: int,
    ) -> list[RoutableConnection]: ...


class TopologyAwareRouter:
    """Extends routing with topology-based collaboration selection.

    For complex/multi-step tasks, queries AgentTopology to find
    collaborator agents that have historically succeeded together.
    """

    def __init__(self, topology: CollaboratorSource, base_router: Any = None):
        self.topology = topology
        self.base_router = base_router

    async def route_with_collaborators(
        self,
        request: str,
        context: dict,
        primary_agent_id: str,
    ) -> dict:
        """Route request and suggest collaborator agents."""
        task_type = context.get("task_type")
        complexity = context.get("complexity", "simple")

        collaborators = await self._resolve_collaborators(primary_agent_id, task_type, complexity)

        return _build_routing_result(primary_agent_id, collaborators)

    async def _resolve_collaborators(
        self,
        primary_agent_id: str,
        task_type: str | None,
        complexity: str,
    ) -> list[str]:
        """Return collaborator agent IDs when complexity warrants it."""
        if complexity not in _COMPLEX_PATTERNS:
            return []

        connections = await self.topology.get_collaborators(primary_agent_id, task_type=task_type, limit=2)
        collaborators = [c.to_agent for c in connections]
        logger.debug(
            "Topology collaborators for %s (%s): %s",
            primary_agent_id,
            complexity,
            collaborators,
        )
        return collaborators


def _build_routing_result(primary: str, collaborators: list[str]) -> dict:
    """Assemble the routing result dict."""
    return {
        "primary": primary,
        "collaborators": collaborators,
        "pattern": "parallel" if collaborators else "single",
        "topology_consulted": bool(collaborators),
    }
