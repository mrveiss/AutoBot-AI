# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped workflow API routes (#14210).

Route group: /llc/workflows/{company_id}
  GET    /                  — list a company's workflows
  POST   /                  — create a workflow (durable identity only)
  GET    /{workflow_id}     — get one workflow
  PATCH  /{workflow_id}     — update a workflow's status
  DELETE /{workflow_id}     — delete a workflow row

Foundation only (per owner direction on #14210): this exposes the durable,
company-scoped ``workflows`` table for CRUD. It does not build process
nodes, canvas UI, or #13963's contextual entry — those are explicitly out of
scope here.

Scoping: the {company_id} path parameter is checked against the caller's
``TenantContext.org_id`` via ``assert_company_access`` (#12238), the same
shared guard every other LLC router uses (companies.py, contacts.py, ...).
Every read/write in this router goes through the table — no Redis or
in-memory fallback (#13916's consolidation rule: two implementations of one
thing become one reused core; this router is the first of the two, not a
third).

#14271: ``workflow_id`` is unique per-company, not globally, so create's
pre-check (``get()`` then ``create()``) is a UX nicety for the common case,
not the enforcement — a concurrent same-company duplicate still reaches the
DB's ``UNIQUE (company_id, workflow_id)`` constraint, which ``create()``
translates into ``WorkflowConflictError`` (caught here as 409) rather than
letting it surface as an unhandled 500.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import assert_company_access
from models.workflow import Workflow
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..services.authz import NotAuthorisedError
from ..services.company_os.errors import CompanyOsError
from ..services.company_os.loaders import is_company_os_row
from ..services.company_os.workflows import CompanyOsWorkflowService
from ..services.workflow import WorkflowConflictError, WorkflowService
from ._common import actor_id
from .company_os import http_error

router = APIRouter(prefix="/workflows", tags=["llc-workflows"])

_get_svc = lazy_singleton(WorkflowService)


def _svc() -> WorkflowService:
    return _get_svc()


_get_company_os = lazy_singleton(CompanyOsWorkflowService)


def _company_os() -> CompanyOsWorkflowService:
    return _get_company_os()


async def _is_company_os(session: AsyncSession, company_id: uuid.UUID, workflow_id: str) -> bool:
    """Re-load after the legacy write matched nothing: was it a Company OS row (#18446)?"""
    existing = await _svc().get(session, company_id, workflow_id)
    return existing is not None and is_company_os_row(existing)


async def _company_os_status(
    session: AsyncSession, company_id: uuid.UUID, workflow_id: str, new_status: str, actor: uuid.UUID
) -> Optional[Workflow]:
    """Re-dispatch a status change the legacy write refused, through the Company OS rules."""
    if not await _is_company_os(session, company_id, workflow_id):
        return None
    try:
        return await _company_os().update_status(session, company_id, workflow_id, new_status, actor=actor)
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc


# ------------------------------------------------------------------ Schemas


class WorkflowCreate(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=255)
    name: Optional[str] = Field(None, max_length=255)
    status: str = Field("planned", max_length=50)
    definition: Dict[str, Any] = Field(default_factory=dict)


class WorkflowStatusUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=50)


class WorkflowResponse(BaseModel):
    workflow_id: str
    company_id: uuid.UUID
    name: Optional[str]
    status: str
    source: str
    definition: Dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ------------------------------------------------------------------ Routes


@router.get("/{company_id}", response_model=List[WorkflowResponse])
async def list_workflows(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[WorkflowResponse]:
    assert_company_access(ctx, company_id)
    workflows = await _svc().list_by_company(session, company_id)
    return [WorkflowResponse.model_validate(w) for w in workflows]


@router.post("/{company_id}", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    company_id: uuid.UUID,
    body: WorkflowCreate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> WorkflowResponse:
    assert_company_access(ctx, company_id)
    existing = await _svc().get(session, company_id, body.workflow_id)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow already exists")
    try:
        workflow = await _svc().create(
            session,
            company_id,
            body.workflow_id,
            name=body.name,
            status=body.status,
            definition=body.definition,
            actor=actor_id(_current_user),
        )
    except WorkflowConflictError:
        # The pre-check above is TOCTOU under concurrency (#14271): a
        # same-company duplicate that raced past it still hits the DB's
        # UNIQUE(company_id, workflow_id) constraint, closing the race
        # rather than merely narrowing it.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow already exists")
    await session.commit()
    return WorkflowResponse.model_validate(workflow)


@router.get("/{company_id}/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    company_id: uuid.UUID,
    workflow_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> WorkflowResponse:
    assert_company_access(ctx, company_id)
    workflow = await _svc().get(session, company_id, workflow_id)
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return WorkflowResponse.model_validate(workflow)


@router.patch("/{company_id}/{workflow_id}", response_model=WorkflowResponse)
async def update_workflow_status(
    company_id: uuid.UUID,
    workflow_id: str,
    body: WorkflowStatusUpdate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> WorkflowResponse:
    assert_company_access(ctx, company_id)
    workflow = await _svc().update_status(session, company_id, workflow_id, body.status, actor=actor_id(_current_user))
    if workflow is None:
        workflow = await _company_os_status(session, company_id, workflow_id, body.status, actor_id(_current_user))
    if workflow is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    await session.commit()
    return WorkflowResponse.model_validate(workflow)


@router.delete("/{company_id}/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_workflow(
    company_id: uuid.UUID,
    workflow_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    assert_company_access(ctx, company_id)
    deleted = await _svc().delete(session, company_id, workflow_id, actor=actor_id(_current_user))
    if not deleted and await _is_company_os(session, company_id, workflow_id):
        try:
            await _company_os().delete(session, company_id, workflow_id, actor=actor_id(_current_user))
        except (CompanyOsError, NotAuthorisedError) as exc:
            raise http_error(exc) from exc
        deleted = True
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    await session.commit()
