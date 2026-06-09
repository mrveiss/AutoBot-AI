# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Registry Service (#1754)

CRUD operations for the central agents table and a seed function
that populates it from DEFAULT_AGENT_CONFIGS at startup.
"""

from typing import Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.agent import Agent, AgentStatus

logger = get_logger(__name__)


class AgentRegistryService:
    """Central agent registry CRUD (#1754).

    Scope (#6828): database-backed CRUD for the agents table.  This is the
    **persistence** registry — canonical source of truth for agent metadata at
    startup/shutdown.  Does not track live health or in-process profile state.
    See also:
    - orchestration.agent_registry.AgentRegistry — static profile/capability registry
    - agents.agent_client.AgentRegistry — health-tracking runtime registry
    - agents.agent_orchestration.distributed_management.DistributedAgentManager — dynamic/distributed
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_agents(
        self,
        status_filter: str | None = None,
        limit: int = 100,
    ) -> List[Agent]:
        """Return all agents, optionally filtered by status (#1754)."""
        stmt = select(Agent).order_by(Agent.name).limit(limit)
        if status_filter:
            stmt = stmt.where(Agent.status == status_filter)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_agent_id(self, agent_id: str) -> Agent | None:
        """Fetch agent by canonical string ID (#1754)."""
        stmt = select(Agent).where(Agent.agent_id == agent_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        agent_id: str,
        name: str,
        description: str | None = None,
        agent_type: str = "worker",
        status: str = AgentStatus.ACTIVE.value,
    ) -> Agent:
        """Create or update an agent row (#1754)."""
        agent = await self.get_by_agent_id(agent_id)
        if agent:
            agent.name = name
            if description is not None:
                agent.description = description
            agent.agent_type = agent_type
            agent.status = status
        else:
            agent = Agent(
                agent_id=agent_id,
                name=name,
                description=description,
                agent_type=agent_type,
                status=status,
            )
            self.session.add(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return agent


async def seed_agents_from_config(session: AsyncSession) -> int:
    """Populate agents table from DEFAULT_AGENT_CONFIGS (#1754).

    Upserts so it's safe to call repeatedly (idempotent).
    Returns the number of agents upserted.
    """
    from api.agent_config import DEFAULT_AGENT_CONFIGS

    svc = AgentRegistryService(session)
    count = 0
    for agent_id, cfg in DEFAULT_AGENT_CONFIGS.items():
        _tier_map: Dict[int, str] = {
            1: "coordinator",
            2: "specialist",
            3: "specialist",
            4: "worker",
        }
        agent_type = _tier_map.get(cfg.get("priority", 3), "worker")
        await svc.upsert(
            agent_id=agent_id,
            name=cfg["name"],
            description=cfg.get("description"),
            agent_type=agent_type,
        )
        count += 1
    logger.info("Seeded %d agents into registry", count)
    return count
