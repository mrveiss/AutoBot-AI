"""LLC activity log API (GH#8216).

GET /api/llc/companies/{company_id}/activity — paginated, filterable audit trail.
"""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user
from user_management.database import get_async_session

from ..models.activity import ActorType
from ..services.activity_log import ActivityLogQuery, LLCActivityLogService

router = APIRouter()

_service = LLCActivityLogService()


class ActivityLogEntry(BaseModel):
    id: str
    company_id: str
    actor_type: str
    actor_agent_id: str | None
    actor_user_id: str | None
    entity_type: str
    entity_id: str
    action: str
    before_state: dict[str, Any] | None
    after_state: dict[str, Any]
    metadata: dict[str, Any] | None
    occurred_at: datetime

    model_config = {"from_attributes": True}


class ActivityLogResponse(BaseModel):
    items: list[ActivityLogEntry]
    page: int
    page_size: int
    total: int
    has_next: bool


@router.get("/companies/{company_id}/activity", response_model=ActivityLogResponse)
async def get_activity_log(
    company_id: str,
    entity_type: str | None = Query(None),
    entity_id: str | None = Query(None),
    action: str | None = Query(None),
    actor_type: ActorType | None = Query(None),
    actor_id: str | None = Query(None),
    from_date: datetime | None = Query(None),
    to_date: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
) -> ActivityLogResponse:
    """Return paginated activity log for a company.

    All filters are optional and AND-ed together. Results are ordered by
    occurred_at descending (newest first).
    """
    params = ActivityLogQuery(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_type=actor_type,
        actor_id=actor_id,
        from_date=from_date,
        to_date=to_date,
        page=page,
        page_size=page_size,
    )

    result = await _service.query(session=session, company_id=company_id, params=params)

    items = [
        ActivityLogEntry(
            id=str(row.id),
            company_id=str(row.company_id),
            actor_type=row.actor_type,
            actor_agent_id=str(row.actor_agent_id) if row.actor_agent_id else None,
            actor_user_id=str(row.actor_user_id) if row.actor_user_id else None,
            entity_type=row.entity_type,
            entity_id=str(row.entity_id),
            action=row.action,
            before_state=row.before_state,
            after_state=row.after_state,
            metadata=row.log_metadata,
            occurred_at=row.occurred_at,
        )
        for row in result.items
    ]

    return ActivityLogResponse(
        items=items,
        page=result.page,
        page_size=result.page_size,
        total=result.total,
        has_next=result.has_next,
    )
