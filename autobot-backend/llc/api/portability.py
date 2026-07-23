# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC Company Import API routes (GH#8246).

Route group: /llc/import
  POST /preview  — collision-detection preview (no writes)
  POST /execute  — transactional import

Access control: both routes require an authenticated session. When
``target_company_id`` names an existing company, the caller's tenant
(``TenantContext.org_id``) must match it — platform admins are exempt — so an
authenticated caller of one company can't import agents/goals/secrets into a
different company (GH#12163, the IDOR fix). When ``target_company_id`` is
omitted the import creates a brand-new top-level company (there is no
existing tenant to check against), matching companies.py's ``create_company``.
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.services.portability import PortabilityService
from llc.services.portability import TemplateImportError as LLCImportError
from user_management.database import get_async_session
from user_management.services import TenantContext

router = APIRouter(prefix="/import", tags=["llc-import"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class ImportPreviewRequest(BaseModel):
    template: Dict[str, Any]
    target_company_id: Optional[uuid.UUID] = None


class ImportPreviewResponse(BaseModel):
    collisions: List[Dict[str, Any]]
    will_create: Dict[str, int]
    warnings: List[str]


class RemappingOptions(BaseModel):
    require_approval_for_hires: Optional[bool] = None


class ImportExecuteRequest(BaseModel):
    template: Dict[str, Any]
    target_company_id: Optional[uuid.UUID] = None
    remapping_options: Optional[RemappingOptions] = None
    secret_mapping: Optional[Dict[str, str]] = None


class ImportExecuteResponse(BaseModel):
    company_id: str
    created_entities: Dict[str, List[str]]
    skipped: Dict[str, List[str]]
    warnings: List[str]


# ---------------------------------------------------------------------------
# Auth / tenant isolation (GH#12163)
# ---------------------------------------------------------------------------


def _assert_import_target_access(ctx: TenantContext, target_company_id: Optional[uuid.UUID]) -> None:
    """Reject importing into a company the caller doesn't belong to.

    No-op when ``target_company_id`` is omitted (new-company import) — there
    is no existing tenant to check against. 404 (not 403) on mismatch, so a
    cross-tenant caller can't distinguish "not my company" from "doesn't
    exist" — matches goals.py/secrets.py (GH#12136, GH#12147). Platform
    admins are exempt.
    """
    if target_company_id is None:
        return
    if str(target_company_id) != str(ctx.org_id) and not ctx.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post(
    "/preview",
    response_model=ImportPreviewResponse,
    summary="Preview import collisions (no writes)",
)
async def preview_import(
    body: ImportPreviewRequest,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ImportPreviewResponse:
    _assert_import_target_access(ctx, body.target_company_id)
    svc = PortabilityService(session=session)
    try:
        result = await svc.preview_import(body.template, target_company_id=body.target_company_id)
    except LLCImportError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")
    return ImportPreviewResponse(**result)


@router.post(
    "/execute",
    response_model=ImportExecuteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Execute transactional company import",
)
async def execute_import(
    body: ImportExecuteRequest,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ImportExecuteResponse:
    _assert_import_target_access(ctx, body.target_company_id)
    remapping = body.remapping_options.model_dump(exclude_none=True) if body.remapping_options else {}
    svc = PortabilityService(session=session)
    try:
        result = await svc.execute_import(
            body.template,
            target_company_id=body.target_company_id,
            remapping_options=remapping,
            secret_mapping=body.secret_mapping or {},
        )
    except LLCImportError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Internal server error")
    await session.commit()
    return ImportExecuteResponse(**result)
