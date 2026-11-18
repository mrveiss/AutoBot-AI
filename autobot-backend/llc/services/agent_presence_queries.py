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

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from sqlalchemy.sql import Select


def agent_org_nodes_with_latest_heartbeat(company_id: str) -> "Select":
    """AgentOrgNode LEFT JOINed to ONE heartbeat run per agent -- the run that says what it is doing.

    Shared by ``llc/api/agents.py::list_agents`` and
    ``protocols.agent_presence_feeds.sync_company_os_presence`` (#16947) --
    agent_id is the logical slug (the dual-keyspace column shared by
    heartbeat/controls/budgets), not the UUID PK; joining on the wrong one
    silently returns 0 rows in Postgres (see ``models.agent_org.AgentOrgNode``).

    Which run (#18654, owner ruling 2026-10-17): any RUNNING run wins, so an older
    run still working is never hidden behind a newer queued or finished one; among
    equals the newest by ``created_at``, then by ``id``. Exactly one run per agent,
    so a ``created_at`` tie no longer lists the agent twice.
    """
    from models.agent_org import AgentOrgNode

    from ..models.heartbeat_run import LLCHeartbeatRun

    chosen = _chosen_run_ids(company_id)
    return (
        select(AgentOrgNode, LLCHeartbeatRun)
        .outerjoin(
            LLCHeartbeatRun,
            (LLCHeartbeatRun.agent_id == AgentOrgNode.agent_id)
            # Agent slugs are not unique across companies.
            & (LLCHeartbeatRun.company_id == company_id) & LLCHeartbeatRun.id.in_(chosen),
        )
        .where(AgentOrgNode.company_id == company_id)
    )


def _chosen_run_ids(company_id: str) -> "Select":
    """The id of each agent's rank-1 run in *company_id*: running first, then newest, then highest id."""
    from ..models.enums import LLCRunStatus
    from ..models.heartbeat_run import LLCHeartbeatRun as run_model

    running_first = case((run_model.status == LLCRunStatus.RUNNING.value, 0), else_=1)
    ranked = (
        select(
            run_model.id.label("run_id"),
            func.row_number()
            .over(
                partition_by=run_model.agent_id,
                order_by=(running_first, run_model.created_at.desc(), run_model.id.desc()),
            )
            .label("rank"),
        )
        .where(run_model.company_id == company_id)
        .subquery()
    )
    return select(ranked.c.run_id).where(ranked.c.rank == 1)


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
