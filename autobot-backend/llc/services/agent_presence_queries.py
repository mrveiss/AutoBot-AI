# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read-only queries shared by an API route and a non-request caller (#16965).

Moved out of ``llc/api/agents.py`` (a FastAPI router module) so that
``protocols/agent_presence_feeds.py`` -- a plain module with no request
context, run from a background task -- does not import a router to reach
one query. Same shape as ``org_chart_rows.py``: extracted queries, imports
kept inside the functions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.sql import Select


def agent_org_nodes_with_latest_heartbeat(company_id: str) -> "Select":
    """AgentOrgNode LEFT JOINed to each agent's own latest heartbeat run.

    Shared by ``llc/api/agents.py::list_agents`` and
    ``protocols.agent_presence_feeds.sync_company_os_presence`` (#16947) --
    agent_id is the logical slug (the dual-keyspace column shared by
    heartbeat/controls/budgets), not the UUID PK; joining on the wrong one
    silently returns 0 rows in Postgres (see ``models.agent_org.AgentOrgNode``).
    """
    from sqlalchemy import func, select

    from models.agent_org import AgentOrgNode

    from ..models.heartbeat_run import LLCHeartbeatRun

    latest_runs = (
        select(LLCHeartbeatRun.agent_id, func.max(LLCHeartbeatRun.created_at).label("latest_at"))
        .where(LLCHeartbeatRun.company_id == company_id)
        .group_by(LLCHeartbeatRun.agent_id)
        .subquery()
    )
    return (
        select(AgentOrgNode, LLCHeartbeatRun)
        .outerjoin(latest_runs, latest_runs.c.agent_id == AgentOrgNode.agent_id)
        .outerjoin(
            LLCHeartbeatRun,
            (LLCHeartbeatRun.agent_id == latest_runs.c.agent_id)
            & (LLCHeartbeatRun.created_at == latest_runs.c.latest_at),
        )
        .where(AgentOrgNode.company_id == company_id)
    )


async def distinct_company_ids_with_agents(session: AsyncSession) -> list[str]:
    """Every company that has at least one org-chart agent (#16965).

    The presence-sync background task has no per-request tenant to scope
    to -- it is the one caller that legitimately needs every tenant, once
    per sweep, so this is deliberately not exposed as an API route.
    """
    from sqlalchemy import select

    from models.agent_org import AgentOrgNode

    result = await session.execute(select(AgentOrgNode.company_id).distinct())
    return [str(company_id) for company_id in result.scalars().all()]
