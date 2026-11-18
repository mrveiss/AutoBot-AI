# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ORM-row to response-model converters for the heartbeat API (#1407, GH#6476)."""

from api.schemas_heartbeat import HeartbeatConfigResponse
from api.schemas_system import (
    HeartbeatRunResponse,
    RunEventResponse,
    WakeupRequestResponse,
)
from models.heartbeat import (
    AgentRuntimeState,
    AgentWakeupRequest,
    HeartbeatRun,
    HeartbeatRunEvent,
)


def _state_to_response(state: AgentRuntimeState, paused_by_name: str | None = None) -> HeartbeatConfigResponse:
    """Convert AgentRuntimeState ORM row to Pydantic response (#1407, GH#6476, MVA-1411)."""
    return HeartbeatConfigResponse(
        agent_id=state.agent_id,
        heartbeat_enabled=state.heartbeat_enabled,
        status=state.status,
        paused_reason=state.paused_reason,
        paused_at=(state.paused_at.isoformat() if state.paused_at else None),
        paused_by=state.paused_by,
        paused_by_name=paused_by_name,
        error_detail=state.error_detail,
        error_at=(state.error_at.isoformat() if state.error_at else None),
        error_code=state.error_code,
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
