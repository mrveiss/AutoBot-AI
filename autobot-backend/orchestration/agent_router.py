# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Agent selection, resolution, and capability coverage extracted from WorkflowRunner (#6393).

GH #6819: This class was renamed from ``AgentRouter`` to ``TaskAgentScorer`` to distinguish
it from ``agents.agent_orchestration.routing.AgentRouter`` (522 LOC, user-request routing).
``TaskAgentScorer`` handles *workflow-task* scoring; the other ``AgentRouter`` handles
*user-request* routing.  The old name is retained as an alias for backward compatibility.

Moved from enhanced_orchestration.agent_router to orchestration.agent_router (issue #10666 B3).
"""

from typing import Any, Dict, List, Set, Tuple

from autobot_shared.logging_manager import get_logger
from orchestration.performance_tracker import PerformanceTracker
from orchestration.types import AgentCapability

logger = get_logger("task_agent_scorer")


class TaskAgentScorer:
    """Scores agents for workflow tasks and computes capability coverage.

    Extracted from WorkflowRunner (#6393) and addresses hidden AgentClientRegistry
    construction (#6392) by accepting the registry as an injected dependency.

    Renamed from ``AgentRouter`` → ``TaskAgentScorer`` (GH #6819) to avoid
    name collision with ``agents.agent_orchestration.routing.AgentRouter``.
    """

    def __init__(
        self,
        agent_capabilities: Dict[str, Set],
        performance_tracker: PerformanceTracker,
        agent_registry: Any,
    ) -> None:
        self.agent_capabilities = agent_capabilities
        self._perf = performance_tracker
        self._agent_client_registry = agent_registry

    async def get_agent_recommendations_scored(self, capabilities_needed: Set) -> List[Tuple[str, float]]:
        """Return (agent, score) pairs ranked best-first (#10660).

        Score blends reliability (0.5), capability-coverage (0.3) and experience
        (0.2). Previously the score was computed then discarded; callers that
        want the ranking confidence use this, while get_agent_recommendations
        keeps returning a plain name list for backward compatibility.
        """
        suitable: List[Tuple[str, float]] = []
        for agent, caps in self.agent_capabilities.items():
            if not capabilities_needed.issubset(caps):
                continue
            perf = self._perf.agent_performance.get(agent)
            if perf is None:
                continue
            score = (
                perf.reliability_score * 0.5
                + len(capabilities_needed.intersection(caps)) / len(capabilities_needed) * 0.3
                + min(perf.total_tasks / 100, 1.0) * 0.2
            )
            suitable.append((agent, score))
        suitable.sort(key=lambda x: x[1], reverse=True)
        return suitable

    async def get_agent_recommendations(self, capabilities_needed: Set) -> List[str]:
        scored = await self.get_agent_recommendations_scored(capabilities_needed)
        return [agent for agent, _ in scored]

    async def get_agent_instance(self, agent_type: str) -> Any | None:
        agent = self._agent_client_registry.get_agent(agent_type)
        if agent is not None:
            await self._agent_client_registry.update_agent_health(agent_type)
            return agent
        logger.warning(
            "Agent '%s' not found. Available: %s",
            agent_type,
            self._agent_client_registry.list_agents(),
        )
        return None

    def calculate_capability_coverage(self) -> Dict[str, float]:
        coverage: Dict[str, float] = {}
        n_agents = max(len(self.agent_capabilities), 1)
        for capability in AgentCapability:
            agents_with_cap = sum(1 for caps in self.agent_capabilities.values() if capability in caps)
            coverage[capability.value] = agents_with_cap / n_agents
        return coverage


# Backward-compatibility alias — callers that imported AgentRouter from this module
# continue to work unchanged while new code should use TaskAgentScorer (GH #6819).
AgentRouter = TaskAgentScorer
