# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Topology Module

Issue #2137: Dynamic DAG of agent connections with Hebbian evolution.

Applies the same Hebbian reinforcement principle used by the knowledge mesh:
agents that succeed together build stronger connections; those that fail
together weaken.  The topology is queried at routing time to bias agent
selection toward historically effective collaborations.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from itertools import combinations
from typing import Optional, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Hebbian learning rate: how much each outcome shifts the weight.
_LEARNING_RATE: float = 0.1
# Decay factor applied to the current weight each update.
_DECAY: float = 1.0 - _LEARNING_RATE


@dataclass
class AgentConnection:
    """A directed, weighted edge between two agents in the topology DAG."""

    id: str
    from_agent: str
    to_agent: str
    task_type: Optional[str]  # None means the connection applies to all task types
    weight: float
    co_success_count: int
    co_failure_count: int
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


@runtime_checkable
class AgentTopologyDB(Protocol):
    """Database access protocol for agent topology persistence.

    Issue #2137: Kept as a Protocol so the topology layer stays testable
    without a real database connection.
    """

    async def get_agent_connections(
        self,
        from_agent: str,
        task_type: Optional[str],
        min_weight: float,
        limit: int,
    ) -> list[AgentConnection]:
        """Return connections from *from_agent* matching the filter criteria."""
        ...

    async def get_or_create_agent_connection(
        self, from_agent: str, to_agent: str, task_type: Optional[str]
    ) -> AgentConnection:
        """Fetch the connection or create it with a neutral starting weight."""
        ...

    async def update_agent_connection(
        self,
        connection_id: str,
        weight: float,
        co_success_count: Optional[int] = None,
        co_failure_count: Optional[int] = None,
    ) -> None:
        """Persist updated weight and counter fields."""
        ...

    async def record_agent_task(
        self,
        agent_id: str,
        task_type: Optional[str],
        workflow_id: str,
        success: bool,
    ) -> None:
        """Append a task history entry for *agent_id*."""
        ...

    async def delete_weak_connections(
        self,
        min_weight: float,
        inactive_since: datetime,
    ) -> int:
        """Delete connections below *min_weight* not updated since *inactive_since*.

        Returns the number of rows deleted.
        """
        ...


class AgentTopology:
    """Dynamic DAG of agent connections.  Evolves from task outcomes.

    Same Hebbian principle as the knowledge mesh: agents that succeed
    together get stronger connections.

    Issue #2137.
    """

    def __init__(self, db: AgentTopologyDB) -> None:
        self.db = db

    async def get_collaborators(
        self,
        agent_id: str,
        task_type: Optional[str] = None,
        min_weight: float = 0.3,
        limit: int = 5,
    ) -> list[AgentConnection]:
        """Return agents that *agent_id* works well with.

        Args:
            agent_id: The agent whose outgoing connections are queried.
            task_type: Filter to connections for a specific task type.
                       Pass ``None`` to include all task types.
            min_weight: Only return connections above this weight threshold.
            limit: Maximum number of connections to return.

        Returns:
            List of :class:`AgentConnection` sorted by weight descending.
        """
        return await self.db.get_agent_connections(
            from_agent=agent_id,
            task_type=task_type,
            min_weight=min_weight,
            limit=limit,
        )

    async def record_outcome(
        self,
        workflow_id: str,
        agents: list[str],
        task_type: Optional[str],
        success: bool,
    ) -> None:
        """Update connection weights after a multi-agent workflow completes.

        For every pair of agents in *agents*, applies Hebbian reinforcement:
        - success: exponential moving average toward 1.0 (strengthen)
        - failure: exponential moving average toward 0.0 (weaken)

        Also appends a task history entry for every participating agent.

        Args:
            workflow_id: Unique identifier for the completed workflow.
            agents: Ordered list of agent IDs that participated.
            task_type: Task type label for the workflow; may be ``None``.
            success: Whether the workflow succeeded overall.
        """
        for from_agent, to_agent in combinations(agents, 2):
            await self._update_pair(from_agent, to_agent, task_type, success)
        await self._record_agent_histories(workflow_id, agents, task_type, success)

    async def _record_agent_histories(
        self,
        workflow_id: str,
        agents: list[str],
        task_type: Optional[str],
        success: bool,
    ) -> None:
        """Persist per-agent task history and emit a summary log entry.

        Issue #2137: Extracted from record_outcome to stay within 30-line limit.
        """
        for agent_id in agents:
            await self.db.record_agent_task(agent_id, task_type, workflow_id, success)
        logger.info(
            "Recorded %s outcome for workflow %s: %d agents, %d pairs",
            "success" if success else "failure",
            workflow_id,
            len(agents),
            len(agents) * (len(agents) - 1) // 2,
        )

    async def _update_pair(
        self,
        from_agent: str,
        to_agent: str,
        task_type: Optional[str],
        success: bool,
    ) -> None:
        """Apply one Hebbian update to a single agent pair.

        Issue #2137: Extracted to keep *record_outcome* under 30 lines.
        """
        conn = await self.db.get_or_create_agent_connection(
            from_agent, to_agent, task_type
        )
        target = 1.0 if success else 0.0
        new_weight = conn.weight * _DECAY + target * _LEARNING_RATE

        if success:
            await self.db.update_agent_connection(
                conn.id,
                weight=new_weight,
                co_success_count=conn.co_success_count + 1,
            )
        else:
            await self.db.update_agent_connection(
                conn.id,
                weight=new_weight,
                co_failure_count=conn.co_failure_count + 1,
            )

    async def prune_weak_connections(
        self,
        min_weight: float = 0.1,
        inactive_days: int = 60,
    ) -> int:
        """Remove weak, inactive agent connections. Returns count deleted.

        Deletes every connection whose weight is below *min_weight* AND whose
        *last_updated* timestamp is older than *inactive_days* days.

        Issue #2167.
        """
        cutoff = datetime.now(tz=timezone.utc) - timedelta(days=inactive_days)
        deleted = await self.db.delete_weak_connections(
            min_weight=min_weight,
            inactive_since=cutoff,
        )
        logger.info(
            "Pruned %d weak connections (min_weight=%.3f, inactive_days=%d)",
            deleted,
            min_weight,
            inactive_days,
        )
        return deleted
