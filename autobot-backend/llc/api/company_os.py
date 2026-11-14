# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company OS model API: roles -> workflows -> processes (#18390).

Route group: /llc/company-os
  /processes[/{process_key}]              reusable processes, one owner role each
  /workflows[/{workflow_id}]              role-owned workflows and meta skills
  /workflows/{workflow_id}/graph          the process graph (GET, PUT whole)
  /workflows/{workflow_id}/graph/validate dry-run a graph without storing it
  /workflows/{workflow_id}/validation     errors and warnings of the stored graph
  /roles/{role_id}/skills                 skills held, transitively, with sources

Tenancy comes from the authenticated org context (``require_org_context``) and
nowhere else: no route takes a company id, so there is nothing for a caller to
point at another company. Reads need membership of the org context; every write is
gated on company owner/admin inside the service. An id from another company is a
404, never a 403, so it cannot be told apart from one that does not exist.
This is the data model and its read/write API only -- nothing here executes a
workflow, a trigger or a handoff.
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.deps import get_session
from llc.models.company_os_enums import WorkflowKind
from llc.services.authz import NotAuthorisedError
from llc.services.company_os.errors import CompanyOsConflict, CompanyOsError, CompanyOsNotFound, GraphInvalid
from llc.services.company_os.graph_types import GraphSpec
from llc.services.company_os.graphs import GraphService
from llc.services.company_os.processes import ProcessService
from llc.services.company_os.workflows import CompanyOsWorkflowService
from user_management.services import TenantContext

from ._common import actor_id
from .company_os_schemas import (
    CompanyWorkflowCreate,
    CompanyWorkflowResponse,
    CompanyWorkflowUpdate,
    GraphResponse,
    GraphValidation,
    ProcessCreate,
    ProcessResponse,
    ProcessUpdate,
)

router = APIRouter(prefix="/company-os", tags=["llc-company-os"])

_processes = ProcessService()
_workflows = CompanyOsWorkflowService()
_graphs = GraphService()


def http_error(exc: Exception) -> HTTPException:
    """Map a service error to its status: 404 / 409 / 422 / 403 / 400."""
    if isinstance(exc, NotAuthorisedError):
        return HTTPException(status.HTTP_403_FORBIDDEN, detail=str(exc))
    if isinstance(exc, CompanyOsNotFound):
        return HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))
    if isinstance(exc, CompanyOsConflict):
        return HTTPException(status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, GraphInvalid):
        return HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": exc.errors})
    if isinstance(exc, CompanyOsError):
        return HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(exc))
    raise exc


# ----------------------------------------------------------------- processes


@router.get("/processes", response_model=List[ProcessResponse])
async def list_processes(
    owner_role_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[ProcessResponse]:
    rows = await _processes.list(session, ctx.org_id, owner_role_id)
    return [ProcessResponse.model_validate(r) for r in rows]


@router.post("/processes", response_model=ProcessResponse, status_code=status.HTTP_201_CREATED)
async def create_process(
    body: ProcessCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ProcessResponse:
    try:
        row = await _processes.create(session, ctx.org_id, actor=actor_id(user), **body.model_dump())
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()
    return ProcessResponse.model_validate(row)


@router.get("/processes/{process_key}", response_model=ProcessResponse)
async def get_process(
    process_key: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ProcessResponse:
    try:
        return ProcessResponse.model_validate(await _processes.get(session, ctx.org_id, process_key))
    except CompanyOsError as exc:
        raise http_error(exc) from exc


@router.patch("/processes/{process_key}", response_model=ProcessResponse)
async def update_process(
    process_key: str,
    body: ProcessUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ProcessResponse:
    try:
        row = await _processes.update(
            session, ctx.org_id, process_key, actor=actor_id(user), **body.model_dump(exclude_unset=True)
        )
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()
    return ProcessResponse.model_validate(row)


@router.delete("/processes/{process_key}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_process(
    process_key: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    try:
        await _processes.delete(session, ctx.org_id, process_key, actor=actor_id(user))
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()


# ----------------------------------------------------------------- workflows


@router.get("/workflows", response_model=List[CompanyWorkflowResponse])
async def list_workflows(
    kind: Optional[WorkflowKind] = None,
    owner_role_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[CompanyWorkflowResponse]:
    rows = await _workflows.list(session, ctx.org_id, kind=kind.value if kind else None, owner_role_id=owner_role_id)
    return [CompanyWorkflowResponse.model_validate(r) for r in rows]


@router.post("/workflows", response_model=CompanyWorkflowResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    body: CompanyWorkflowCreate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowResponse:
    data = body.model_dump()
    data["kind"] = body.kind.value
    try:
        row = await _workflows.create(session, ctx.org_id, actor=actor_id(user), **data)
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()
    return CompanyWorkflowResponse.model_validate(row)


@router.get("/workflows/{workflow_id}", response_model=CompanyWorkflowResponse)
async def get_workflow(
    workflow_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowResponse:
    try:
        return CompanyWorkflowResponse.model_validate(await _workflows.get(session, ctx.org_id, workflow_id))
    except CompanyOsError as exc:
        raise http_error(exc) from exc


@router.patch("/workflows/{workflow_id}", response_model=CompanyWorkflowResponse)
async def update_workflow(
    workflow_id: str,
    body: CompanyWorkflowUpdate,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CompanyWorkflowResponse:
    try:
        row = await _workflows.update(
            session, ctx.org_id, workflow_id, actor=actor_id(user), **body.model_dump(exclude_unset=True)
        )
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()
    return CompanyWorkflowResponse.model_validate(row)


@router.delete("/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def delete_workflow(
    workflow_id: str,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    try:
        await _workflows.delete(session, ctx.org_id, workflow_id, actor=actor_id(user))
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()


# -------------------------------------------------------------------- graphs


@router.get("/workflows/{workflow_id}/graph", response_model=GraphResponse)
async def get_graph(
    workflow_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GraphResponse:
    try:
        spec = await _graphs.get(session, ctx.org_id, workflow_id)
        report = await _graphs.validate_spec(session, ctx.org_id, workflow_id, spec)
    except CompanyOsError as exc:
        raise http_error(exc) from exc
    return GraphResponse(graph=spec, validation=GraphValidation(errors=report.errors, warnings=report.warnings))


@router.put("/workflows/{workflow_id}/graph", response_model=GraphResponse)
async def put_graph(
    workflow_id: str,
    body: GraphSpec,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GraphResponse:
    try:
        report = await _graphs.replace(session, ctx.org_id, workflow_id, body, actor=actor_id(user))
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()
    return GraphResponse(graph=body, validation=GraphValidation(errors=[], warnings=report.warnings))


@router.post("/workflows/{workflow_id}/graph/validate", response_model=GraphValidation)
async def validate_graph_body(
    workflow_id: str,
    body: GraphSpec,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GraphValidation:
    try:
        report = await _graphs.validate_spec(session, ctx.org_id, workflow_id, body)
    except CompanyOsError as exc:
        raise http_error(exc) from exc
    return GraphValidation(errors=report.errors, warnings=report.warnings)


@router.get("/workflows/{workflow_id}/validation", response_model=GraphValidation)
async def validate_stored_graph(
    workflow_id: str,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GraphValidation:
    try:
        report = await _graphs.validate_stored(session, ctx.org_id, workflow_id)
    except CompanyOsError as exc:
        raise http_error(exc) from exc
    return GraphValidation(errors=report.errors, warnings=report.warnings)
