# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

from llc.services.portability import TemplateImportError as LLCImportError
from llc.services.portability import PortabilityService
from user_management.database import get_async_session

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
) -> ImportPreviewResponse:
    svc = PortabilityService(session=session)
    try:
        result = await svc.preview_import(body.template, target_company_id=body.target_company_id)
    except LLCImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
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
) -> ImportExecuteResponse:
    remapping = body.remapping_options.model_dump(exclude_none=True) if body.remapping_options else {}
    svc = PortabilityService(session=session)
    try:
        result = await svc.execute_import(
            body.template,
            target_company_id=body.target_company_id,
            remapping_options=remapping,
            secret_mapping=body.secret_mapping or {},
        )
    except LLCImportError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    await session.commit()
    return ImportExecuteResponse(**result)
