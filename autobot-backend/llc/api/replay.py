# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC agent run replay API (GH#9034).

Routes (all under /llc):
  POST /agents/{agent_id}/runs/{run_id}/replay
    — trigger a new run with stored inputs; returns the new run record.
  GET  /agents/{agent_id}/runs/{run_id}/replay-log
    — return the recorded timeline (step-browser); ?redact_pii=true strips
      credentials from the response on read (raw inputs are always stored).
  GET  /agents/{agent_id}/runs/{run_id}/diff/{other_run_id}
    — unified text diff of output_text between two runs.
  GET  /agents/{agent_id}/runs/{run_id}/fixture
    — export run as a JSON test fixture (always redacted).

Authorization: board_member (OWNER/ADMIN) for all replay endpoints — same
guard as controls.py (now via shared ``require_board_role`` in llc/deps.py).
"""

from __future__ import annotations

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..deps import require_board_role
from ..models.enums import LLCRunStatus, MembershipRole
from ..models.heartbeat_run import LLCHeartbeatRun
from ..scheduler.heartbeat_scheduler import get_heartbeat_scheduler
from ..services.budget import BudgetService
from ..services.membership_service import MembershipService
from ..services.replay_service import ReplayLogNotFoundError, RunReplayService
from autobot_shared.singleton_factory import lazy_singleton

router = APIRouter(prefix="/agents", tags=["llc-replay"])

_ALLOWED_ROLES = {MembershipRole.OWNER, MembershipRole.ADMIN}

_get_membership = lazy_singleton(MembershipService)
_get_replay_svc = lazy_singleton(RunReplayService)
_get_budget_svc = lazy_singleton(BudgetService)


# ---------------------------------------------------------------------------
# Shared auth helper (M7: delegates to canonical require_board_role in deps.py)
# ---------------------------------------------------------------------------


async def _check_admin(ctx: TenantContext, current_user: dict, session: AsyncSession) -> None:
    """Gate: caller must be OWNER or ADMIN of the tenant company."""
    await require_board_role(
        company_id=ctx.org_id,
        current_user=current_user,
        session=session,
        allowed_roles=_ALLOWED_ROLES,
        membership_svc=_get_membership(),
    )


# ---------------------------------------------------------------------------
# Validation helpers (H2, H3, M3 — all called BEFORE creating a run row)
# ---------------------------------------------------------------------------


async def _validate_agent_tenant(
    session: AsyncSession,
    agent_id: str,
    org_id: uuid.UUID,
) -> Dict[str, Any]:
    """Load agent config and verify it belongs to the caller's tenant (H2a).

    Returns the agent row dict.  Raises 404 if missing, 403 if wrong tenant.
    """
    from sqlalchemy import text as _text

    result = await session.execute(
        _text("""
            SELECT aon.agent_id, aon.name, aon.heartbeat_cron,
                   aon.adapter_type, aon.adapter_config, aon.context_mode,
                   aon.company_id, aon.status, aon.heartbeat_enabled
            FROM agent_org_nodes aon
            WHERE aon.agent_id = :agent_id
        """),
        {"agent_id": agent_id},
    )
    row = result.mappings().first()
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    agent_company_id = row["company_id"]
    if str(agent_company_id) != str(org_id):
        raise HTTPException(status_code=403, detail="Agent does not belong to this organization")

    return dict(row)


def _validate_agent_status(agent_cfg: Dict[str, Any]) -> None:
    """Reject replay when the agent is inactive or terminated (H2c)."""
    status = str(agent_cfg.get("status") or "")
    if status in ("inactive", "terminated"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot replay: agent status is '{status}'",
        )


async def _validate_budget(session: AsyncSession, agent_id: str) -> None:
    """Reject replay when the agent is over its budget limit (H2d)."""
    svc = _get_budget_svc()
    _remaining, is_over, _alert = await svc.check_budget(session, agent_id)
    if is_over:
        raise HTTPException(
            status_code=402,
            detail="Cannot replay: agent has exceeded its budget limit",
        )


async def _validate_no_active_run(session: AsyncSession, agent_id: str) -> None:
    """Reject replay when a RUNNING or QUEUED run already exists (H3a)."""
    result = await session.execute(
        select(LLCHeartbeatRun).where(
            LLCHeartbeatRun.agent_id == agent_id,
            LLCHeartbeatRun.status.in_([LLCRunStatus.RUNNING.value, LLCRunStatus.QUEUED.value]),
        ).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot replay: agent already has an active run ({existing.id}, status={existing.status})",
        )


def _validate_log_agent_match(log_agent_id: str, path_agent_id: str) -> None:
    """Reject replay when the replay-log's agent_id differs from the URL path (H2b)."""
    if log_agent_id != path_agent_id:
        raise HTTPException(
            status_code=400,
            detail="Replay log agent_id does not match the requested agent_id",
        )


# ---------------------------------------------------------------------------
# Dispatch helper
# ---------------------------------------------------------------------------


async def _dispatch_replay_run(
    new_run_id: uuid.UUID,
    agent_cfg: Dict[str, Any],
    replay_context: Dict[str, Any],
) -> None:
    """Fire the replay run via the heartbeat scheduler (H3b: replay=True flag)."""
    # H3b: set replay flag so adapters skip session resume.
    context = dict(replay_context, replay=True)
    get_heartbeat_scheduler().dispatch_run(agent_cfg, new_run_id, context)


# ---------------------------------------------------------------------------
# Endpoint: trigger_replay (H2, H3, M3, L5 — validations first, then create)
# ---------------------------------------------------------------------------


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
    await _check_admin(ctx, current_user, session)

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    # M3: ALL validations happen BEFORE creating the run row.
    # H2a + H2c: tenant scope + status gate.
    agent_cfg = await _validate_agent_tenant(session, agent_id, ctx.org_id)
    _validate_agent_status(agent_cfg)

    # H3a: refuse while a RUNNING/QUEUED run exists.
    await _validate_no_active_run(session, agent_id)

    # H2d: budget gate.
    await _validate_budget(session, agent_id)

    # Load the replay log (validates company scope + existence).
    svc = _get_replay_svc()
    log = await _load_replay_log(session, run_uuid, ctx.org_id)

    # H2b: path agent_id must match the stored log.
    _validate_log_agent_match(log.agent_id, agent_id)

    # All gates passed — create the run row and dispatch.
    new_run = await svc.replay_run(session, run_uuid, ctx.org_id)
    await session.commit()

    replay_context = dict(log.inputs_snapshot or {})
    await _dispatch_replay_run(new_run.id, agent_cfg, replay_context)

    return {
        "new_run_id": str(new_run.id),
        "replay_of_run_id": run_id,
        "status": new_run.status,
        "agent_id": new_run.agent_id,
    }


async def _load_replay_log(session: AsyncSession, run_id: uuid.UUID, company_id: uuid.UUID):  # type: ignore[return]
    """Load LLCRunReplayLog or raise 404."""
    from ..models.replay_log import LLCRunReplayLog

    result = await session.execute(
        select(LLCRunReplayLog).where(
            LLCRunReplayLog.run_id == run_id,
            LLCRunReplayLog.company_id == company_id,
        )
    )
    log = result.scalar_one_or_none()
    if log is None:
        raise HTTPException(status_code=404, detail="No replay log found for this run")
    return log


# ---------------------------------------------------------------------------
# Endpoint: get_replay_log
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/runs/{run_id}/replay-log")
async def get_replay_log(
    agent_id: str,
    run_id: str,
    redact_pii: bool = Query(False, description="Redact credentials/PII from the returned payload"),
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Return the recorded timeline for a run (for step-browser).

    Raw inputs are stored in the DB; use ``?redact_pii=true`` to have
    credentials stripped from the response on read.  Emails are NOT
    separately redacted (the credential_redaction module covers API keys
    and bearer tokens; email redaction would require regex patterns not
    currently present in that module).
    """
    await _check_admin(ctx, current_user, session)

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    svc = _get_replay_svc()
    log = await svc.get_replay_log(session, run_uuid, ctx.org_id, redact_pii=redact_pii)
    if log is None:
        raise HTTPException(status_code=404, detail="No replay log found for this run")
    return log


# ---------------------------------------------------------------------------
# Endpoint: diff_runs
# ---------------------------------------------------------------------------


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
    await _check_admin(ctx, current_user, session)

    try:
        uuid_a = uuid.UUID(run_id)
        uuid_b = uuid.UUID(other_run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    svc = _get_replay_svc()
    return await svc.get_run_diff(session, uuid_a, uuid_b, ctx.org_id)


# ---------------------------------------------------------------------------
# Endpoint: export_fixture (M1: auth handled server-side; client uses api client)
# ---------------------------------------------------------------------------


@router.get("/{agent_id}/runs/{run_id}/fixture")
async def export_fixture(
    agent_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Export run as a JSON test fixture (inputs + expected output shape).

    Always applies PII redaction to the exported payload.
    In-process runs record inputs only (no output file exists for autobot_agent
    adapter runs); the ``recorded_events`` and ``output_text`` fields will be
    null for those runs.
    """
    await _check_admin(ctx, current_user, session)

    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")

    svc = _get_replay_svc()
    try:
        return await svc.export_fixture(session, run_uuid, ctx.org_id)
    except ReplayLogNotFoundError:
        raise HTTPException(status_code=404, detail="No replay log found for this run")
