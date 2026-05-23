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
# Request / response schemas
# ------------------------------------------------------------------


class RoutineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    cron_schedule: str = Field(..., description="Standard 5-field cron expression")
    produces: RoutineProduces = RoutineProduces.NEW_WORK_ITEM
    work_item_template: Dict[str, Any] = {}
    assignee_agent_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    env: Optional[Dict[str, Any]] = None


class RoutineUpdate(BaseModel):
    name: Optional[str] = None
    cron_schedule: Optional[str] = None
    description: Optional[str] = None
    env: Optional[Dict[str, Any]] = None
    status: Optional[RoutineStatus] = None


class RoutineResponse(BaseModel):
    id: str
    company_id: str
    name: str
    cron_schedule: str
    produces: str
    description: Optional[str]
    env: Optional[Dict[str, Any]]
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "RoutineResponse":
        return cls(
            id=str(obj.id),
            company_id=str(obj.company_id),
            name=obj.name,
            cron_schedule=obj.cron_schedule,
            produces=obj.produces if isinstance(obj.produces, str) else obj.produces.value,
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
    created_at: datetime
    heartbeat_run_id: Optional[str]
    work_item_id: Optional[str]

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_obj(cls, obj: Any) -> "RoutineRunResponse":
        return cls(
            id=str(obj.id),
            routine_id=str(obj.routine_id),
            status=obj.status,
            created_at=obj.created_at,
            heartbeat_run_id=str(obj.heartbeat_run_id) if obj.heartbeat_run_id else None,
            work_item_id=str(obj.work_item_id) if obj.work_item_id else None,
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
        company_id,
        body.name,
        body.cron_schedule,
        body.produces,
        body.work_item_template,
        assignee_agent_id=body.assignee_agent_id,
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
    routines = await svc.list(session, company_id, status=status_filter)
    return [RoutineResponse.from_orm_obj(r) for r in routines]


@router.get("/routines/{routine_id}", response_model=RoutineResponse)
async def get_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> RoutineResponse:
    svc = _service()
    routine = await svc.get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    return RoutineResponse.from_orm_obj(routine)


@router.patch("/routines/{routine_id}", response_model=RoutineResponse)
async def update_routine(
    routine_id: uuid.UUID,
    body: RoutineUpdate,
    session: AsyncSession = Depends(get_session),
) -> RoutineResponse:
    svc = _service()
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        routine = await svc.update(session, routine_id, **updates)
    except ValueError:
        raise HTTPException(status_code=404, detail="Routine not found")
    await session.commit()
    return RoutineResponse.from_orm_obj(routine)


@router.delete("/routines/{routine_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_routine(
    routine_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    svc = _service()
    await svc.delete(session, routine_id)
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
    routine = await svc.get(session, routine_id)
    if routine is None:
        raise HTTPException(status_code=404, detail="Routine not found")
    run = await svc.record_run(session, routine_id, "queued")
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
