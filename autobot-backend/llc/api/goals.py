# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC goal API routes (GH#8212, GH#6469).

Routes:
  GET    /llc/goals                — list root goals for a company
  POST   /llc/goals                — create a goal
  GET    /llc/goals/{id}           — get single goal
  PATCH  /llc/goals/{id}           — update goal fields
  DELETE /llc/goals/{id}           — delete goal + subtree
  GET    /llc/goals/{id}/ancestors — ancestor chain (root-first)
  GET    /llc/goals/{id}/tasks     — work items linked to this goal (GH#6469)
"""

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.singleton_factory import lazy_singleton
from user_management.database import get_async_session

from ..models.goal import GoalLevel, GoalStatus
from ..models.work_item import LLCWorkItem
from ..services.goal import GoalService

router = APIRouter(prefix="/goals", tags=["llc-goals"])

_get_svc = lazy_singleton(GoalService)


def _svc() -> GoalService:
    return _get_svc()


# ------------------------------------------------------------------ Schemas


class GoalCreate(BaseModel):
    company_id: str
    title: str
    level: GoalLevel
    description: Optional[str] = None
    parent_goal_id: Optional[uuid.UUID] = None
    owner_agent_id: Optional[str] = None
    due_date: Optional[datetime] = None
    status: GoalStatus = GoalStatus.DRAFT


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    level: Optional[GoalLevel] = None
    status: Optional[GoalStatus] = None
    owner_agent_id: Optional[str] = None
    due_date: Optional[datetime] = None
    parent_goal_id: Optional[uuid.UUID] = None


class GoalResponse(BaseModel):
    id: uuid.UUID
    company_id: str
    parent_goal_id: Optional[uuid.UUID]
    title: str
    description: Optional[str]
    level: str
    status: str
    owner_agent_id: Optional[str]
    due_date: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkItemSummaryResponse(BaseModel):
    """Compact work item projection returned by GET /llc/goals/{id}/tasks (GH#6469)."""

    id: uuid.UUID
    identifier: str
    title: str
    type: str
    status: str
    priority: str
    goal_id: Optional[uuid.UUID]
    parent_id: Optional[uuid.UUID]
    assignee_agent_id: Optional[uuid.UUID]
    assignee_user_id: Optional[uuid.UUID]

    class Config:
        from_attributes = True


# ------------------------------------------------------------------ Routes


@router.get("", response_model=List[GoalResponse])
async def list_goals(
    company_id: str = Query(..., description="Company ID to filter goals"),
    parent_goal_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(get_async_session),
) -> List[GoalResponse]:
    goals = await _svc().list_by_company(session, company_id, parent_goal_id)
    return [GoalResponse.model_validate(g) for g in goals]


@router.post("", response_model=GoalResponse, status_code=201)
async def create_goal(
    body: GoalCreate,
    session: AsyncSession = Depends(get_async_session),
) -> GoalResponse:
    goal = await _svc().create(
        session,
        company_id=body.company_id,
        title=body.title,
        level=body.level,
        description=body.description,
        parent_goal_id=body.parent_goal_id,
        owner_agent_id=body.owner_agent_id,
        due_date=body.due_date,
        status=body.status,
    )
    return GoalResponse.model_validate(goal)


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> GoalResponse:
    goal = await _svc().get(session, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return GoalResponse.model_validate(goal)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: uuid.UUID,
    body: GoalUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> GoalResponse:
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    goal = await _svc().update(session, goal_id, **updates)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return GoalResponse.model_validate(goal)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    deleted = await _svc().delete(session, goal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")


@router.get("/{goal_id}/ancestors", response_model=List[GoalResponse])
async def get_ancestors(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> List[GoalResponse]:
    goal = await _svc().get(session, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    ancestors = await _svc().get_ancestors(session, goal_id)
    return [GoalResponse.model_validate(a) for a in ancestors]


@router.get("/{goal_id}/tasks", response_model=List[WorkItemSummaryResponse])
async def list_tasks_for_goal(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
) -> List[WorkItemSummaryResponse]:
    """Return all work items linked to a goal (GH#6469)."""
    goal = await _svc().get(session, goal_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.goal_id == goal_id))
    items = result.scalars().all()
    return [WorkItemSummaryResponse.model_validate(item) for item in items]
