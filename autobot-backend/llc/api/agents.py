# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC agent heartbeat trigger API (GH#8225).

Routes:
  POST  /api/llc/agents/{agent_id}/heartbeat/trigger

Run listing and detail are served by llc/api/runs.py
(GET /api/llc/agents/{agent_id}/runs[/{run_id}]) to avoid prefix collision.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..scheduler.heartbeat_scheduler import HeartbeatScheduler

router = APIRouter(prefix="/agents", tags=["llc-agents"])

_get_scheduler = lazy_singleton(HeartbeatScheduler)


def _scheduler() -> HeartbeatScheduler:
    return _get_scheduler()


class TriggerResponse(BaseModel):
    run_id: uuid.UUID
    status: str


@router.post("/{agent_id}/heartbeat/trigger", response_model=TriggerResponse, status_code=202)
async def trigger_heartbeat(
    agent_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> TriggerResponse:
    """Manually trigger a heartbeat run for *agent_id* immediately.

    Requires an authenticated user with org context. The agent must belong to
    the caller's organization — cross-tenant triggers are rejected with 403.
    """
    sched = _scheduler()
    try:
        run, agent_cfg = await sched.trigger_manual(session, agent_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    agent_company = agent_cfg.get("company_id")
    if agent_company is not None and agent_company != ctx.org_id:
        raise HTTPException(status_code=403, detail="Agent belongs to a different organization")

    await session.commit()
    sched.dispatch_run(agent_cfg, run.id)
    return TriggerResponse(run_id=run.id, status=run.status)
