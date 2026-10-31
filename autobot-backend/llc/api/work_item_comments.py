# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC work item comment read route (GH#18750).

Routes:
  GET /api/llc/work-items/{work_item_id}/comments

Split out of ``work_items.py``, which sits at its file-size ceiling. The POST
sibling (``add_comment``) stays in ``work_items.py``; both are tenant-scoped by
the same IDOR guard (GH#9861): another company's item is indistinguishable
from a missing one.
"""

import uuid
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.env_utils import env_int_clamped
from autobot_shared.logging_manager import get_logger
from llc.deps import get_session, service_dep
from user_management.services import TenantContext

from ..models.work_item import LLCWorkItemComment
from ..services.work_item_service import WorkItemService

logger = get_logger(__name__)

# Page-size bounds, env-backed so an operator can tune them without a deploy. A floor of 1 keeps a
# zero or negative setting from making every limit a 422.
COMMENTS_PAGE_DEFAULT = env_int_clamped("LLC_COMMENTS_PAGE_DEFAULT", 100, min_v=1)
COMMENTS_PAGE_MAX = env_int_clamped("LLC_COMMENTS_PAGE_MAX", 500, min_v=1)

router = APIRouter(prefix="/work-items", tags=["llc-work-items"])
_service = service_dep(WorkItemService)


def serialize_comment(comment: LLCWorkItemComment) -> Dict[str, Any]:
    """One comment on the wire, for the list route and the POST sibling."""
    return {
        "id": str(comment.id),
        "work_item_id": str(comment.work_item_id),
        "company_id": str(comment.company_id),
        "body": comment.body,
        "author_agent_id": (str(comment.author_agent_id) if comment.author_agent_id else None),
        "author_user_id": (str(comment.author_user_id) if comment.author_user_id else None),
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


@router.get("/{work_item_id}/comments")
async def list_comments(
    work_item_id: str,
    limit: int = Query(COMMENTS_PAGE_DEFAULT, ge=1, le=COMMENTS_PAGE_MAX),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    """List a work item's comments, oldest first, in the caller's tenant."""
    existing = await _service().get(session, work_item_id)
    if existing is None or str(existing.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail="Work item not found")
    stmt = (
        select(LLCWorkItemComment)
        .where(
            LLCWorkItemComment.work_item_id == uuid.UUID(work_item_id),
            LLCWorkItemComment.company_id == uuid.UUID(str(ctx.org_id)),
        )
        .order_by(LLCWorkItemComment.created_at.asc(), LLCWorkItemComment.id.asc())
        .limit(limit + 1)  # one extra row says whether another page exists
        .offset(offset)
    )
    rows = (await session.execute(stmt)).scalars().all()
    return {
        "comments": [serialize_comment(c) for c in rows[:limit]],
        "limit": limit,
        "offset": offset,
        "has_more": len(rows) > limit,
    }
