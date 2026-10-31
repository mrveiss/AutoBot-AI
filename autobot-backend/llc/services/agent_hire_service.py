# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Hiring an agent into a company -- the one place a hired agent is made live (GH#8214).

``POST /companies/{id}/agent-hires`` and the HIRE approval hook both end here, so an
approved hire creates exactly what an unapproved one used to: one ``agent_org_nodes`` row,
its budget row, and (after commit) its heartbeat schedule entry. Before a hire is approved
none of these exist -- the request is only a pending approval whose payload is
:class:`HirePayload`.
"""

import uuid
from typing import TYPE_CHECKING, Any, Dict, Optional

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from models.agent_org import AgentOrgNode
from models.approval import ApprovalType
from user_management.models.organization import Organization

from .budget import BudgetService

if TYPE_CHECKING:  # approval.py imports this module through approval_hooks
    from .approval import ApprovalService

logger = get_logger(__name__)


class HirePayload(BaseModel):
    """Everything needed to create the agent, frozen when the hire is requested."""

    agent_id: str
    agent_name: str
    org_role: str
    title: Optional[str] = None
    capabilities: Optional[str] = None
    reports_to: Optional[str] = None
    heartbeat_cron: Optional[str] = None
    heartbeat_enabled: bool = False
    adapter_type: str = "claude_code"
    adapter_config: Dict[str, Any]
    model: str
    instructions_file_path: str


class HireApprovalRequiredError(Exception):
    """A company that requires board approval for hires was asked to add an agent another way (GH#8214)."""

    def __init__(self, company_id: uuid.UUID) -> None:
        self.company_id = company_id
        super().__init__(
            f"Company {company_id} requires board approval for hires; "
            f"request the hire through POST /companies/{company_id}/agent-hires"
        )


class AgentHirePending(BaseModel):
    """Answer to a hire that needs board approval: the request exists, the agent does not (GH#8214)."""

    status: str = "pending_approval"
    approval_id: str
    company_id: str
    agent_name: str


async def company_requires_hire_approval(session: AsyncSession, company_id: uuid.UUID) -> bool:
    """Whether *company_id* has ``require_approval_for_hires`` on; an unknown company does not."""
    row = await session.execute(select(Organization.require_approval_for_hires).where(Organization.id == company_id))
    return bool(row.scalar_one_or_none())


async def refuse_unapproved_hire(session: AsyncSession, company_id: uuid.UUID) -> None:
    """Raise :class:`HireApprovalRequiredError` when *company_id* gates hires; for every other way to add an agent.

    Exempt on purpose, each with its reason at the call site: the company's first (default CEO) agent, and
    an import into a company the import itself creates.
    """
    if await company_requires_hire_approval(session, company_id):
        raise HireApprovalRequiredError(company_id)


async def insert_hired_agent(session: AsyncSession, company_id: uuid.UUID, hire: HirePayload) -> uuid.UUID:
    """Create the live agent and its budget in the caller's transaction; return the node id."""
    node_id = uuid.uuid4()
    session.add(
        AgentOrgNode(
            id=node_id,
            agent_id=hire.agent_id,
            name=hire.agent_name,
            org_role=hire.org_role,
            title=hire.title,
            capabilities=hire.capabilities,
            company_id=company_id,
            reports_to=hire.reports_to,
            heartbeat_cron=hire.heartbeat_cron,
            heartbeat_enabled=hire.heartbeat_enabled,
            adapter_type=hire.adapter_type,
            adapter_config=hire.adapter_config,
            model=hire.model,
            instructions_file_path=hire.instructions_file_path,
        )
    )
    await session.flush()
    # Auto-provision a budget row for the newly hired agent (GH#9901); idempotent.
    await BudgetService().provision_budget(session, hire.agent_id, str(company_id))
    return node_id


async def schedule_hired_agent(hire: HirePayload) -> None:
    """Put a heartbeat-enabled hire on the schedule (#15907). Call only after the commit."""
    if hire.heartbeat_enabled and hire.heartbeat_cron:
        from ..scheduler.schedule_entry import schedule_heartbeat  # noqa: PLC0415 -- heavy scheduler import

        await schedule_heartbeat(hire.agent_id, hire.heartbeat_cron)


async def request_hire_approval(
    session: AsyncSession,
    svc: "ApprovalService",
    company_id: uuid.UUID,
    hire: HirePayload,
    requested_by_user: uuid.UUID,
) -> AgentHirePending:
    """Record the hire as a pending approval and commit it.

    No agent, budget or schedule entry exists until the board approves it.
    """
    approval = await svc.request_approval(
        session,
        company_id=company_id,
        gate_type=ApprovalType.HIRE,
        payload=hire.model_dump(mode="json"),
        requested_by=str(requested_by_user),
        actor_user_id=requested_by_user,
    )
    await session.commit()
    await svc.publish_requested(approval)
    logger.info("Hire of %r awaits approval %s (company=%s)", hire.agent_name, approval.id, company_id)
    return AgentHirePending(approval_id=str(approval.id), company_id=str(company_id), agent_name=hire.agent_name)
