# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC Routines API routes (GH#8229).

Routes:
  GET    /api/llc/companies/{company_id}/routines
  POST   /api/llc/companies/{company_id}/routines
  GET    /api/llc/routines/{routine_id}
  PATCH  /api/llc/routines/{routine_id}
  DELETE /api/llc/routines/{routine_id}
  GET    /api/llc/routines/{routine_id}/runs
  POST   /api/llc/routines/{routine_id}/trigger
"""

import time
import uuid
from datetime import datetime
from typing import List, Optional

try:
    from croniter import croniter as croniter
except ImportError:
    croniter = None  # type: ignore[assignment,misc]  # croniter not installed
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user
from autobot_shared.redis_client import get_async_redis_client
from llc.deps import get_session, service_dep

from ..models.enums import RoutineProduces, RoutineStatus
from ..scheduler.routine_scheduler import _SCHEDULE_KEY
from ..services.routine_service import RoutineService

router = APIRouter(tags=["llc-routines"])
_service = service_dep(RoutineService)


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class RoutineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    cron_schedule: str
    assignee_agent_id: Optional[uuid.UUID] = None
    env: Optional[dict] = None
    produces: RoutineProduces = RoutineProduces.NEW_WORK_ITEM
    work_item_template: Optional[dict] = None
    recurring_work_item_id: Optional[uuid.UUID] = None


class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cron_schedule: Optional[str] = None
    assignee_agent_id: Optional[uuid.UUID] = None
    status: Optional[RoutineStatus] = None
    env: Optional[dict] = None
    produces: Optional[RoutineProduces] = None
    work_item_template: Optional[dict] = None
    recurring_work_item_id: Optional[uuid.UUID] = None


class RoutineRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: Optional[str]
    cron_schedule: str
    assignee_agent_id: Optional[uuid.UUID]
    status: RoutineStatus
    env: Optional[dict]
    produces: RoutineProduces
    work_item_template: Optional[dict]
    recurring_work_item_id: Optional[uuid.UUID]
    last_fired_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime


class RoutineRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    routine_id: uuid.UUID
    heartbeat_run_id: Optional[uuid.UUID]
    work_item_id: Optional[uuid.UUID]
    status: str
    started_at: Optional[datetime]
    finished_at: Optional[datetime]
    created_at: datetime


class TriggerResponse(BaseModel):
    routine_id: uuid.UUID
    message: str = "Routine scheduled for immediate execution"


# ------------------------------------------------------------------
# Company-scoped routes
# ------------------------------------------------------------------


@router.get("/companies/{company_id}/routines", response_model=List[RoutineRead])
async def list_routines(
    company_id: uuid.UUID,
    status: Optional[RoutineStatus] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> List[RoutineRead]:
    routines = await _service().list(
        session,
        company_id=company_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    return [RoutineRead.model_validate(r) for r in routines]


@router.post(
    "/companies/{company_id}/routines",
    response_model=RoutineRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_routine(
    company_id: uuid.UUID,
    body: RoutineCreate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> RoutineRead:
    if croniter is None:
        raise HTTPException(status_code=503, detail="Routine scheduling unavailable — croniter not installed")
    if not croniter.is_valid(body.cron_schedule):
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {body.cron_schedule!r}")
    routine = await _service().create(
        session,
        company_id,
        body.name,
        body.cron_schedule,
        body.produces,
        body.work_item_template or {},
        assignee_agent_id=body.assignee_agent_id,
        description=body.description,
        env=body.env,
        recurring_work_item_id=body.recurring_work_item_id,
    )
    await session.commit()
    await session.refresh(routine)
    try:
        redis = await get_async_redis_client()
        if redis is not None:
            from datetime import timezone

            next_ts: float = croniter(body.cron_schedule, datetime.now(tz=timezone.utc)).get_next(float)
            await redis.zadd(_SCHEDULE_KEY, {f"routine:{routine.id}": next_ts}, nx=True)
    except Exception:
        pass
    return RoutineRead.model_validate(routine)


# ------------------------------------------------------------------
# Resource-level routes
# ------------------------------------------------------------------


@router.get("/routines/{routine_id}", response_model=RoutineRead)
async def get_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> RoutineRead:
    routine = await _service().get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    return RoutineRead.model_validate(routine)


@router.patch("/routines/{routine_id}", response_model=RoutineRead)
async def update_routine(
    routine_id: uuid.UUID,
    body: RoutineUpdate,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> RoutineRead:
    updates = body.model_dump(exclude_unset=True)
    new_cron = updates.get("cron_schedule")
    if croniter is None and new_cron is not None:
        raise HTTPException(status_code=503, detail="Routine scheduling unavailable — croniter not installed")
    if new_cron is not None and not croniter.is_valid(new_cron):
        raise HTTPException(status_code=422, detail=f"Invalid cron expression: {new_cron!r}")
    try:
        routine = await _service().update(session, routine_id, **updates)
    except ValueError:
        raise HTTPException(status_code=404, detail="Routine not found")
    await session.commit()
    await session.refresh(routine)
    new_status = updates.get("status")
    try:
        redis = await get_async_redis_client()
        if redis is not None:
            if new_status is not None and new_status != RoutineStatus.ACTIVE:
                # Deactivated — remove from schedule
                await redis.zrem(_SCHEDULE_KEY, f"routine:{routine_id}")
            elif new_status == RoutineStatus.ACTIVE or new_cron is not None:
                # Re-activated or cron changed — re-insert with updated next fire time
                cron_expr = new_cron or routine.cron_schedule
                from datetime import timezone

                next_ts: float = croniter(cron_expr, datetime.now(tz=timezone.utc)).get_next(float)
                await redis.zadd(_SCHEDULE_KEY, {f"routine:{routine_id}": next_ts}, nx=False)
    except Exception:
        pass
    return RoutineRead.model_validate(routine)


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> None:
    routine = await _service().get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    await _service().delete(session, routine_id)
    await session.commit()


@router.get("/routines/{routine_id}/runs", response_model=List[RoutineRunRead])
async def list_routine_runs(
    routine_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> List[RoutineRunRead]:
    routine = await _service().get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    runs = await _service().list_runs(session, routine_id, limit=limit, offset=offset)
    return [RoutineRunRead.model_validate(r) for r in runs]


@router.post(
    "/routines/{routine_id}/trigger",
    response_model=TriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
) -> TriggerResponse:
    routine = await _service().get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    if routine.status != RoutineStatus.ACTIVE:
        raise HTTPException(status_code=409, detail="Routine is not active")
    # Schedule for immediate dispatch — the scheduler creates the run record when it fires,
    # preventing the double-run that would occur if we called record_run here too.
    try:
        redis = await get_async_redis_client()
        if redis is not None:
            await redis.zadd(_SCHEDULE_KEY, {f"routine:{routine_id}": time.time()}, nx=False)
    except Exception:
        pass
    return TriggerResponse(routine_id=routine_id)
