# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Agent Org Service (#1405)

Business logic for agent organizational hierarchy: trees, chains of command,
direct reports, reporting-line updates with cycle detection, and role defaults.
"""

import uuid
from typing import Any, Callable, Dict, List

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


# Map org roles onto the frontend activity-monitor agent "type" vocabulary
# (orchestrator | worker | monitor | analyzer | executor). (#10502)
_ROLE_TO_ACTIVITY_TYPE: Dict[str, str] = {
    OrgRole.MANAGER.value: "orchestrator",
    OrgRole.COORDINATOR.value: "orchestrator",
    OrgRole.SPECIALIST.value: "analyzer",
    OrgRole.WORKER.value: "worker",
}


def _normalise_company_id(company_id: "str | uuid.UUID | None") -> "uuid.UUID | None":
    """Coerce a company id to UUID before it reaches a comparison or the ORM.

    ``AgentOrgNode.company_id`` is ``UUID(as_uuid=True)``, so assigning a plain
    string fails at ``flush()`` on SQLite during binding — a valid caller with a
    valid id, failing at the write rather than at the door. Callers legitimately
    pass either form: the HTTP routes pass the tenant context's UUID, and older
    in-process callers pass strings.

    Normalising once means the tenant comparisons and the assignment all use the
    same type, rather than each site deciding for itself with ``str()`` and
    happening to agree.
    """
    if company_id is None:
        return None
    return company_id if isinstance(company_id, uuid.UUID) else uuid.UUID(str(company_id))


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
        return [self._subtree(node, nodes) for node in nodes if node.reports_to == parent_id]

    def _subtree(self, node: AgentOrgNode, nodes: List[AgentOrgNode]) -> Dict[str, Any]:
        """One node with its reports, recursively (#1405)."""
        return {
            "agent_id": node.agent_id,
            "name": node.name,
            "org_role": node.org_role,
            "title": node.title,
            "capabilities": node.capabilities,
            "direct_reports_count": sum(1 for n in nodes if n.reports_to == node.agent_id),
            "children": self._build_tree(nodes, node.agent_id),
        }

    async def get_org_tree(self, *, can_see: Callable[[Any], bool]) -> List[Dict[str, Any]]:
        """
        Return recursive org tree from root agents (#1405).

        Root agents are those with reports_to == None. ``can_see`` is the caller's
        company_id predicate (#19246), required so no caller can forget to scope: only
        visible agents are kept, and a visible agent whose manager is hidden becomes a root
        rather than disappearing.
        """
        nodes = [n for n in await self.get_all_nodes() if can_see(n.company_id)]
        visible = {n.agent_id for n in nodes}
        roots = [n for n in nodes if n.reports_to is None or n.reports_to not in visible]
        return [self._subtree(root, nodes) for root in roots]

    @staticmethod
    def _status_for_node(node: AgentOrgNode) -> str | None:
        """The one status the org registry knows: paused. Anything else is unmeasured (#17514)."""
        return "paused" if node.pre_pause_status is not None else None

    async def get_agent_statuses(self, *, can_see: Callable[[Any], bool]) -> List[Dict[str, Any]]:
        """Return all registered agents with runtime status (#10502).

        Backs ``GET /api/agents/status`` for the Home dashboard "Agent
        Activity Monitor", which previously 404'd and showed only a subset
        of agents. Sourced from the org registry so every registered agent
        is returned.
        """
        nodes = [n for n in await self.get_all_nodes() if can_see(n.company_id)]  # #19246: caller's view
        names = await self._company_names({n.company_id for n in nodes if n.company_id})
        # #17514: the registry measures no activity, so those fields are None ("not reported"),
        # never a 0 that reads as observed. The company tells two same-role agents apart.
        return [
            {
                "id": node.agent_id,
                "name": node.name,
                "type": _ROLE_TO_ACTIVITY_TYPE.get(node.org_role, "worker"),
                "status": self._status_for_node(node),
                "companyId": str(node.company_id) if node.company_id else None,
                "companyName": names.get(node.company_id),
                "recentTasks": [],
                "activityTimeline": [],
            }
            for node in nodes
        ]

    async def _company_names(self, company_ids: set) -> Dict[Any, str]:
        """company_id -> display name, in one query, for companies already in the caller's view."""
        if not company_ids:
            return {}
        from user_management.models.organization import Organization

        # A soft-deleted company is not named (Organization.deleted_at, the canonical soft-delete).
        rows = await self.session.execute(
            select(Organization.id, Organization.name).where(
                Organization.id.in_(company_ids), Organization.deleted_at.is_(None)
            )
        )
        return {company_id: name for company_id, name in rows.all()}

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
        company_id: "str | uuid.UUID | None" = None,
    ) -> AgentOrgNode:
        """
        Update reporting line with cycle detection (#1405).

        Raises ValueError on cycle or unknown agent.
        Triggers capability re-indexing into company KB when company_id is provided (#8244).
        """
        node = await self.get_node(agent_id)
        if node is None:
            raise ValueError(f"Agent not found in org hierarchy: {agent_id!r}")

        # Tenant scoping (#15794, CWE-862). ``get_node`` looks the target up by
        # ``agent_id`` alone, and ``new_manager_id`` was accepted as given, so a
        # caller holding admin.reporting_line.write could re-parent an agent in
        # ANY company and name a manager from any other. The permission answers
        # "may this caller edit reporting lines"; it cannot answer "whose".
        #
        # Enforced only when a company is supplied, because this service is also
        # called from paths that legitimately have no tenant (seeding, and the
        # pre-tenancy callers). Those pass None and are unchanged; the HTTP
        # routes always pass the caller's own context, never a body value.
        company_uuid = _normalise_company_id(company_id)
        if company_uuid is not None:
            if node.company_id != company_uuid:
                raise ValueError(f"Agent not found in org hierarchy: {agent_id!r}")
            if new_manager_id is not None:
                manager = await self.get_node(new_manager_id)
                if manager is None or manager.company_id != company_uuid:
                    raise ValueError(f"Manager not in this company: {new_manager_id!r}")

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
        if company_uuid is not None:
            node.company_id = company_uuid

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
        company_id: "str | uuid.UUID | None" = None,
    ) -> AgentOrgNode:
        """
        Create or update an agent_org_nodes record (#1405).

        Used to register agents in the hierarchy on demand.
        Triggers capability indexing into company KB when company_id is provided (#8244).
        """
        node = await self.get_node(agent_id)

        # Tenant scoping (#15794). Same reasoning as update_reporting_line: the
        # permission says the caller may edit reporting lines, not whose. An
        # existing node belonging to another company must read as absent rather
        # than be updated, and a manager must be in this company.
        #
        # Absent, not forbidden: a distinct error would tell an unauthorised
        # caller that an agent exists in a company they cannot see.
        company_uuid = _normalise_company_id(company_id)
        if company_uuid is not None:
            if node is not None and node.company_id != company_uuid:
                raise ValueError(f"Agent not found in org hierarchy: {agent_id!r}")
            if reports_to is not None:
                manager = await self.get_node(reports_to)
                if manager is None or manager.company_id != company_uuid:
                    raise ValueError(f"Manager not in this company: {reports_to!r}")

        if node is None:
            if company_uuid is not None:
                # A NEW node in a company that gates hires is a hire: it goes through the approval (#8214).
                from llc.services.agent_hire_service import refuse_unapproved_hire  # noqa: PLC0415 -- llc layer

                await refuse_unapproved_hire(self.session, company_uuid)
            node = AgentOrgNode(
                id=uuid.uuid4(),
                agent_id=agent_id,
                name=name,
                org_role=org_role,
                reports_to=reports_to,
                title=title,
                capabilities=capabilities,
                company_id=company_uuid,
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
                node.company_id = company_uuid
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
