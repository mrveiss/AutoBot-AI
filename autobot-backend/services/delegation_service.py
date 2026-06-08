# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Delegation Service (#1753)

Assigns tasks from managers to direct reports, escalates stuck tasks
up the chain of command, and provides activity summaries.
"""

from typing import Any, Dict, List

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.task_delegation import DelegationStatus, TaskDelegation
from services.agent_org_service import AgentOrgService

logger = get_logger(__name__)


class DelegationService:
    """Task delegation and escalation operations (#1753)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self._org = AgentOrgService(session)

    async def delegate_task(
        self,
        delegator_id: str,
        assignee_id: str,
        task_description: str,
        context: Dict[str, Any] | None = None,
    ) -> TaskDelegation:
        """
        Assign a task from delegator to assignee (#1753).

        Validates that:
        - delegator has can_delegate permission (manager/coordinator)
        - assignee is a direct report of delegator
        """
        delegator = await self._org.get_node(delegator_id)
        if delegator is None:
            raise ValueError(f"Delegator {delegator_id!r} not in org hierarchy")

        defaults = self._org.get_role_defaults(delegator.org_role)
        if not defaults.get("can_delegate"):
            raise ValueError(f"Agent {delegator_id!r} (role={delegator.org_role}) " "cannot delegate tasks")

        reports = await self._org.get_direct_reports(delegator_id)
        report_ids = {r["agent_id"] for r in reports}
        if assignee_id not in report_ids:
            raise ValueError(f"Agent {assignee_id!r} is not a direct report " f"of {delegator_id!r}")

        delegation = TaskDelegation(
            delegator_id=delegator_id,
            assignee_id=assignee_id,
            task_description=task_description,
            context=context,
            status=DelegationStatus.PENDING.value,
        )
        self.session.add(delegation)
        await self.session.commit()
        await self.session.refresh(delegation)

        logger.info(
            "Task delegated: %s -> %s (id=%s)",
            delegator_id,
            assignee_id,
            delegation.id,
        )
        return delegation

    async def escalate_task(self, delegation_id: str) -> TaskDelegation:
        """
        Escalate a failed/stuck task up the chain of command (#1753).

        Finds the next manager above the delegator and marks the
        delegation as escalated.
        """
        delegation = await self._get_or_raise(delegation_id)

        chain = await self._org.get_chain_of_command(delegation.delegator_id)
        escalation_target = None
        for i, link in enumerate(chain):
            if link["agent_id"] == delegation.delegator_id and i + 1 < len(chain):
                escalation_target = chain[i + 1]["agent_id"]
                break

        if escalation_target is None:
            raise ValueError(f"No manager above {delegation.delegator_id!r} to escalate to")

        delegation.status = DelegationStatus.ESCALATED.value
        delegation.escalated_to = escalation_target
        await self.session.commit()
        await self.session.refresh(delegation)

        logger.info("Task %s escalated to %s", delegation_id, escalation_target)
        return delegation

    async def update_status(
        self,
        delegation_id: str,
        new_status: str,
        result: Dict[str, Any] | None = None,
    ) -> TaskDelegation:
        """Update delegation status and optional result (#1753)."""
        delegation = await self._get_or_raise(delegation_id)
        delegation.status = new_status
        if result is not None:
            delegation.result = result
        await self.session.commit()
        await self.session.refresh(delegation)
        return delegation

    async def get_delegation(self, delegation_id: str) -> TaskDelegation | None:
        """Fetch a single delegation by ID (#1753)."""
        import uuid

        stmt = select(TaskDelegation).where(TaskDelegation.id == uuid.UUID(delegation_id))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_activity_summary(self, manager_id: str) -> Dict[str, Any]:
        """
        Aggregate activity for all direct reports (#1753).

        Returns counts by status for tasks delegated by manager_id.
        """
        stmt = (
            select(
                TaskDelegation.status,
                func.count(TaskDelegation.id).label("count"),
            )
            .where(TaskDelegation.delegator_id == manager_id)
            .group_by(TaskDelegation.status)
        )
        result = await self.session.execute(stmt)
        rows = result.all()

        by_status = {row.status: row.count for row in rows}
        return {
            "manager_id": manager_id,
            "total_delegated": sum(by_status.values()),
            "by_status": by_status,
        }

    async def list_delegations(
        self,
        agent_id: str,
        role: str = "delegator",
        status_filter: str | None = None,
        limit: int = 50,
    ) -> List[TaskDelegation]:
        """List delegations where agent_id is delegator or assignee (#1753)."""
        col = TaskDelegation.delegator_id if role == "delegator" else TaskDelegation.assignee_id
        stmt = select(TaskDelegation).where(col == agent_id).order_by(TaskDelegation.created_at.desc()).limit(limit)
        if status_filter:
            stmt = stmt.where(TaskDelegation.status == status_filter)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def _get_or_raise(self, delegation_id: str) -> TaskDelegation:
        """Load delegation or raise ValueError (#1753)."""
        delegation = await self.get_delegation(delegation_id)
        if delegation is None:
            raise ValueError(f"Delegation {delegation_id!r} not found")
        return delegation
