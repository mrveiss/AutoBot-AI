# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC template library API routes (GH#8260).

Route group: /llc/templates
  POST   /                     — publish a template
  GET    /                     — list templates (filter by category, tag, q)
  GET    /search               — RAG semantic search over platform:template_kb
  GET    /{template_id}        — fetch full template JSON
  POST   /{template_id}/import — import template into target company
  DELETE /{template_id}        — delete template + remove from ChromaDB
"""

import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.template import (
    TemplateCategory,
    TemplateDetail,
    TemplateImportRequest,
    TemplateImportResult,
    TemplateListParams,
    TemplatePublishRequest,
    TemplateRead,
    TemplateSearchResponse,
    TemplateSearchResult,
)
from llc.services.template import (
    BuiltInTemplateNotFoundError,
    TemplateAccessError,
    TemplateNotFoundError,
    TemplateSecretPlaceholderError,
    TemplateService,
)
from user_management.database import get_async_session

router = APIRouter(prefix="/templates", tags=["llc-templates"])


def _get_service(session: AsyncSession = Depends(get_async_session)) -> TemplateService:
    """DI factory — injects TemplateService with session."""
    return TemplateService(session=session)


@router.post("/", response_model=TemplateDetail, status_code=status.HTTP_201_CREATED)
async def publish_template(
    req: TemplatePublishRequest,
    company_id: Optional[uuid.UUID] = Query(None, description="Owning company ID"),
    svc: TemplateService = Depends(_get_service),
) -> TemplateDetail:
    """Publish a scrubbed company export as a reusable template (GH#8260)."""
    try:
        result = await svc.publish(req, company_id=company_id)
        await svc.session.commit()
        return result
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")


@router.get("/search", response_model=TemplateSearchResponse)
async def search_templates(
    q: str = Query(..., min_length=1, description="Semantic search query"),
    svc: TemplateService = Depends(_get_service),
) -> TemplateSearchResponse:
    """RAG search over platform:template_kb ChromaDB collection (GH#8260)."""
    results: List[TemplateSearchResult] = await svc.search(q)
    return TemplateSearchResponse(query=q, results=results, total=len(results))


@router.get("/", response_model=List[TemplateRead])
async def list_templates(
    category: Optional[TemplateCategory] = Query(None),
    tag: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    company_id: Optional[uuid.UUID] = Query(None, description="Requesting company ID"),
    svc: TemplateService = Depends(_get_service),
) -> List[TemplateRead]:
    """List templates visible to the requesting company (GH#8260)."""
    params = TemplateListParams(
        category=category,
        tag=tag,
        q=q,
        page=page,
        page_size=page_size,
    )
    return await svc.list_templates(params, requesting_company_id=company_id)


@router.get("/{template_id}", response_model=TemplateDetail)
async def get_template(
    template_id: uuid.UUID,
    company_id: Optional[uuid.UUID] = Query(None, description="Requesting company ID"),
    svc: TemplateService = Depends(_get_service),
) -> TemplateDetail:
    """Fetch full template JSON by ID (GH#8260)."""
    try:
        return await svc.get(template_id, requesting_company_id=company_id)
    except TemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except TemplateAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/{template_id}/import", response_model=TemplateImportResult)
async def import_template(
    template_id: uuid.UUID,
    req: TemplateImportRequest,
    svc: TemplateService = Depends(_get_service),
) -> TemplateImportResult:
    """Import template into target company; resolves {{SECRET}} placeholders (GH#8260)."""
    try:
        result = await svc.import_template(template_id, req)
        await svc.session.commit()
        return result
    except TemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except TemplateAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    except TemplateSecretPlaceholderError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"message": "Unresolved secret placeholders", "unresolved": exc.unresolved},
        )


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_template(
    template_id: uuid.UUID,
    svc: TemplateService = Depends(_get_service),
) -> None:
    """Delete template from DB and ChromaDB collection (GH#8260)."""
    try:
        await svc.delete(template_id)
        await svc.session.commit()
    except TemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")


@router.get("/built-in", response_model=List[Dict])
async def list_built_in_templates() -> List[Dict]:
    """List all built-in company templates (GH#9042).

    Returns template metadata only (name, description, category, tags).
    Does not require authentication or database access.
    """
    return TemplateService.list_built_in_templates()


@router.get("/built-in/{template_key}", response_model=Dict)
async def get_built_in_template(template_key: str) -> Dict:
    """Fetch a specific built-in template by key (GH#9042).

    Args:
        template_key: Template identifier (e.g., 'software-team')

    Returns:
        Full template JSON including metadata, variables, agents, goals, work_items, kb_collections
    """
    try:
        return TemplateService.get_built_in_template(template_key)
    except BuiltInTemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error")
