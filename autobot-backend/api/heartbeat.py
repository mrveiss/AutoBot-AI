# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Heartbeat API (#1407)

Endpoints for heartbeat configuration, run history, wakeup requests,
and agent runtime state inspection.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from fastapi import APIRouter, Depends, HTTPException, Query, status
from models.heartbeat import (
    AgentRuntimeState,
    AgentWakeupRequest,
    HeartbeatRun,
    HeartbeatRunEvent,
    WakeupTrigger,
)
from pydantic import BaseModel, Field
from services.heartbeat_scheduler import HeartbeatScheduler, _get_or_create_state
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

logger = logging.getLogger(__name__)
router = APIRouter()

_scheduler: Optional[HeartbeatScheduler] = None


def configure_scheduler(scheduler: HeartbeatScheduler) -> None:
    """Inject the shared HeartbeatScheduler instance (#1407)."""
    global _scheduler
    _scheduler = scheduler


def _get_scheduler() -> HeartbeatScheduler:
    """FastAPI dependency: return the active scheduler or 503."""
    if _scheduler is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Heartbeat scheduler not initialised",
        )
    return _scheduler


class HeartbeatConfigRequest(BaseModel):
    """Request body to configure heartbeat for an agent."""

    heartbeat_enabled: bool = False
    heartbeat_interval_seconds: int = Field(default=300, ge=10)
    max_run_duration_seconds: int = Field(default=600, ge=10)


class HeartbeatConfigResponse(BaseModel):
    """Response for agent heartbeat config / runtime state."""

    agent_id: str
    heartbeat_enabled: bool
    heartbeat_interval_seconds: int
    max_run_duration_seconds: int
    current_task_id: Optional[str]
    last_heartbeat_at: Optional[str]
    session_params: Optional[Dict[str, Any]]
    extra: Optional[Dict[str, Any]]
    created_at: Optional[str]
    updated_at: Optional[str]


class WakeupRequestCreate(BaseModel):
    """Request body to queue a wakeup for an agent."""

    priority: int = 0
    context: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


class WakeupRequestResponse(BaseModel):
    """Response for a queued wakeup request."""

    id: str
    agent_id: str
    priority: int
    context: Optional[Dict[str, Any]]
    reason: Optional[str]
    consumed: bool
    consumed_at: Optional[str]
    created_at: Optional[str]


class RunEventResponse(BaseModel):
    """Response for a single run event."""

    id: str
    event_type: str
    message: Optional[str]
    payload: Optional[Dict[str, Any]]
    occurred_at: str


class HeartbeatRunResponse(BaseModel):
    """Response for a single heartbeat run."""

    id: str
    agent_id: str
    status: str
    trigger: str
    wakeup_context: Optional[Dict[str, Any]]
    started_at: Optional[str]
    finished_at: Optional[str]
    tokens_used: Optional[int]
    cost_usd: Optional[float]
    model: Optional[str]
    provider: Optional[str]
    error_message: Optional[str]
    created_at: Optional[str]
    events: List[RunEventResponse] = []


@router.get("/{agent_id}/config", response_model=HeartbeatConfigResponse)
async def get_config(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Return heartbeat config and runtime state for an agent (#1407)."""
    state = await _get_or_create_state(session, agent_id)
    await session.commit()
    return _state_to_response(state)


@router.put("/{agent_id}/config", response_model=HeartbeatConfigResponse)
async def update_config(
    agent_id: str,
    body: HeartbeatConfigRequest,
    session: AsyncSession = Depends(get_db_session),
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Update heartbeat config for an agent and sync the scheduler (#1407)."""
    state = await _get_or_create_state(session, agent_id)
    was_enabled = state.heartbeat_enabled
    state.heartbeat_enabled = body.heartbeat_enabled
    state.heartbeat_interval_seconds = body.heartbeat_interval_seconds
    state.max_run_duration_seconds = body.max_run_duration_seconds
    await session.commit()
    await session.refresh(state)
    if body.heartbeat_enabled and not was_enabled:
        await scheduler.enable_agent(agent_id, body.heartbeat_interval_seconds)
    elif not body.heartbeat_enabled and was_enabled:
        await scheduler.disable_agent(agent_id)
    elif body.heartbeat_enabled and was_enabled:
        await scheduler.enable_agent(agent_id, body.heartbeat_interval_seconds)
    return _state_to_response(state)


@router.patch("/{agent_id}/session", response_model=HeartbeatConfigResponse)
async def update_session(
    agent_id: str,
    body: Dict[str, Any],
    session: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Persist agent session params (adapter-specific codec) (#1407)."""
    state = await _get_or_create_state(session, agent_id)
    if "session_params" in body:
        state.session_params = body["session_params"]
    if "current_task_id" in body:
        state.current_task_id = body["current_task_id"]
    if "extra" in body:
        state.extra = body["extra"]
    await session.commit()
    await session.refresh(state)
    return _state_to_response(state)


@router.get("/{agent_id}/runs", response_model=List[HeartbeatRunResponse])
async def list_runs(
    agent_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
) -> List[HeartbeatRunResponse]:
    """List recent heartbeat runs for an agent, newest first (#1407)."""
    result = await session.execute(
        select(HeartbeatRun)
        .where(HeartbeatRun.agent_id == agent_id)
        .options(selectinload(HeartbeatRun.events))
        .order_by(HeartbeatRun.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return [_run_to_response(r) for r in result.scalars().all()]


@router.get("/{agent_id}/runs/{run_id}", response_model=HeartbeatRunResponse)
async def get_run(
    agent_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
) -> HeartbeatRunResponse:
    """Get a single heartbeat run with its events (#1407)."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid run_id UUID")
    result = await session.execute(
        select(HeartbeatRun)
        .where(HeartbeatRun.id == run_uuid, HeartbeatRun.agent_id == agent_id)
        .options(selectinload(HeartbeatRun.events))
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return _run_to_response(run)


@router.post("/{agent_id}/wakeup", status_code=status.HTTP_202_ACCEPTED)
async def request_wakeup(
    agent_id: str,
    body: WakeupRequestCreate,
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> Dict[str, str]:
    """Queue an event-driven wakeup request for an agent (#1407)."""
    req_id = await scheduler.wakeup(
        agent_id=agent_id,
        context=body.context,
        priority=body.priority,
        reason=body.reason,
    )
    return {"id": req_id, "agent_id": agent_id, "status": "queued"}


@router.get("/{agent_id}/wakeup", response_model=List[WakeupRequestResponse])
async def list_wakeup_requests(
    agent_id: str,
    include_consumed: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
) -> List[WakeupRequestResponse]:
    """List pending (or all) wakeup requests for an agent (#1407)."""
    q = select(AgentWakeupRequest).where(AgentWakeupRequest.agent_id == agent_id)
    if not include_consumed:
        q = q.where(AgentWakeupRequest.consumed_at.is_(None))
    result = await session.execute(q.order_by(AgentWakeupRequest.priority.desc()))
    return [_wakeup_to_response(r) for r in result.scalars().all()]


@router.post("/{agent_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_manual(
    agent_id: str,
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> Dict[str, str]:
    """Immediately queue a manual heartbeat run for an agent (#1407)."""
    asyncio.create_task(
        scheduler._run_once(agent_id, WakeupTrigger.MANUAL),
        name=f"hb-manual-{agent_id}",
    )
    return {"agent_id": agent_id, "status": "triggered"}


def _state_to_response(state: AgentRuntimeState) -> HeartbeatConfigResponse:
    """Convert AgentRuntimeState ORM row to Pydantic response (#1407)."""
    return HeartbeatConfigResponse(
        agent_id=state.agent_id,
        heartbeat_enabled=state.heartbeat_enabled,
        heartbeat_interval_seconds=state.heartbeat_interval_seconds,
        max_run_duration_seconds=state.max_run_duration_seconds,
        current_task_id=state.current_task_id,
        last_heartbeat_at=(
            state.last_heartbeat_at.isoformat() if state.last_heartbeat_at else None
        ),
        session_params=state.session_params,
        extra=state.extra,
        created_at=(state.created_at.isoformat() if state.created_at else None),
        updated_at=(state.updated_at.isoformat() if state.updated_at else None),
    )


def _run_to_response(run: HeartbeatRun) -> HeartbeatRunResponse:
    """Convert HeartbeatRun ORM row to Pydantic response (#1407)."""
    return HeartbeatRunResponse(
        id=str(run.id),
        agent_id=run.agent_id,
        status=run.status,
        trigger=run.trigger,
        wakeup_context=run.wakeup_context,
        started_at=(run.started_at.isoformat() if run.started_at else None),
        finished_at=(run.finished_at.isoformat() if run.finished_at else None),
        tokens_used=run.tokens_used,
        cost_usd=run.cost_usd,
        model=run.model,
        provider=run.provider,
        error_message=run.error_message,
        created_at=(run.created_at.isoformat() if run.created_at else None),
        events=[_event_to_response(e) for e in (run.events or [])],
    )


def _event_to_response(event: HeartbeatRunEvent) -> RunEventResponse:
    """Convert HeartbeatRunEvent ORM row to Pydantic response (#1407)."""
    return RunEventResponse(
        id=str(event.id),
        event_type=event.event_type,
        message=event.message,
        payload=event.payload,
        occurred_at=event.occurred_at,
    )


def _wakeup_to_response(req: AgentWakeupRequest) -> WakeupRequestResponse:
    """Convert AgentWakeupRequest ORM row to Pydantic response (#1407)."""
    return WakeupRequestResponse(
        id=str(req.id),
        agent_id=req.agent_id,
        priority=req.priority,
        context=req.context,
        reason=req.reason,
        consumed=req.consumed_at is not None,
        consumed_at=(req.consumed_at.isoformat() if req.consumed_at else None),
        created_at=(req.created_at.isoformat() if req.created_at else None),
    )
