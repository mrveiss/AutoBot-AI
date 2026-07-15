# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC agent heartbeat trigger API (GH#8225).

Routes:
  GET   /api/llc/agents              — list agents + latest heartbeat summary (GH#8549)
  POST  /api/llc/agents/{agent_id}/heartbeat/trigger

Run listing and detail are served by llc/api/runs.py
(GET /api/llc/agents/{agent_id}/runs[/{run_id}]) to avoid prefix collision.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from models.agent_org import AgentOrgNode
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..models.heartbeat_run import LLCHeartbeatRun
from ..scheduler.heartbeat_scheduler import get_heartbeat_scheduler

logger = get_logger(__name__)
router = APIRouter(prefix="/agents", tags=["llc-agents"])


class TriggerResponse(BaseModel):
    run_id: uuid.UUID
    status: str


@router.get("", response_model=List[Dict[str, Any]])
async def list_agents(
    company_id: Optional[str] = Query(None, description="Filter by company UUID"),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """List LLC agents for the org with their latest heartbeat summary (GH#8549, #11366).

    Returns the full company roster from the org chart (``AgentOrgNode``) — every
    agent, not just those with heartbeat history — each with its human-readable
    name and its latest heartbeat run (LEFT JOIN) for status.  This lets assignee
    pickers (Routines, Heartbeat monitor) list freshly-provisioned agents and show
    names instead of opaque ids.
    """
    effective_company_id = company_id or str(ctx.org_id)

    # Latest heartbeat run per agent, keyed by the logical agent_id *slug* — the
    # dual-keyspace column shared by heartbeat/controls/budgets, NOT the UUID PK
    # (joining on the wrong one silently returns 0 rows in Postgres; see AgentOrgNode).
    latest_runs = (
        select(
            LLCHeartbeatRun.agent_id,
            func.max(LLCHeartbeatRun.created_at).label("latest_at"),
        )
        .where(LLCHeartbeatRun.company_id == effective_company_id)
        .group_by(LLCHeartbeatRun.agent_id)
        .subquery()
    )

    # Full roster from the org chart, LEFT JOINed to each agent's latest run.
    result = await session.execute(
        select(AgentOrgNode, LLCHeartbeatRun)
        .outerjoin(latest_runs, latest_runs.c.agent_id == AgentOrgNode.agent_id)
        .outerjoin(
            LLCHeartbeatRun,
            (LLCHeartbeatRun.agent_id == latest_runs.c.agent_id)
            & (LLCHeartbeatRun.created_at == latest_runs.c.latest_at),
        )
        .where(AgentOrgNode.company_id == effective_company_id)
        .order_by(AgentOrgNode.name)
    )

    return [
        {
            # Logical agent_id slug — kept as `id` for backward compatibility with
            # the heartbeat monitor; also exposed explicitly as `agent_id`.
            "id": node.agent_id,
            "agent_id": node.agent_id,
            # UUID PK — the keyspace work-item / routine assignees are stored in
            # (llc_work_items.assignee_agent_id); assignee pickers POST this value.
            "org_node_id": str(node.id),
            "name": node.name,
            "org_role": node.org_role,
            "title": node.title,
            "heartbeat_enabled": node.heartbeat_enabled,
            "last_heartbeat_at": (
                run.started_at.isoformat()
                if run is not None and run.started_at
                else (node.last_heartbeat_at.isoformat() if node.last_heartbeat_at else None)
            ),
            "last_run_status": run.status if run is not None else None,
            "current_run_started_at": (
                run.started_at.isoformat() if run is not None and run.status == "running" and run.started_at else None
            ),
        }
        for node, run in result.all()
    ]


@router.post("/{agent_id}/heartbeat/trigger", response_model=TriggerResponse, status_code=202)
async def trigger_heartbeat(
    agent_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> TriggerResponse:
    """Manually trigger a heartbeat run for *agent_id* immediately.

    Requires an authenticated user with org context. The agent must belong to
    the caller's organization — cross-tenant triggers are rejected with 404
    (same response as "not found" to prevent agent-ID enumeration).
    """
    sched = get_heartbeat_scheduler()
    try:
        run, agent_cfg = await sched.trigger_manual(session, agent_id)
    except ValueError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error")

    agent_company = agent_cfg.get("company_id")
    if agent_company is not None and agent_company != ctx.org_id:
        # Return 404 (not 403) to prevent cross-tenant agent-ID enumeration oracle
        raise HTTPException(status_code=404, detail=f"Agent {agent_id!r} not found or not configured")

    await session.commit()
    sched.dispatch_run(agent_cfg, run.id)
    return TriggerResponse(run_id=run.id, status=run.status)
