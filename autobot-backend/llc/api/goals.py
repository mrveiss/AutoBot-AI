# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
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

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import assert_company_access
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..models.goal import GoalLevel, GoalStatus, LLCGoal
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


class GoalTreeNode(GoalResponse):
    """A goal plus its descendants, for the tree read path (#12739)."""

    children: List["GoalTreeNode"] = []


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


async def _get_authorized_goal(session: AsyncSession, goal_id: uuid.UUID, ctx: TenantContext) -> LLCGoal:
    """Load a goal and enforce tenant isolation; 404 if missing or cross-tenant (GH#12136).

    Uses the service getter (not the generic bare-select ``load_authorized``)
    because ``GoalService.get`` is the seam tests mock (test_goals_idor.py) —
    swapping to a raw ``session.execute(select(...))`` here would bypass that
    mock in the test harness and change observable behaviour.
    """
    goal = await _svc().get(session, goal_id)
    if goal is None or (str(goal.company_id) != str(ctx.org_id) and not ctx.is_platform_admin):
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal


def _build_goal_forest(goals: list) -> List["GoalTreeNode"]:
    """Assemble flat goals into nested roots (#12739).

    Orphans — a goal whose parent is missing or belongs to another company — are
    surfaced as roots rather than dropped. Silently discarding them would make
    the tree disagree with the flat list, which is the failure mode this
    endpoint exists to end.
    """
    nodes = {g.id: GoalTreeNode.model_validate(g) for g in goals}
    roots: List[GoalTreeNode] = []
    for goal in goals:
        node = nodes[goal.id]
        parent = nodes.get(goal.parent_goal_id) if goal.parent_goal_id else None
        if parent is None:
            roots.append(node)
        else:
            parent.children.append(node)
    return roots


# ------------------------------------------------------------------ Routes


@router.get("", response_model=List[GoalResponse])
async def list_goals(
    company_id: str = Query(..., description="Company ID to filter goals"),
    parent_goal_id: Optional[uuid.UUID] = Query(None),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[GoalResponse]:
    assert_company_access(ctx, company_id)
    goals = await _svc().list_by_company(session, company_id, parent_goal_id)
    return [GoalResponse.model_validate(g) for g in goals]


@router.post("", response_model=GoalResponse, status_code=201)
async def create_goal(
    body: GoalCreate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GoalResponse:
    assert_company_access(ctx, body.company_id)
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


# NOTE: /tree is declared BEFORE /{goal_id} on purpose. FastAPI matches routes in
# declaration order, so a later /tree would never be reached — "tree" would bind
# to {goal_id} and fail UUID parsing instead (#12739).
@router.get("/tree", response_model=List[GoalTreeNode])
async def get_goal_tree(
    company_id: str = Query(..., description="Company ID to build the goal tree for"),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[GoalTreeNode]:
    """Return the company's full goal hierarchy as nested roots (#12739).

    ``GET /goals`` returns only top-level goals, and children were reachable
    only by already knowing each parent id — so the tree UI could not render
    anything below the roots. One query, assembled in memory, rather than a
    round-trip per level.
    """
    assert_company_access(ctx, company_id)
    goals = await _svc().list_all_by_company(session, company_id)
    return _build_goal_forest(goals)


@router.get("/{goal_id}", response_model=GoalResponse)
async def get_goal(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GoalResponse:
    goal = await _get_authorized_goal(session, goal_id, ctx)
    return GoalResponse.model_validate(goal)


@router.patch("/{goal_id}", response_model=GoalResponse)
async def update_goal(
    goal_id: uuid.UUID,
    body: GoalUpdate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GoalResponse:
    await _get_authorized_goal(session, goal_id, ctx)
    updates = {k: v for k, v in body.model_dump(exclude_unset=True).items()}
    goal = await _svc().update(session, goal_id, **updates)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return GoalResponse.model_validate(goal)


@router.delete("/{goal_id}", status_code=204)
async def delete_goal(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    await _get_authorized_goal(session, goal_id, ctx)
    deleted = await _svc().delete(session, goal_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Goal not found")


@router.get("/{goal_id}/children", response_model=List[GoalResponse])
async def list_goal_children(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[GoalResponse]:
    """Direct children of *goal_id* (#12739). Complements the upward /ancestors."""
    goal = await _get_authorized_goal(session, goal_id, ctx)
    children = await _svc().list_by_company(session, str(goal.company_id), goal_id)
    return [GoalResponse.model_validate(c) for c in children]


@router.get("/{goal_id}/ancestors", response_model=List[GoalResponse])
async def get_ancestors(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[GoalResponse]:
    await _get_authorized_goal(session, goal_id, ctx)
    ancestors = await _svc().get_ancestors(session, goal_id)
    return [GoalResponse.model_validate(a) for a in ancestors]


@router.get("/{goal_id}/tasks", response_model=List[WorkItemSummaryResponse])
async def list_tasks_for_goal(
    goal_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[WorkItemSummaryResponse]:
    """Return all work items linked to a goal (GH#6469)."""
    await _get_authorized_goal(session, goal_id, ctx)
    result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.goal_id == goal_id))
    items = result.scalars().all()
    return [WorkItemSummaryResponse.model_validate(item) for item in items]
