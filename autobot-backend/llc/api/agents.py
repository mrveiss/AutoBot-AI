# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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
    """List LLC agents for the org with their latest heartbeat summary (GH#8549).

    Returns one row per distinct agent_id that has at least one heartbeat run
    scoped to the caller's org.  Heartbeat-enabled status and last-run data are
    derived from LLCHeartbeatRun rows.
    """
    effective_company_id = company_id or str(ctx.org_id)

    # Subquery: latest run per agent
    subq = (
        select(
            LLCHeartbeatRun.agent_id,
            func.max(LLCHeartbeatRun.created_at).label("latest_at"),
        )
        .where(LLCHeartbeatRun.company_id == effective_company_id)
        .group_by(LLCHeartbeatRun.agent_id)
        .subquery()
    )
    result = await session.execute(
        select(LLCHeartbeatRun)
        .join(
            subq,
            (LLCHeartbeatRun.agent_id == subq.c.agent_id) & (LLCHeartbeatRun.created_at == subq.c.latest_at),
        )
        .order_by(LLCHeartbeatRun.agent_id)
    )
    rows = result.scalars().all()

    return [
        {
            "id": run.agent_id,
            "name": run.agent_id,
            "heartbeat_enabled": True,
            "last_heartbeat_at": run.started_at.isoformat() if run.started_at else None,
            "last_run_status": run.status,
            "current_run_started_at": (
                run.started_at.isoformat() if run.status == "running" and run.started_at else None
            ),
        }
        for run in rows
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
