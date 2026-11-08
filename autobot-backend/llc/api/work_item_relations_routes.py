# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Work-item relation routes (GH#8252, #20103).

Moved out of ``work_items.py`` (at its size ceiling); the paths are unchanged.

Scope and identity come from the verified caller, never the request: the company
is ``ctx.org_id`` and the acting user is ``actor_id(current_user)``. ``company_id``,
``created_by_*`` and ``actor_*`` are still accepted so an existing client does not
start failing with a 422, and are ignored.
"""

import uuid
from typing import Any, Dict, Optional

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import get_session, service_dep
from user_management.services import TenantContext

from ..models.enums import WorkItemRelationType
from ..models.work_item import LLCWorkItemRelation
from ..services.work_item_relations import RelationConflict, WorkItemRelationService
from ..services.work_item_service import WorkItemService
from ._common import actor_id, require_work_item_id

logger = get_logger(__name__)
router = APIRouter(prefix="/work-items", tags=["llc-work-items"], dependencies=[Depends(require_work_item_id)])
_get_relation_service = lazy_singleton(WorkItemRelationService)
_service = service_dep(WorkItemService)

_NOT_FOUND = "Work item not found"
_REL_NOT_FOUND = "Relation not found"


class RelationCreate(BaseModel):
    """``company_id`` and ``created_by_*`` are accepted for compatibility and ignored."""

    company_id: Optional[str] = None
    target_id: str
    relation_type: WorkItemRelationType
    created_by_agent_id: Optional[str] = None
    created_by_user_id: Optional[str] = None


def _relation_service() -> WorkItemRelationService:
    return _get_relation_service()


async def _require_item(session: AsyncSession, item_id: str, ctx: TenantContext) -> None:
    """404 unless the item exists in the caller's company (IDOR guard, M4/GH#9861)."""
    try:
        item = await _service().get(session, item_id, company_id=str(ctx.org_id))
    except ValueError:
        item = None
    if item is None or str(item.company_id) != str(ctx.org_id):
        raise HTTPException(status_code=404, detail=_NOT_FOUND)


async def _require_relation_of(session: AsyncSession, relation_id: str, item_id: str, ctx: TenantContext) -> None:
    """404 unless the relation is in the caller's company and touches ``item_id`` (#20114).

    Either end qualifies: a relation and its mirror leg join the same two items, so
    removing through either item reaches the pair.
    """
    try:
        rid, iid = uuid.UUID(relation_id), uuid.UUID(item_id)
    except ValueError:
        raise HTTPException(status_code=404, detail=_REL_NOT_FOUND)
    rel = (
        await session.execute(
            select(LLCWorkItemRelation).where(
                LLCWorkItemRelation.id == rid,
                LLCWorkItemRelation.company_id == ctx.org_id,
                sa.or_(LLCWorkItemRelation.source_id == iid, LLCWorkItemRelation.target_id == iid),
            )
        )
    ).scalar_one_or_none()
    if rel is None:
        raise HTTPException(status_code=404, detail=_REL_NOT_FOUND)


@router.post("/{work_item_id}/relations", status_code=201)
async def add_relation(
    work_item_id: str,
    body: RelationCreate,
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> Dict[str, Any]:
    await _require_item(session, work_item_id, ctx)
    await _require_item(session, body.target_id, ctx)
    try:
        rel = await _relation_service().add(
            session,
            company_id=str(ctx.org_id),
            source_id=work_item_id,
            target_id=body.target_id,
            relation_type=body.relation_type,
            created_by_user_id=str(actor_id(current_user)),
        )
        await session.commit()
    except RelationConflict as exc:
        logger.info("Relation conflict on %s: %s", work_item_id, exc)
        raise HTTPException(status_code=409, detail="Relation already exists or is invalid")
    except ValueError as exc:
        logger.info("Relation add rejected on %s: %s", work_item_id, exc)
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return {
        "id": str(rel.id),
        "source_id": work_item_id,
        "target_id": body.target_id,
        "relation_type": rel.relation_type,
    }


@router.delete("/{work_item_id}/relations/{relation_id}", status_code=204)
async def remove_relation(
    work_item_id: str,
    relation_id: str,
    company_id: Optional[str] = Query(None, description="Accepted for compatibility; ignored."),
    actor_agent_id: Optional[str] = Query(None, description="Accepted for compatibility; ignored."),
    actor_user_id: Optional[str] = Query(None, description="Accepted for compatibility; ignored."),
    session: AsyncSession = Depends(get_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    await _require_item(session, work_item_id, ctx)
    await _require_relation_of(session, relation_id, work_item_id, ctx)
    try:
        await _relation_service().remove(
            session,
            company_id=str(ctx.org_id),
            relation_id=relation_id,
            actor_user_id=str(actor_id(current_user)),
        )
        await session.commit()
    except ValueError as exc:
        logger.info("Relation remove rejected on %s: %s", work_item_id, exc)
        raise HTTPException(status_code=404, detail=_REL_NOT_FOUND)
