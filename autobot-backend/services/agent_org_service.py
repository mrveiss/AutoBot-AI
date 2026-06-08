# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Agent Org Service (#1405)

Business logic for agent organizational hierarchy: trees, chains of command,
direct reports, reporting-line updates with cycle detection, and role defaults.
"""

import uuid
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.agent_org import AgentOrgNode, OrgRole

logger = get_logger(__name__)

# Default permissions per org role (manager can delegate, workers execute)
_ROLE_DEFAULTS: Dict[str, Dict[str, Any]] = {
    OrgRole.MANAGER.value: {
        "can_delegate": True,
        "can_approve": True,
        "can_execute": True,
        "max_direct_reports": 10,
    },
    OrgRole.COORDINATOR.value: {
        "can_delegate": True,
        "can_approve": False,
        "can_execute": True,
        "max_direct_reports": 5,
    },
    OrgRole.SPECIALIST.value: {
        "can_delegate": False,
        "can_approve": False,
        "can_execute": True,
        "max_direct_reports": 0,
    },
    OrgRole.WORKER.value: {
        "can_delegate": False,
        "can_approve": False,
        "can_execute": True,
        "max_direct_reports": 0,
    },
}


class AgentOrgService:
    """Service for agent organizational hierarchy operations (#1405)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # -- Queries -----------------------------------------------------------

    async def get_all_nodes(self) -> List[AgentOrgNode]:
        """Fetch all org nodes in one query. Helper to avoid N+1 (#1405)."""
        result = await self.session.execute(select(AgentOrgNode))
        return list(result.scalars().all())

    async def get_node(self, agent_id: str) -> AgentOrgNode | None:
        """Return the org node for agent_id or None if not registered."""
        result = await self.session.execute(select(AgentOrgNode).where(AgentOrgNode.agent_id == agent_id))
        return result.scalar_one_or_none()

    # -- Tree / hierarchy --------------------------------------------------

    def _build_tree(self, nodes: List[AgentOrgNode], parent_id: str | None) -> List[Dict[str, Any]]:
        """Recursively build tree from flat node list. Helper (#1405)."""
        children = [n for n in nodes if n.reports_to == parent_id]
        return [
            {
                "agent_id": node.agent_id,
                "name": node.name,
                "org_role": node.org_role,
                "title": node.title,
                "capabilities": node.capabilities,
                "direct_reports_count": sum(1 for n in nodes if n.reports_to == node.agent_id),
                "children": self._build_tree(nodes, node.agent_id),
            }
            for node in children
        ]

    async def get_org_tree(self) -> List[Dict[str, Any]]:
        """
        Return recursive org tree from root agents (#1405).

        Root agents are those with reports_to == None.
        """
        nodes = await self.get_all_nodes()
        return self._build_tree(nodes, parent_id=None)

    async def get_chain_of_command(self, agent_id: str) -> List[Dict[str, Any]]:
        """
        Walk from agent_id up to the root (#1405).

        First entry is the agent itself; last is the root.
        Raises ValueError if agent_id is not found.
        """
        nodes = await self.get_all_nodes()
        index = {n.agent_id: n for n in nodes}

        if agent_id not in index:
            raise ValueError(f"Agent not found in org hierarchy: {agent_id!r}")

        chain: List[Dict[str, Any]] = []
        current_id: str | None = agent_id
        seen: set = set()

        while current_id is not None:
            if current_id in seen:
                logger.warning("Cycle detected in org hierarchy at %s", current_id)
                break
            seen.add(current_id)
            node = index.get(current_id)
            if node is None:
                break
            chain.append(
                {
                    "agent_id": node.agent_id,
                    "name": node.name,
                    "org_role": node.org_role,
                    "title": node.title,
                }
            )
            current_id = node.reports_to

        return chain

    async def get_direct_reports(self, agent_id: str) -> List[Dict[str, Any]]:
        """Return agents whose reports_to equals agent_id (#1405)."""
        result = await self.session.execute(select(AgentOrgNode).where(AgentOrgNode.reports_to == agent_id))
        nodes = result.scalars().all()
        return [
            {
                "agent_id": n.agent_id,
                "name": n.name,
                "org_role": n.org_role,
                "title": n.title,
            }
            for n in nodes
        ]

    # -- Cycle detection ---------------------------------------------------

    async def detect_cycle(self, agent_id: str, proposed_manager_id: str) -> bool:
        """
        Return True if assigning proposed_manager_id creates a cycle (#1405).

        Walk UP from proposed_manager_id; if we reach agent_id, it's a cycle.
        """
        nodes = await self.get_all_nodes()
        index = {n.agent_id: n for n in nodes}

        current: str | None = proposed_manager_id
        visited: set = set()

        while current is not None:
            if current == agent_id:
                return True
            if current in visited:
                break
            visited.add(current)
            node = index.get(current)
            current = node.reports_to if node else None

        return False

    # -- Updates -----------------------------------------------------------

    async def update_reporting_line(
        self,
        agent_id: str,
        new_manager_id: str | None,
        org_role: str | None = None,
        title: str | None = None,
        capabilities: str | None = None,
        company_id: str | None = None,
    ) -> AgentOrgNode:
        """
        Update reporting line with cycle detection (#1405).

        Raises ValueError on cycle or unknown agent.
        Triggers capability re-indexing into company KB when company_id is provided (#8244).
        """
        node = await self.get_node(agent_id)
        if node is None:
            raise ValueError(f"Agent not found in org hierarchy: {agent_id!r}")

        if new_manager_id is not None and new_manager_id != node.reports_to:
            if await self.detect_cycle(agent_id, new_manager_id):
                raise ValueError(f"Setting manager to {new_manager_id!r} " f"would create a cycle")
            node.reports_to = new_manager_id
        elif new_manager_id is None:
            node.reports_to = None

        if org_role is not None:
            node.org_role = org_role
        if title is not None:
            node.title = title
        if capabilities is not None:
            node.capabilities = capabilities
        if company_id is not None:
            node.company_id = company_id

        await self.session.flush()
        logger.info(
            "Updated org node agent_id=%s reports_to=%s role=%s",
            agent_id,
            node.reports_to,
            node.org_role,
        )

        effective_company_id = company_id or (str(node.company_id) if node.company_id else None)
        if effective_company_id:
            try:
                from llc.kb import AgentCapabilityIndexer

                await AgentCapabilityIndexer().index_from_db(agent_id, effective_company_id)
            except Exception:
                logger.exception("Capability re-index failed for agent %s (non-fatal)", agent_id)

        return node

    # -- Role defaults -----------------------------------------------------

    def get_role_defaults(self, role: str) -> Dict[str, Any]:
        """Return default permissions for the given org role (#1405)."""
        return dict(_ROLE_DEFAULTS.get(role, _ROLE_DEFAULTS[OrgRole.WORKER.value]))

    # -- Upsert ------------------------------------------------------------

    async def upsert_node(
        self,
        agent_id: str,
        name: str,
        org_role: str = OrgRole.WORKER.value,
        reports_to: str | None = None,
        title: str | None = None,
        capabilities: str | None = None,
        company_id: str | None = None,
    ) -> AgentOrgNode:
        """
        Create or update an agent_org_nodes record (#1405).

        Used to register agents in the hierarchy on demand.
        Triggers capability indexing into company KB when company_id is provided (#8244).
        """
        node = await self.get_node(agent_id)
        if node is None:
            node = AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name=name,
                org_role=org_role,
                reports_to=reports_to,
                title=title,
                capabilities=capabilities,
                company_id=company_id,
            )
            self.session.add(node)
            logger.info(
                "Registered new org node agent_id=%s role=%s",
                agent_id,
                org_role,
            )
        else:
            node.name = name
            node.org_role = org_role
            if reports_to is not None:
                node.reports_to = reports_to
            if title is not None:
                node.title = title
            if capabilities is not None:
                node.capabilities = capabilities
            if company_id is not None:
                node.company_id = company_id
            logger.info("Updated org node agent_id=%s", agent_id)

        await self.session.flush()

        effective_company_id = company_id or (str(node.company_id) if node.company_id else None)
        if effective_company_id:
            try:
                from llc.kb import AgentCapabilityIndexer

                await AgentCapabilityIndexer().index_from_db(agent_id, effective_company_id)
            except Exception:
                logger.exception("Capability index failed for agent %s (non-fatal)", agent_id)

        return node
