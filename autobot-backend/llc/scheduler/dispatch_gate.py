# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The one gate every Company OS agent run passes before it starts (#19240).

Heartbeat, manual and event wakes, routines and the liveness monitor all ask here.
The answer is a reason string, or ``None`` when the agent may run. Budget is read
before the run because cost is only ingested after it: without the pre-run check,
an exhausted agent keeps spending until the watchdog next sweeps.

Agents have two id keyspaces (see ``models/reporting_line.py``). Pause flags and
budgets are keyed by the slug, routines hold the node's UUID, so a reference is
resolved to its node before either is read.
"""

import logging
import uuid
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.redis_client import get_async_redis_client
from models.agent_org import AgentOrgNode

from ..models.enums import UNDISPATCHABLE_AGENT_STATUSES, LLCAgentStatus
from ..services.budget import BudgetService

logger = logging.getLogger(__name__)

#: The reason text a caller may need to tell apart: replay answers it with a 402.
BUDGET_EXHAUSTED = "budget is exhausted"

#: What the board did on purpose. ``inactive`` is left out: the budget watchdog
#: writes it, and a dead run of an over-budget agent must still release its claims.
_DELIBERATE_STOP_STATUSES = frozenset({LLCAgentStatus.PAUSED.value, LLCAgentStatus.TERMINATED.value})


class AgentNotDispatchable(ValueError):
    """A run was requested for an agent the gate refuses."""

    def __init__(self, agent_id: str, company_id: Any, reason: str) -> None:
        super().__init__(f"Agent {agent_id} cannot run: {reason}")
        self.company_id = company_id
        self.reason = reason


def as_uuid(value: Any) -> Optional[uuid.UUID]:
    """*value* as a UUID, or ``None`` when it is not one (a slug, say)."""
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


async def resolve_agent(session: AsyncSession, company_id: Any, agent_ref: Any) -> Any:
    """The ``(agent_id, status)`` row for a slug or node PK within *company_id*, or ``None``."""
    match = AgentOrgNode.agent_id == str(agent_ref)
    node_pk = as_uuid(agent_ref)
    if node_pk is not None:
        match = or_(match, AgentOrgNode.id == node_pk)
    result = await session.execute(
        select(AgentOrgNode.agent_id, AgentOrgNode.status).where(AgentOrgNode.company_id == company_id, match).limit(1)
    )
    return result.first()


async def _pause_flag_reason(slug: Optional[str], company_id: Optional[Any]) -> Optional[str]:
    """The controls keys. Redis down leaves the status column, which every pause also writes."""
    redis = await get_async_redis_client()
    if redis is None:
        return None
    if company_id and await redis.exists(f"llc:company:{company_id}:paused"):
        return "company is paused"
    if slug and await redis.exists(f"llc:agent:{slug}:paused"):
        return "agent is paused"
    return None


async def dispatch_block_reason(
    session: AsyncSession,
    agent_id: str,
    company_id: Any,
    status: Optional[str],
    *,
    deliberate_only: bool = False,
) -> Optional[str]:
    """Why this resolved agent must not run, or ``None``.

    ``deliberate_only`` is the liveness monitor's question: was this one agent stopped
    on purpose? A budget stop and a company pause are not that. A company pause writes
    only its Redis key and leaves dead runs holding their claims unless they are recovered.
    An exception, from Redis or the budget read, propagates: unknown is not "may run".
    """
    blocked = _DELIBERATE_STOP_STATUSES if deliberate_only else UNDISPATCHABLE_AGENT_STATUSES
    if status in blocked:
        return f"agent status is {status}"
    reason = await _pause_flag_reason(agent_id, None if deliberate_only else company_id)
    if reason is None and not deliberate_only and company_id:
        _, over_limit, _ = await BudgetService().check_budget(session, agent_id, str(company_id))
        reason = BUDGET_EXHAUSTED if over_limit else None
    return reason


async def agent_ref_block_reason(
    session: AsyncSession,
    agent_ref: Any,
    company_id: Any,
    *,
    deliberate_only: bool = False,
) -> Optional[str]:
    """:func:`dispatch_block_reason` for a caller holding a slug, a node PK, or no agent at all."""
    company_uuid = as_uuid(company_id)
    row = await resolve_agent(session, company_uuid, agent_ref) if agent_ref and company_uuid else None
    if row is None:  # no agent to judge: only the flags remain
        slug = str(agent_ref) if agent_ref else None
        return await _pause_flag_reason(slug, None if deliberate_only else company_id)
    return await dispatch_block_reason(session, row[0], company_id, row[1], deliberate_only=deliberate_only)


async def require_dispatchable(session: AsyncSession, agent: dict) -> None:
    """Raise :class:`AgentNotDispatchable` when *agent*'s config row may not run."""
    company_id = agent.get("company_id")
    reason = await dispatch_block_reason(session, agent["agent_id"], company_id, agent.get("status"))
    if reason is not None:
        raise AgentNotDispatchable(agent["agent_id"], company_id, reason)
