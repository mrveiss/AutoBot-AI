# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Config Revisions API (#1404)

Endpoints for listing, inspecting, and rolling back configuration revisions.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_db_session
from auth_middleware import get_current_user
from services.config_revision_service import ConfigRevisionService

logger = logging.getLogger(__name__)
router = APIRouter()


# -- Response schemas --------------------------------------------------


class ConfigRevisionResponse(BaseModel):
    """Response for a single config revision."""

    id: str
    entity_type: str
    entity_id: str
    before_config: Optional[Dict[str, Any]] = None
    after_config: Dict[str, Any]
    changed_keys: List[str] = Field(default_factory=list)
    source: str
    created_by: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# -- Helpers -----------------------------------------------------------


def _to_response(revision) -> ConfigRevisionResponse:
    """Convert a ConfigRevision ORM object to response schema (#1404)."""
    return ConfigRevisionResponse(
        id=str(revision.id),
        entity_type=revision.entity_type,
        entity_id=revision.entity_id,
        before_config=revision.before_config,
        after_config=revision.after_config,
        changed_keys=revision.changed_keys or [],
        source=revision.source,
        created_by=revision.created_by,
        created_at=(revision.created_at.isoformat() if revision.created_at else None),
        updated_at=(revision.updated_at.isoformat() if revision.updated_at else None),
    )


# -- Endpoints ---------------------------------------------------------


@router.get(
    "/config-revisions/{entity_type}/{entity_id}",
    response_model=List[ConfigRevisionResponse],
)
async def list_revisions(
    entity_type: str,
    entity_id: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """List revision history for an entity, newest first (#1404)."""
    svc = ConfigRevisionService(session)
    revisions = await svc.get_revisions(
        entity_type=entity_type,
        entity_id=entity_id,
        limit=limit,
        offset=offset,
    )
    return [_to_response(r) for r in revisions]


@router.get(
    "/config-revisions/{entity_type}/{entity_id}/{revision_id}",
    response_model=ConfigRevisionResponse,
)
async def get_revision(
    entity_type: str,
    entity_id: str,
    revision_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Get a specific revision with diff metadata (#1404)."""
    svc = ConfigRevisionService(session)
    revision = await svc.get_revision(revision_id)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {revision_id} not found",
        )
    if revision.entity_type != entity_type or revision.entity_id != entity_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Revision {revision_id} does not belong to {entity_type}/{entity_id}",
        )
    return _to_response(revision)


@router.post(
    "/config-revisions/{entity_type}/{entity_id}/{revision_id}/rollback",
    response_model=ConfigRevisionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def rollback_to_revision(
    entity_type: str,
    entity_id: str,
    revision_id: uuid.UUID,
    current_user: dict = Depends(get_current_user),
    session: AsyncSession = Depends(get_db_session),
):
    """Roll back entity config to a prior revision (#1404).

    Creates a new revision capturing the rollback so the action is
    itself part of the audit trail.
    """
    svc = ConfigRevisionService(session)
    username = current_user.get("username", "unknown")
    try:
        new_revision = await svc.rollback_to_revision(revision_id, username)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Request failed",
        )
    return _to_response(new_revision)
