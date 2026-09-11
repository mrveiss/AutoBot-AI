# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""How each agent on the org chart is doing: latest heartbeat and open work.

Extracted from ``companies.py::get_org_chart``, which the function-length gate
blocks above 65 lines, while ``companies.py`` is grandfathered at a fixed size
and may not grow (#14236) -- so, as with ``org_chart_placement``, the cut has to
leave the file. The seam: these two queries enrich agents that already exist;
the route still gathers the hierarchy and budget rows and composes the nodes.

Imports stay inside the functions, as they were inside the route.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Dict

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from llc.models.heartbeat_run import LLCHeartbeatRun


async def latest_runs_by_agent(session: AsyncSession, company_id: uuid.UUID) -> Dict[str, "LLCHeartbeatRun"]:
    """The most recent heartbeat run per agent in the company (status + liveness)."""
    from sqlalchemy import func, select

    from llc.models.heartbeat_run import LLCHeartbeatRun

    subq = (
        select(
            LLCHeartbeatRun.agent_id,
            func.max(LLCHeartbeatRun.created_at).label("latest_at"),
        )
        .where(LLCHeartbeatRun.company_id == company_id)
        .group_by(LLCHeartbeatRun.agent_id)
        .subquery()
    )
    latest_runs = (
        (
            await session.execute(
                select(LLCHeartbeatRun).join(
                    subq,
                    (LLCHeartbeatRun.agent_id == subq.c.agent_id) & (LLCHeartbeatRun.created_at == subq.c.latest_at),
                )
            )
        )
        .scalars()
        .all()
    )
    return {r.agent_id: r for r in latest_runs}


async def assigned_counts_by_agent(session: AsyncSession, company_id: uuid.UUID) -> Dict[str, int]:
    """Unfinished work items assigned to each agent -- one grouped query, no N+1.

    "Assigned" means the item has an ``assignee_agent_id`` matching the
    ``AgentOrgNode.id`` (UUID PK) AND the item is not yet in a terminal state.
    The join goes through ``AgentOrgNode`` so the result is keyed by
    ``AgentOrgNode.agent_id`` -- the logical string slug used everywhere else --
    not the UUID PK, which handles hire-generated slugs that differ from the PK.
    GH#9980: enum members are used directly so PG serialises lowercase values.
    """
    from sqlalchemy import func, select

    from llc.models.enums import WorkItemStatus
    from llc.models.work_item import LLCWorkItem
    from models.agent_org import AgentOrgNode

    assign_q = (
        select(
            AgentOrgNode.agent_id,
            func.count(LLCWorkItem.id).label("cnt"),
        )
        .join(AgentOrgNode, AgentOrgNode.id == LLCWorkItem.assignee_agent_id)
        .where(
            LLCWorkItem.company_id == company_id,
            LLCWorkItem.assignee_agent_id.isnot(None),
            LLCWorkItem.status.notin_([WorkItemStatus.DONE, WorkItemStatus.CANCELLED]),
        )
        .group_by(AgentOrgNode.agent_id)
    )
    return {row.agent_id: row.cnt for row in (await session.execute(assign_q)).all()}
