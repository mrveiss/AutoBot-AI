# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC template library API routes (GH#8260).

Route group: /llc/templates
  POST   /                     — publish a template
  GET    /                     — list templates (filter by category, tag, q)
  GET    /search               — RAG semantic search over platform:template_kb
  GET    /{template_id}        — fetch full template JSON
  POST   /{template_id}/import — import template into target company
  DELETE /{template_id}        — delete template + remove from ChromaDB

Auth / tenant isolation (GH#12148): every handler requires an authenticated
user. Company-scoped operations bind the requesting/owning company to the
caller's authenticated organization context rather than trusting a
caller-supplied ``company_id`` — a caller can no longer read, publish into,
import into, or delete templates on behalf of an arbitrary company. DELETE
additionally requires the caller's org to own the template (or platform admin).
"""

import uuid
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
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
from user_management.services import TenantContext

router = APIRouter(prefix="/templates", tags=["llc-templates"])


def _get_service(session: AsyncSession = Depends(get_async_session)) -> TemplateService:
    """DI factory — injects TemplateService with session."""
    return TemplateService(session=session)


def _assert_company_match(ctx: TenantContext, company_id: str) -> None:
    """Reject a caller-supplied company that isn't the caller's own org (GH#12148).

    Platform admins are exempt. 403 (not 404) here because the caller is
    asserting a company identity that isn't theirs — an authorization failure,
    not a lookup miss.
    """
    if company_id != str(ctx.org_id) and not ctx.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/", response_model=TemplateDetail, status_code=status.HTTP_201_CREATED)
async def publish_template(
    req: TemplatePublishRequest,
    company_id: Optional[uuid.UUID] = Query(None, description="Owning company ID"),
    svc: TemplateService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> TemplateDetail:
    """Publish a scrubbed company export as a reusable template (GH#8260).

    The template is owned by the caller's authenticated organization; a
    caller-supplied ``company_id`` must match it (GH#12148).
    """
    if company_id is not None:
        _assert_company_match(ctx, str(company_id))
    try:
        result = await svc.publish(req, company_id=ctx.org_id)
        await svc.session.commit()
        return result
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")


@router.get("/search", response_model=TemplateSearchResponse)
async def search_templates(
    q: str = Query(..., min_length=1, description="Semantic search query"),
    svc: TemplateService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
) -> TemplateSearchResponse:
    """RAG search over platform:template_kb ChromaDB collection (GH#8260).

    Returns platform-level template metadata only; requires authentication
    (GH#12148).
    """
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[TemplateRead]:
    """List templates visible to the caller's organization (GH#8260).

    Private-template visibility is scoped to the authenticated org; a
    caller-supplied ``company_id`` must match it (GH#12148).
    """
    if company_id is not None:
        _assert_company_match(ctx, str(company_id))
    params = TemplateListParams(
        category=category,
        tag=tag,
        q=q,
        page=page,
        page_size=page_size,
    )
    return await svc.list_templates(params, requesting_company_id=ctx.org_id)


# Static /built-in routes MUST be declared before the dynamic /{template_id}
# route: FastAPI matches in definition order, so a {template_id: uuid} above
# would swallow GET /built-in and 422 on UUID parsing of "built-in" (GH#9042).
@router.get("/built-in", response_model=List[Dict])
async def list_built_in_templates(
    _current_user: dict = Depends(get_current_user),
) -> List[Dict]:
    """List all built-in company templates (GH#9042).

    Returns template metadata only (name, description, category, tags).
    Requires authentication (GH#12148).
    """
    return TemplateService.list_built_in_templates()


@router.get("/built-in/{template_key}", response_model=Dict)
async def get_built_in_template(
    template_key: str,
    _current_user: dict = Depends(get_current_user),
) -> Dict:
    """Fetch a specific built-in template by key (GH#9042).

    Args:
        template_key: Template identifier (e.g., 'software-team')

    Returns:
        Full template JSON including metadata, variables, agents, goals, work_items, kb_collections
    """
    try:
        return TemplateService.get_built_in_template(template_key)
    except BuiltInTemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Built-in template not found")


@router.get("/{template_id}", response_model=TemplateDetail)
async def get_template(
    template_id: uuid.UUID,
    company_id: Optional[uuid.UUID] = Query(None, description="Requesting company ID"),
    svc: TemplateService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> TemplateDetail:
    """Fetch full template JSON by ID (GH#8260).

    Access is evaluated against the caller's authenticated org; a
    caller-supplied ``company_id`` must match it (GH#12148).
    """
    if company_id is not None:
        _assert_company_match(ctx, str(company_id))
    try:
        return await svc.get(template_id, requesting_company_id=ctx.org_id)
    except TemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except TemplateAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")


@router.post("/{template_id}/import", response_model=TemplateImportResult)
async def import_template(
    template_id: uuid.UUID,
    req: TemplateImportRequest,
    svc: TemplateService = Depends(_get_service),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> TemplateImportResult:
    """Import template into target company; resolves {{SECRET}} placeholders (GH#8260).

    The import target must be the caller's authenticated org (GH#12148).
    """
    _assert_company_match(ctx, str(req.target_company_id))
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
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Delete template from DB and ChromaDB collection (GH#8260).

    Only the owning organization (or a platform admin) may delete a template
    (GH#12148).
    """
    try:
        detail = await svc.get(template_id, requesting_company_id=ctx.org_id)
    except TemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    except TemplateAccessError:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if not ctx.is_platform_admin and str(detail.created_by_company_id) != str(ctx.org_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        await svc.delete(template_id)
        await svc.session.commit()
    except TemplateNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
