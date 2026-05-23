# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

from ..models.enums import RoutineProduces, RoutineStatus
from ..services.routine_service import RoutineService

router = APIRouter(tags=["llc-routines"])
_get_service = lazy_singleton(RoutineService)


def _service() -> RoutineService:
    return _get_service()


async def get_session() -> AsyncSession:
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------


class RoutineCreate(BaseModel):
    name: str
    description: Optional[str] = None
    cron_schedule: str
    assignee_agent_id: Optional[str] = None
    env: Optional[dict] = None
    produces: RoutineProduces = RoutineProduces.NEW_WORK_ITEM
    work_item_template: Optional[dict] = None
    recurring_work_item_id: Optional[str] = None


class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    cron_schedule: Optional[str] = None
    assignee_agent_id: Optional[str] = None
    status: Optional[RoutineStatus] = None
    env: Optional[dict] = None
    produces: Optional[RoutineProduces] = None
    work_item_template: Optional[dict] = None
    recurring_work_item_id: Optional[str] = None


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
) -> RoutineRead:
    routine = await _service().create(
        session,
        company_id,
        body.name,
        body.cron_schedule,
        body.produces,
        body.work_item_template or {},
        assignee_agent_id=uuid.UUID(body.assignee_agent_id) if body.assignee_agent_id else None,
        description=body.description,
        env=body.env,
        recurring_work_item_id=uuid.UUID(body.recurring_work_item_id) if body.recurring_work_item_id else None,
    )
    await session.commit()
    await session.refresh(routine)
    return RoutineRead.model_validate(routine)


# ------------------------------------------------------------------
# Resource-level routes
# ------------------------------------------------------------------


@router.get("/routines/{routine_id}", response_model=RoutineRead)
async def get_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
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
) -> RoutineRead:
    updates = body.model_dump(exclude_unset=True)
    if "assignee_agent_id" in updates and updates["assignee_agent_id"] is not None:
        updates["assignee_agent_id"] = uuid.UUID(updates["assignee_agent_id"])
    if "recurring_work_item_id" in updates and updates["recurring_work_item_id"] is not None:
        updates["recurring_work_item_id"] = uuid.UUID(updates["recurring_work_item_id"])
    try:
        routine = await _service().update(session, routine_id, **updates)
    except ValueError:
        raise HTTPException(status_code=404, detail="Routine not found")
    await session.commit()
    await session.refresh(routine)
    return RoutineRead.model_validate(routine)


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await _service().delete(session, routine_id)
    await session.commit()


@router.get("/routines/{routine_id}/runs", response_model=List[RoutineRunRead])
async def list_routine_runs(
    routine_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> List[RoutineRunRead]:
    routine = await _service().get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    runs = await _service().list_runs(session, routine_id, limit=limit, offset=offset)
    return [RoutineRunRead.model_validate(r) for r in runs]


@router.post(
    "/routines/{routine_id}/trigger",
    response_model=RoutineRunRead,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RoutineRunRead:
    routine = await _service().get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    run = await _service().record_run(session, routine_id, "queued")
    await session.commit()
    await session.refresh(run)
    return RoutineRunRead.model_validate(run)
