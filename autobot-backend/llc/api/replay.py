# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC agent run replay API (GH#9034).

Routes (all under /llc):
  POST GET /agents/{agent_id}/runs/{run_id}/replay
    — trigger a new run with stored inputs; returns the new run record.
  GET  /agents/{agent_id}/runs/{run_id}/replay-log
    — return the recorded timeline (step-browser) with optional ?redact_pii=true.
  GET  /agents/{agent_id}/runs/{run_id}/diff/{other_run_id}
    — unified text diff of output_text between two runs.
  GET  /agents/{agent_id}/runs/{run_id}/fixture
    — export run as a JSON test fixture.

Authorization: board_member (OWNER/ADMIN) for all replay endpoints — same
guard as controls.py (_require_board_role).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..models.enums import MembershipRole
from ..scheduler.heartbeat_scheduler import get_heartbeat_scheduler
from ..services.membership_service import MembershipService
from ..services.replay_service import ReplayLogNotFoundError, RunReplayService
from autobot_shared.singleton_factory import lazy_singleton

router = APIRouter(prefix="/agents", tags=["llc-replay"])

_ALLOWED_ROLES = {MembershipRole.OWNER, MembershipRole.ADMIN}

_get_membership = lazy_singleton(MembershipService)
_get_replay_svc = lazy_singleton(RunReplayService)


async def _require_admin(
    ctx: TenantContext,
    current_user: dict,
    session: AsyncSession,
) -> None:
    """Raise 403 unless the caller is OWNER or ADMIN of the company."""
    user_id = current_user.get("id") or current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    svc = _get_membership()
    try:
        members = await svc.list_members(session, str(ctx.org_id))
        role = next(
            (m.role for m in members if str(m.user_id) == str(user_id)),
            None,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Membership lookup failed: {exc}") from exc

    if role not in _ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail="Replay endpoints require board admin (owner/admin) role",
        )


@router.post("/{agent_id}/runs/{run_id}/replay", status_code=202)
async def trigger_replay(
    agent_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Replay a run — re-executes stored inputs, creating a new run record.

    Returns the new (QUEUED) run.  Dispatch is asynchronous; poll
    ``GET /agents/{agent_id}/runs/{new_run_id}`` for completion status.
    """
    await _require_admin(ctx, current_user, session)

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    svc = _get_replay_svc()
    try:
        new_run = await svc.replay_run(session, run_uuid, ctx.org_id)
    except ReplayLogNotFoundError:
        raise HTTPException(status_code=404, detail="No replay log found for this run")

    # Fetch agent config for dispatch.
    from sqlalchemy import text as _text
    from user_management.database import get_async_session_factory

    await session.commit()

    factory = get_async_session_factory()
    async with factory() as lookup_session:
        result = await lookup_session.execute(
            _text("""
                SELECT aon.agent_id, aon.name, aon.heartbeat_cron,
                       aon.adapter_type, aon.adapter_config, aon.context_mode,
                       aon.company_id
                FROM agent_org_nodes aon
                WHERE aon.agent_id = :agent_id
            """),
            {"agent_id": agent_id},
        )
        row = result.mappings().first()

    if row:
        agent_cfg = dict(row)
        # Load replay context from the log.
        from sqlalchemy import select
        from ..models.replay_log import LLCRunReplayLog

        async with factory() as log_session:
            log_result = await log_session.execute(
                select(LLCRunReplayLog).where(
                    LLCRunReplayLog.run_id == run_uuid,
                    LLCRunReplayLog.company_id == ctx.org_id,
                )
            )
            log = log_result.scalar_one_or_none()
        replay_context = dict(log.inputs_snapshot) if log and log.inputs_snapshot else {}
        get_heartbeat_scheduler().dispatch_run(agent_cfg, new_run.id, replay_context)

    return {
        "new_run_id": str(new_run.id),
        "replay_of_run_id": run_id,
        "status": new_run.status,
        "agent_id": new_run.agent_id,
    }


@router.get("/{agent_id}/runs/{run_id}/replay-log")
async def get_replay_log(
    agent_id: str,
    run_id: str,
    redact_pii: bool = Query(False, description="Redact PII/credentials from returned payload"),
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Return the recorded timeline for a run (for step-browser).

    Use ``?redact_pii=true`` to strip credentials/emails from the payload.
    """
    await _require_admin(ctx, current_user, session)

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    svc = _get_replay_svc()
    log = await svc.get_replay_log(session, run_uuid, ctx.org_id, redact_pii=redact_pii)
    if log is None:
        raise HTTPException(status_code=404, detail="No replay log found for this run")
    return log


@router.get("/{agent_id}/runs/{run_id}/diff/{other_run_id}")
async def diff_runs(
    agent_id: str,
    run_id: str,
    other_run_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Unified text diff of output_text between two runs."""
    await _require_admin(ctx, current_user, session)

    try:
        uuid_a = uuid.UUID(run_id)
        uuid_b = uuid.UUID(other_run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    svc = _get_replay_svc()
    return await svc.get_run_diff(session, uuid_a, uuid_b, ctx.org_id)


@router.get("/{agent_id}/runs/{run_id}/fixture")
async def export_fixture(
    agent_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Export run as a JSON test fixture (inputs + expected output shape).

    Always applies PII redaction.
    """
    await _require_admin(ctx, current_user, session)

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    svc = _get_replay_svc()
    try:
        return await svc.export_fixture(session, run_uuid, ctx.org_id)
    except ReplayLogNotFoundError:
        raise HTTPException(status_code=404, detail="No replay log found for this run")
