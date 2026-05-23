# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC Routine API routes (GH#8229).

Routes:
  POST   /api/llc/companies/{company_id}/routines          — create routine
  GET    /api/llc/companies/{company_id}/routines          — list routines
  GET    /api/llc/routines/{id}                            — get routine
  PATCH  /api/llc/routines/{id}                            — update routine
  DELETE /api/llc/routines/{id}                            — soft-delete (archive)
  POST   /api/llc/routines/{id}/trigger                    — manual trigger → queued run
  GET    /api/llc/routines/{id}/runs                       — paginated run history
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session_factory

from ..models.enums import RoutineStatus
from ..services.routine_service import RoutineNotFoundError, RoutineService

router = APIRouter(tags=["llc-routines"])
_get_service = lazy_singleton(RoutineService)


def _service() -> RoutineService:
    return _get_service()


async def get_session() -> AsyncSession:
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


# ------------------------------------------------------------------
# Request / response schemas
# ------------------------------------------------------------------


class RoutineCreate(BaseModel):
    agent_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    cron_schedule: str = Field(..., description="Standard 5-field cron expression")
    description: Optional[str] = None
    env: Dict[str, Any] = {}


class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    cron_schedule: Optional[str] = None
    description: Optional[str] = None
    env: Optional[Dict[str, Any]] = None
    status: Optional[RoutineStatus] = None


class RoutineResponse(BaseModel):
    id: str
    company_id: str
    agent_id: str
    name: str
    cron_schedule: str
    description: Optional[str]
    env: Dict[str, Any]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "RoutineResponse":
        return cls(
            id=str(obj.id),
            company_id=str(obj.company_id),
            agent_id=str(obj.agent_id),
            name=obj.name,
            cron_schedule=obj.cron_schedule,
            description=obj.description,
            env=obj.env,
            status=obj.status if isinstance(obj.status, str) else obj.status.value,
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )


class RoutineRunResponse(BaseModel):
    id: str
    routine_id: str
    status: str
    triggered_at: datetime
    completed_at: Optional[datetime]
    error: Optional[str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "RoutineRunResponse":
        return cls(
            id=str(obj.id),
            routine_id=str(obj.routine_id),
            status=obj.status,
            triggered_at=obj.triggered_at,
            completed_at=obj.completed_at,
            error=obj.error,
        )


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------


@router.post(
    "/companies/{company_id}/routines",
    response_model=RoutineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_routine(
    company_id: uuid.UUID,
    body: RoutineCreate,
    session: AsyncSession = Depends(get_session),
) -> RoutineResponse:
    svc = _service()
    routine = await svc.create(
        session,
        company_id=company_id,
        agent_id=body.agent_id,
        name=body.name,
        cron_schedule=body.cron_schedule,
        description=body.description,
        env=body.env,
    )
    await session.commit()
    return RoutineResponse.from_orm_obj(routine)


@router.get("/companies/{company_id}/routines", response_model=List[RoutineResponse])
async def list_routines(
    company_id: uuid.UUID,
    status_filter: Optional[RoutineStatus] = Query(None, alias="status"),
    session: AsyncSession = Depends(get_session),
) -> List[RoutineResponse]:
    svc = _service()
    routines = await svc.list(session, company_id=company_id, status=status_filter)
    return [RoutineResponse.from_orm_obj(r) for r in routines]


@router.get("/routines/{routine_id}", response_model=RoutineResponse)
async def get_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RoutineResponse:
    svc = _service()
    try:
        routine = await svc.get(session, routine_id)
    except RoutineNotFoundError:
        raise HTTPException(status_code=404, detail="Routine not found")
    return RoutineResponse.from_orm_obj(routine)


@router.patch("/routines/{routine_id}", response_model=RoutineResponse)
async def update_routine(
    routine_id: uuid.UUID,
    body: RoutineUpdate,
    session: AsyncSession = Depends(get_session),
) -> RoutineResponse:
    svc = _service()
    try:
        routine = await svc.update(
            session,
            routine_id,
            cron_schedule=body.cron_schedule,
            name=body.name,
            description=body.description,
            env=body.env,
            status=body.status,
        )
    except RoutineNotFoundError:
        raise HTTPException(status_code=404, detail="Routine not found")
    await session.commit()
    return RoutineResponse.from_orm_obj(routine)


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = _service()
    try:
        await svc.delete(session, routine_id)
    except RoutineNotFoundError:
        raise HTTPException(status_code=404, detail="Routine not found")
    await session.commit()


@router.post(
    "/routines/{routine_id}/trigger",
    response_model=RoutineRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def trigger_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RoutineRunResponse:
    svc = _service()
    try:
        await svc.get(session, routine_id)
    except RoutineNotFoundError:
        raise HTTPException(status_code=404, detail="Routine not found")
    run = await svc.record_run(session, routine_id, status="queued")
    await session.commit()
    return RoutineRunResponse.from_orm_obj(run)


@router.get("/routines/{routine_id}/runs", response_model=List[RoutineRunResponse])
async def list_runs(
    routine_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> List[RoutineRunResponse]:
    svc = _service()
    runs = await svc.list_runs(session, routine_id, limit=limit, offset=offset)
    return [RoutineRunResponse.from_orm_obj(r) for r in runs]
