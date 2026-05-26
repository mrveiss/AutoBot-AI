# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Heartbeat API (#1407)

Endpoints for heartbeat configuration, run history, wakeup requests,
and agent runtime state inspection.
"""

import asyncio
import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.schemas_system import (
    AgentPauseRequest,
    AgentResumeRequest,
    AgentTerminateRequest,
    HeartbeatConfigRequest,
    HeartbeatConfigResponse,
    HeartbeatRunResponse,
    HeartbeatTriggerResponse,
    HeartbeatWakeupQueuedResponse,
    RunEventResponse,
    WakeupRequestCreate,
    WakeupRequestResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from models.heartbeat import (
    AgentRuntimeState,
    AgentStatus,
    AgentWakeupRequest,
    HeartbeatRun,
    HeartbeatRunEvent,
    WakeupTrigger,
)
from services.heartbeat_scheduler import HeartbeatScheduler, _get_or_create_state

logger = get_logger(__name__)
router = APIRouter()

_scheduler: HeartbeatScheduler | None = None


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


@router.get("/{agent_id}/config", response_model=HeartbeatConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_config",
    error_code_prefix="HEARTBEAT",
)
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_config",
    error_code_prefix="HEARTBEAT",
)
async def update_config(
    agent_id: str,
    body: HeartbeatConfigRequest,
    session: AsyncSession = Depends(get_db_session),
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Update heartbeat config for an agent and sync the scheduler (#1407, GH#6476)."""
    state = await _get_or_create_state(session, agent_id)
    if state.status == AgentStatus.TERMINATED.value:
        raise HTTPException(status_code=409, detail="Agent is terminated and cannot be reconfigured")
    was_enabled = state.heartbeat_enabled
    state.heartbeat_enabled = body.heartbeat_enabled  # drives status via hybrid setter
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="update_session",
    error_code_prefix="HEARTBEAT",
)
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_runs",
    error_code_prefix="HEARTBEAT",
)
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="get_run",
    error_code_prefix="HEARTBEAT",
)
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


@router.post("/{agent_id}/wakeup", status_code=status.HTTP_202_ACCEPTED, response_model=HeartbeatWakeupQueuedResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="request_wakeup",
    error_code_prefix="HEARTBEAT",
)
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
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="list_wakeup_requests",
    error_code_prefix="HEARTBEAT",
)
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


@router.post("/{agent_id}/trigger", status_code=status.HTTP_202_ACCEPTED, response_model=HeartbeatTriggerResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="trigger_manual",
    error_code_prefix="HEARTBEAT",
)
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


@router.post("/{agent_id}/pause", response_model=HeartbeatConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="pause_agent",
    error_code_prefix="HEARTBEAT",
)
async def pause_agent(
    agent_id: str,
    body: AgentPauseRequest,
    session: AsyncSession = Depends(get_db_session),
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Pause an agent's heartbeat (GH#6476).

    Transitions status to PAUSED, cancels the scheduler loop, and records
    who paused it and why.  Does not affect TERMINATED agents.
    """
    state = await _get_or_create_state(session, agent_id)
    if state.status == AgentStatus.TERMINATED.value:
        raise HTTPException(status_code=409, detail="Agent is terminated; cannot pause")
    if state.status == AgentStatus.PAUSED.value:
        return _state_to_response(state)
    state.status = AgentStatus.PAUSED.value
    state.paused_reason = body.reason
    state.paused_at = now_utc()
    state.paused_by = body.paused_by or "user"
    await session.commit()
    await session.refresh(state)
    await scheduler.disable_agent(agent_id)
    logger.info("Agent %s paused by %s: %s", agent_id, state.paused_by, state.paused_reason)
    return _state_to_response(state)


@router.post("/{agent_id}/resume", response_model=HeartbeatConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="resume_agent",
    error_code_prefix="HEARTBEAT",
)
async def resume_agent(
    agent_id: str,
    body: AgentResumeRequest,
    session: AsyncSession = Depends(get_db_session),
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Resume a paused agent's heartbeat (GH#6476).

    Transitions PAUSED → ACTIVE.  System-paused agents (paused_by starts with
    "system:") require admin role; user-paused agents can be resumed freely.
    DISABLED and TERMINATED agents are not affected — use PUT /config instead.
    """
    state = await _get_or_create_state(session, agent_id)
    if state.status == AgentStatus.TERMINATED.value:
        raise HTTPException(status_code=409, detail="Agent is terminated; cannot resume")
    if state.status != AgentStatus.PAUSED.value:
        raise HTTPException(status_code=409, detail=f"Agent is not paused (status={state.status})")
    # System-enforced pauses require admin approval (GH#6476)
    paused_by = state.paused_by or ""
    if paused_by.startswith("system:"):
        user_roles = getattr(_user, "roles", []) or []
        if "admin" not in user_roles:
            raise HTTPException(
                status_code=403,
                detail=f"Agent was paused by {paused_by}; admin approval required to resume",
            )
    state.status = AgentStatus.ACTIVE.value
    state.paused_reason = None
    state.paused_at = None
    state.paused_by = None
    await session.commit()
    await session.refresh(state)
    await scheduler.enable_agent(agent_id, state.heartbeat_interval_seconds)
    logger.info("Agent %s resumed", agent_id)
    return _state_to_response(state)


@router.post("/{agent_id}/terminate", response_model=HeartbeatConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="terminate_agent",
    error_code_prefix="HEARTBEAT",
)
async def terminate_agent(
    agent_id: str,
    body: AgentTerminateRequest,
    session: AsyncSession = Depends(get_db_session),
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Permanently terminate an agent's heartbeat (GH#6476).

    Transitions status to TERMINATED, stops the scheduler loop, and records the
    reason.  Terminated agents cannot be re-enabled via any endpoint.
    """
    state = await _get_or_create_state(session, agent_id)
    if state.status == AgentStatus.TERMINATED.value:
        return _state_to_response(state)
    state.status = AgentStatus.TERMINATED.value
    state.paused_reason = body.reason
    state.paused_at = now_utc()
    state.paused_by = getattr(_user, "id", "user")
    await session.commit()
    await session.refresh(state)
    await scheduler.disable_agent(agent_id)
    logger.info("Agent %s terminated: %s", agent_id, body.reason)
    return _state_to_response(state)


def _state_to_response(state: AgentRuntimeState) -> HeartbeatConfigResponse:
    """Convert AgentRuntimeState ORM row to Pydantic response (#1407, GH#6476)."""
    return HeartbeatConfigResponse(
        agent_id=state.agent_id,
        heartbeat_enabled=state.heartbeat_enabled,
        status=state.status,
        paused_reason=state.paused_reason,
        paused_at=(state.paused_at.isoformat() if state.paused_at else None),
        paused_by=state.paused_by,
        heartbeat_interval_seconds=state.heartbeat_interval_seconds,
        max_run_duration_seconds=state.max_run_duration_seconds,
        current_task_id=state.current_task_id,
        last_heartbeat_at=(state.last_heartbeat_at.isoformat() if state.last_heartbeat_at else None),
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
        merged_count=req.merged_count if req.merged_count is not None else 0,
    )
