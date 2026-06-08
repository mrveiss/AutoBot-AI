# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC heartbeat run management API (GH#8228).

Routes:
  GET    /api/llc/agents/{agent_id}/runs         — list runs (paginated, filterable)
  GET    /api/llc/agents/{agent_id}/runs/{run_id} — run detail
  POST   /api/llc/agents/{agent_id}/runs/{run_id}/cancel — manual cancel (board only)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.redis_client import get_async_redis_client
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..adapters import get_adapter_for_agent
from ..models.heartbeat_run import LLCHeartbeatRun

router = APIRouter(prefix="/agents", tags=["llc-runs"])


def _run_to_dict(run: LLCHeartbeatRun) -> Dict[str, Any]:
    return {
        "id": str(run.id),
        "company_id": str(run.company_id),
        "agent_id": run.agent_id,
        "invocation_source": run.invocation_source,
        "status": run.status,
        "work_item_id": str(run.work_item_id) if run.work_item_id else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": run.error,
        "external_run_id": run.external_run_id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


@router.get("/{agent_id}/runs", response_model=List[Dict[str, Any]])
async def list_runs(
    agent_id: str,
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """List heartbeat runs for an agent, newest first."""
    q = select(LLCHeartbeatRun).where(
        LLCHeartbeatRun.agent_id == agent_id,
        LLCHeartbeatRun.company_id == ctx.org_id,
    )
    if status:
        q = q.where(LLCHeartbeatRun.status == status)
    q = q.order_by(LLCHeartbeatRun.created_at.desc()).limit(limit).offset(offset)
    result = await session.execute(q)
    return [_run_to_dict(r) for r in result.scalars().all()]


@router.get("/{agent_id}/runs/{run_id}")
async def get_run(
    agent_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Get a single heartbeat run with context snapshot."""
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")
    result = await session.execute(
        select(LLCHeartbeatRun).where(
            LLCHeartbeatRun.agent_id == agent_id,
            LLCHeartbeatRun.id == run_uuid,
            LLCHeartbeatRun.company_id == ctx.org_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    data = _run_to_dict(run)
    data["context_snapshot"] = run.context_snapshot
    return data


@router.post("/{agent_id}/runs/{run_id}/cancel", status_code=200)
async def cancel_run(
    agent_id: str,
    run_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """Manual run cancel (board only).

    Sets run status = cancelled, calls adapter.cancel() best-effort,
    and releases the Redis checkout lock when a work item was held.
    """
    try:
        run_uuid = uuid.UUID(run_id)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid run_id UUID format")
    result = await session.execute(
        select(LLCHeartbeatRun).where(
            LLCHeartbeatRun.agent_id == agent_id,
            LLCHeartbeatRun.id == run_uuid,
            LLCHeartbeatRun.company_id == ctx.org_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    if run.status not in ("queued", "running"):
        raise HTTPException(
            status_code=409,
            detail=f"Cannot cancel run with status '{run.status}'",
        )

    # Update run status
    run.status = "cancelled"
    run.finished_at = datetime.now(tz=timezone.utc)
    session.add(run)

    # Best-effort adapter cancel
    try:
        adapter = await get_adapter_for_agent(agent_id)
        if adapter is not None:
            await adapter.cancel({}, run_id)
    except Exception:
        pass

    # Release checkout lock
    if run.work_item_id:
        redis = await get_async_redis_client()
        if redis is not None:
            try:
                await redis.delete(f"llc:checkout:{run.work_item_id}")
            except Exception:
                pass

    await session.commit()
    return _run_to_dict(run)


@router.get("/{agent_id}/diary", response_model=List[Dict[str, Any]])
async def get_agent_diary(
    agent_id: str,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    date_from: Optional[str] = Query(None, description="ISO date filter start (YYYY-MM-DD)"),
    date_to: Optional[str] = Query(None, description="ISO date filter end (YYYY-MM-DD)"),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[Dict[str, Any]]:
    """Return diary entries for an agent, newest first.

    Reads from the KB via ``AgentDiaryService``.  Supports ``limit``/``offset``
    pagination and optional ``date_from``/``date_to`` filters (inclusive).
    """
    try:
        from memory.agent_diary import AgentDiaryService

        diary = AgentDiaryService()
        entries = await diary.read(agent_name=agent_id, last_n=limit + offset)
    except Exception:
        import logging

        logging.getLogger(__name__).warning("get_agent_diary: KB read failed for agent_id=%s", agent_id, exc_info=True)
        return []

    if date_from or date_to:

        def _in_range(entry: Dict[str, Any]) -> bool:
            ts = (entry.get("metadata") or {}).get("diary_timestamp", "")
            if not ts:
                return True
            date_str = ts[:10]
            if date_from and date_str < date_from:
                return False
            if date_to and date_str > date_to:
                return False
            return True

        entries = [e for e in entries if _in_range(e)]

    return entries[offset : offset + limit]
