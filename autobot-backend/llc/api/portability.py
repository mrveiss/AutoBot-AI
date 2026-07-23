# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC Company Import API routes (GH#8246).

Route group: /llc/import
  POST /preview  — collision-detection preview (no writes)
  POST /execute  — transactional import
"""

import uuid
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.deps import assert_company_access
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
    # A target_company_id names an existing tenant to import into, so a
    # cross-tenant caller must be rejected. When None, the import creates a
    # brand-new company scoped to the caller, so only auth is required.
    if body.target_company_id is not None:
        assert_company_access(ctx, body.target_company_id)
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
    # See preview_import: target_company_id is optional (new-company import).
    if body.target_company_id is not None:
        assert_company_access(ctx, body.target_company_id)
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
