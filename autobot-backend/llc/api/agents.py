# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC agent heartbeat API routes (GH#8225).

Routes:
  POST  /api/llc/agents/{agent_id}/heartbeat/trigger
  GET   /api/llc/agents/{agent_id}/runs
  GET   /api/llc/agents/{agent_id}/runs/{run_id}
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, get_tenant_context
from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..models.enums import HeartbeatRunStatus
from ..models.heartbeat_run import LLCHeartbeatRun
from ..scheduler.heartbeat_scheduler import HeartbeatScheduler

router = APIRouter(prefix="/agents", tags=["llc-agents"])

_get_scheduler = lazy_singleton(HeartbeatScheduler)


def _scheduler() -> HeartbeatScheduler:
    return _get_scheduler()


# ------------------------------------------------------------------
# Response schemas
# ------------------------------------------------------------------


class HeartbeatRunRead(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    agent_id: str
    invocation_source: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    external_run_id: Optional[str] = None
    context_snapshot: Optional[Dict[str, Any]] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class HeartbeatRunList(BaseModel):
    items: List[HeartbeatRunRead]
    total: int
    page: int
    page_size: int


class TriggerResponse(BaseModel):
    run_id: uuid.UUID
    status: str


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------


@router.post("/{agent_id}/heartbeat/trigger", response_model=TriggerResponse, status_code=202)
async def trigger_heartbeat(
    agent_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
) -> TriggerResponse:
    """Manually trigger a heartbeat run for *agent_id* immediately."""
    sched = _scheduler()
    try:
        run, agent_cfg = await sched.trigger_manual(session, agent_id)
        await session.commit()
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    sched.dispatch_run(agent_cfg, run.id)
    return TriggerResponse(run_id=run.id, status=run.status)


@router.get("/{agent_id}/runs", response_model=HeartbeatRunList)
async def list_runs(
    agent_id: str,
    status: Optional[HeartbeatRunStatus] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
) -> HeartbeatRunList:
    """List heartbeat runs for *agent_id*, paginated, optionally filtered by status."""
    stmt = (
        select(LLCHeartbeatRun)
        .where(LLCHeartbeatRun.agent_id == agent_id)
        .order_by(LLCHeartbeatRun.created_at.desc())
    )
    if ctx.org_id is not None:
        stmt = stmt.where(LLCHeartbeatRun.company_id == ctx.org_id)
    if status is not None:
        stmt = stmt.where(LLCHeartbeatRun.status == status.value)

    count_result = await session.execute(stmt.with_only_columns(LLCHeartbeatRun.id))
    total = len(count_result.scalars().all())

    offset = (page - 1) * page_size
    paginated = stmt.offset(offset).limit(page_size)
    result = await session.execute(paginated)
    runs = result.scalars().all()

    return HeartbeatRunList(
        items=[HeartbeatRunRead.model_validate(r) for r in runs],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{agent_id}/runs/{run_id}", response_model=HeartbeatRunRead)
async def get_run(
    agent_id: str,
    run_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(get_tenant_context),
) -> HeartbeatRunRead:
    """Fetch a single heartbeat run with its context snapshot."""
    filters = [
        LLCHeartbeatRun.id == run_id,
        LLCHeartbeatRun.agent_id == agent_id,
    ]
    if ctx.org_id is not None:
        filters.append(LLCHeartbeatRun.company_id == ctx.org_id)
    result = await session.execute(
        select(LLCHeartbeatRun).where(*filters)
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return HeartbeatRunRead.model_validate(run)
