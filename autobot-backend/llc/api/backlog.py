# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC Backlog view API routes (GH#8222).

Routes:
  GET  /api/llc/backlog  — priority-ordered backlog with type/status/sprint filters + pagination
  POST /api/llc/backlog/bulk-assign-sprint — assign multiple items to a sprint in one call
"""

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import WorkItemStatus, WorkItemType
from ..models.work_item import LLCWorkItem
from ..services.backlog import BacklogService
from llc.deps import get_session, service_dep

router = APIRouter(prefix="/backlog", tags=["llc-backlog"])
_service = service_dep(BacklogService)


def _item_to_dict(item: LLCWorkItem) -> Dict[str, Any]:
    return {
        "id": str(item.id),
        "company_id": str(item.company_id),
        "identifier": item.identifier,
        "type": item.type,
        "title": item.title,
        "description": item.description,
        "status": item.status,
        "priority": item.priority,
        "story_points": item.story_points,
        "labels": item.labels,
        "parent_id": str(item.parent_id) if item.parent_id else None,
        "project_id": str(item.project_id) if item.project_id else None,
        "sprint_id": str(item.sprint_id) if item.sprint_id else None,
        "goal_id": str(item.goal_id) if item.goal_id else None,
        "assignee_agent_id": str(item.assignee_agent_id) if item.assignee_agent_id else None,
        "assignee_user_id": str(item.assignee_user_id) if item.assignee_user_id else None,
        "assignee_type": item.assignee_type,
        "version": item.version,
        "created_by_agent_id": str(item.created_by_agent_id) if item.created_by_agent_id else None,
        "created_by_user_id": str(item.created_by_user_id) if item.created_by_user_id else None,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "cancelled_at": item.cancelled_at.isoformat() if item.cancelled_at else None,
        "created_at": item.created_at.isoformat() if hasattr(item, "created_at") and item.created_at else None,
        "updated_at": item.updated_at.isoformat() if hasattr(item, "updated_at") and item.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class BacklogResponse(BaseModel):
    items: List[Dict[str, Any]]
    total: int
    limit: int
    offset: int


class BulkAssignSprintRequest(BaseModel):
    company_id: str
    sprint_id: str
    work_item_ids: List[str] = Field(..., min_length=1, max_length=500)


class BulkAssignSprintResponse(BaseModel):
    updated: int
    sprint_id: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", response_model=BacklogResponse)
async def get_backlog(
    company_id: str = Query(..., description="Company UUID"),
    project_id: Optional[str] = Query(None, description="Filter by project"),
    status: Optional[WorkItemStatus] = Query(None, description="Filter by work item status"),
    type: Optional[WorkItemType] = Query(None, description="Filter by work item type"),
    sprint_id: Optional[str] = Query(
        None,
        description="Filter by sprint UUID. When omitted, returns unassigned items (sprint_id IS NULL).",
    ),
    limit: int = Query(50, ge=1, le=500, description="Page size"),
    offset: int = Query(0, ge=0, description="Page offset"),
    session: AsyncSession = Depends(get_session),
) -> BacklogResponse:
    """Return backlog items ordered by priority (CRITICAL → HIGH → MEDIUM → LOW), then age."""
    items, total = await _service().list_backlog(
        session,
        company_id=company_id,
        project_id=project_id,
        status=status,
        type=type,
        sprint_id=sprint_id,
        limit=limit,
        offset=offset,
    )
    return BacklogResponse(
        items=[_item_to_dict(i) for i in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post("/bulk-assign-sprint", response_model=BulkAssignSprintResponse)
async def bulk_assign_sprint(
    body: BulkAssignSprintRequest,
    session: AsyncSession = Depends(get_session),
) -> BulkAssignSprintResponse:
    """Assign multiple backlog items to a sprint in a single DB round-trip.

    Items that don't belong to the given company are silently excluded.
    Returns the count of rows actually updated.
    """
    if not body.work_item_ids:
        raise HTTPException(status_code=422, detail="work_item_ids must not be empty")

    updated = await _service().bulk_assign_sprint(
        session,
        company_id=body.company_id,
        work_item_ids=body.work_item_ids,
        sprint_id=body.sprint_id,
    )
    await session.commit()
    return BulkAssignSprintResponse(updated=updated, sprint_id=body.sprint_id)
