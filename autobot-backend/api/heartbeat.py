# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Heartbeat API (#1407)

Endpoints for heartbeat configuration, run history, wakeup requests,
and agent runtime state inspection.
"""

import uuid
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from api.heartbeat_responses import (
    _run_to_response,
    _state_to_response,
    _wakeup_to_response,
)
from api.schemas_heartbeat import (
    AgentErrorRequest,
    AgentPauseRequest,
    AgentRecoverRequest,
    AgentResumeRequest,
    AgentTerminateRequest,
    HeartbeatConfigRequest,
    HeartbeatConfigResponse,
)
from api.schemas_system import (
    HeartbeatRunResponse,
    HeartbeatTriggerResponse,
    HeartbeatWakeupQueuedResponse,
    WakeupRequestCreate,
    WakeupRequestResponse,
)
from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from autobot_shared.async_compat import fire_and_forget
from autobot_shared.auth.permissions import is_admin_role
from autobot_shared.error_boundaries import ErrorCategory, with_error_handling
from autobot_shared.logging_manager import get_logger
from autobot_shared.principal import resolve_principal_id
from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.models.user import resolve_display_name
from models.heartbeat import (
    AgentRuntimeState,
    AgentWakeupRequest,
    HeartbeatRun,
    HeartbeatStatus,
    WakeupTrigger,
)
from services.audit.audit import record_committed
from services.audit.taxonomy import AuditAction, AuditCategory, AuditEvent, action_name
from services.heartbeat_scheduler import HeartbeatScheduler, _get_or_create_state
from user_management.models.user import User

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
    operation="get_heartbeat_config",
    error_code_prefix="HEARTBEAT",
)
async def get_heartbeat_config(
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Return heartbeat config and runtime state for an agent (#1407)."""
    state = await _get_or_create_state(session, agent_id)
    await session.commit()
    return await _state_response(session, state)


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
    if state.status == HeartbeatStatus.TERMINATED.value:
        raise HTTPException(status_code=409, detail="Agent is terminated and cannot be reconfigured")
    # P0-2: block re-enable via config while PAUSED — use POST /{agent_id}/resume (GH#6476)
    if state.status == HeartbeatStatus.PAUSED.value:
        raise HTTPException(status_code=409, detail="Agent is paused; use POST /{agent_id}/resume to re-enable")
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
    return await _state_response(session, state)


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
    return await _state_response(session, state)


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
    fire_and_forget(
        scheduler._run_once(agent_id, WakeupTrigger.MANUAL),
        name=f"hb-manual-{agent_id}",
    )
    return {"agent_id": agent_id, "status": "triggered"}


def _actor_id(user: Any) -> str:
    """The verified caller's principal id, from the auth dependency only (#21136)."""
    claims = user if isinstance(user, dict) else vars(user)
    return resolve_principal_id(claims) or str(claims.get("username") or "unknown")


async def _audit_control(actor: str, action: AuditAction, agent_id: str, reason: str | None = None) -> bool:
    """Durably record who paused, resumed or terminated an agent; call only AFTER the commit (#21136).

    Resume clears the row, so this event is the only record of the resumer: it is the awaited,
    bounded ``record_committed`` write, not the fire-and-forget bus. The state change is already
    committed, so a failed write is logged and counted by the audit module and returned, not raised.
    """
    return await record_committed(
        AuditEvent(
            category=AuditCategory.SECURITY,
            action=action_name(action),
            actor_id=actor,
            resource_type="agent_heartbeat",
            resource_id=agent_id,
            metadata={"reason": reason} if reason else None,
        )
    )


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
    if state.status == HeartbeatStatus.TERMINATED.value:
        raise HTTPException(status_code=409, detail="Agent is terminated; cannot pause")
    if state.status == HeartbeatStatus.PAUSED.value:
        return await _state_response(session, state)
    state.status = HeartbeatStatus.PAUSED.value
    state.paused_reason = body.reason
    state.paused_at = now_utc()
    # The verified caller is the only actor; body.paused_by is never trusted (#21136).
    state.paused_by = _actor_id(_user)
    await session.commit()
    await _audit_control(state.paused_by, AuditAction.AGENT_PAUSE, agent_id, body.reason)
    await session.refresh(state)
    await scheduler.disable_agent(agent_id)
    logger.info("Agent %s paused by %s: %s", agent_id, state.paused_by, state.paused_reason)
    return await _state_response(session, state)


async def _request_skill_approval_for_resume(agent_id: str, paused_by: str, requested_by: str) -> str:
    """Queue a SkillApproval for a non-admin resume of a system-paused agent (GH#8734).

    Delegates to GovernanceEngine so the request appears in the SLM Approvals
    dashboard and is persisted to the skills DB for audit.  Returns the
    approval_id that the caller should surface in the 202 response.
    """
    from skills.governance import GovernanceEngine

    engine = GovernanceEngine()
    result = await engine.request_activation(
        skill_name="agent.resume",
        skill_id=f"agent:resume:{agent_id}",
        requested_by=requested_by,
        reason=f"resume agent {agent_id} (auto-paused by {paused_by})",
    )
    return result.approval_id or ""


def _require_resumable(state: AgentRuntimeState) -> None:
    """Raise 409 unless the agent is PAUSED."""
    if state.status == HeartbeatStatus.TERMINATED.value:
        raise HTTPException(status_code=409, detail="Agent is terminated; cannot resume")
    if state.status != HeartbeatStatus.PAUSED.value:
        raise HTTPException(status_code=409, detail=f"Agent is not paused (status={state.status})")


async def _queue_system_pause_resume(agent_id: str, paused_by: str, user: Any) -> Any:
    """A 202 response when a non-admin resumes a system-paused agent (GH#8734), else None.

    ``user`` is a dict with ``role`` and ``username`` keys, or an object with those attributes.
    """
    from fastapi.responses import JSONResponse

    if not paused_by.startswith("system:"):
        return None
    claims = user if isinstance(user, dict) else vars(user)
    if is_admin_role(claims.get("role", "")):
        return None
    approval_id = await _request_skill_approval_for_resume(agent_id, paused_by, claims.get("username", ""))
    return JSONResponse(
        status_code=202,
        content={
            "approval_id": approval_id,
            "status": "pending",
            "message": f"Agent was paused by {paused_by}; resume request queued for admin approval",
        },
    )


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
    """Resume a paused agent's heartbeat (GH#6476, GH#8734).

    Transitions PAUSED → ACTIVE.  System-paused agents (paused_by starts with
    "system:") go through the SkillApproval governance workflow (GH#8734 AC-6):
    admins resume immediately; non-admins receive HTTP 202 with an approval_id
    that an admin must approve via the SLM dashboard before the agent resumes.
    User-paused agents can be resumed by any authenticated user.
    DISABLED and TERMINATED agents are not affected — use PUT /config instead.
    """
    state = await _get_or_create_state(session, agent_id)
    _require_resumable(state)
    queued = await _queue_system_pause_resume(agent_id, state.paused_by or "", _user)
    if queued is not None:
        return queued
    state.status = HeartbeatStatus.ACTIVE.value
    state.paused_reason = None
    state.paused_at = None
    state.paused_by = None
    await session.commit()
    # No resumer column on the row (would need a migration); this event names the caller.
    resumer = _actor_id(_user)
    await _audit_control(resumer, AuditAction.AGENT_RESUME, agent_id)
    await session.refresh(state)
    await scheduler.enable_agent(agent_id, state.heartbeat_interval_seconds)
    logger.info("Agent %s resumed by %s", agent_id, resumer)
    return await _state_response(session, state)


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
    if state.status == HeartbeatStatus.TERMINATED.value:
        return await _state_response(session, state)
    state.status = HeartbeatStatus.TERMINATED.value
    state.paused_reason = body.reason
    state.paused_at = now_utc()
    state.paused_by = _actor_id(_user)
    await session.commit()
    await _audit_control(state.paused_by, AuditAction.AGENT_TERMINATE, agent_id, body.reason)
    await session.refresh(state)
    await scheduler.disable_agent(agent_id)
    logger.info("Agent %s terminated: %s", agent_id, body.reason)
    return await _state_response(session, state)


@router.post("/{agent_id}/error", response_model=HeartbeatConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="set_agent_error",
    error_code_prefix="HEARTBEAT",
)
async def set_agent_error(
    agent_id: str,
    body: AgentErrorRequest,
    session: AsyncSession = Depends(get_db_session),
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Transition an agent to ERROR status (MVA-1411).

    Suspends heartbeat execution and records error metadata.  The agent stays
    in ERROR until recovered via POST /{agent_id}/recover.  TERMINATED agents
    are not affected.
    """
    state = await _get_or_create_state(session, agent_id)
    if state.status == HeartbeatStatus.TERMINATED.value:
        raise HTTPException(status_code=409, detail="Agent is terminated; cannot set error state")
    if state.status == HeartbeatStatus.ERROR.value:
        return await _state_response(session, state)
    state.status = HeartbeatStatus.ERROR.value
    state.error_detail = body.error_detail
    state.error_at = now_utc()
    state.error_code = body.error_code
    await session.commit()
    await session.refresh(state)
    await scheduler.disable_agent(agent_id)
    logger.info("Agent %s entered error state: code=%s detail=%s", agent_id, state.error_code, state.error_detail)
    return await _state_response(session, state)


@router.post("/{agent_id}/recover", response_model=HeartbeatConfigResponse)
@with_error_handling(
    category=ErrorCategory.SERVER_ERROR,
    operation="recover_agent",
    error_code_prefix="HEARTBEAT",
)
async def recover_agent(
    agent_id: str,
    body: AgentRecoverRequest,
    session: AsyncSession = Depends(get_db_session),
    scheduler: HeartbeatScheduler = Depends(_get_scheduler),
    _user=Depends(get_current_user),
) -> HeartbeatConfigResponse:
    """Recover an agent from ERROR status back to ACTIVE (MVA-1411).

    Clears error metadata and re-enables the heartbeat loop.  Only valid for
    ERROR-state agents; raises 409 for any other status.
    """
    state = await _get_or_create_state(session, agent_id)
    if state.status != HeartbeatStatus.ERROR.value:
        raise HTTPException(status_code=409, detail=f"Agent is not in error state (status={state.status})")
    state.status = HeartbeatStatus.ACTIVE.value
    state.error_detail = None
    state.error_at = None
    state.error_code = None
    await session.commit()
    await session.refresh(state)
    await scheduler.enable_agent(agent_id, state.heartbeat_interval_seconds)
    logger.info("Agent %s recovered from error state", agent_id)
    return await _state_response(session, state)


async def _paused_by_name(session: AsyncSession, paused_by: str | None) -> str | None:
    """The display name of the user whose principal id is ``paused_by``, or None (#21136).

    None for no actor, a ``system:*`` actor, a legacy free-text actor, or an unknown user; the
    client then shows the system label or the raw value.
    """
    try:
        user_id = uuid.UUID(paused_by or "")
    except ValueError:
        return None
    row = (await session.execute(select(User.display_name, User.username).where(User.id == user_id))).one_or_none()
    return resolve_display_name(row.display_name, row.username) if row else None


async def _state_response(session: AsyncSession, state: AgentRuntimeState) -> HeartbeatConfigResponse:
    """The response for ``state`` with the actor's display name resolved from the user record (#21136)."""
    return _state_to_response(state, await _paused_by_name(session, state.paused_by))
