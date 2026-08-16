# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company role routes — the reachable surface for #14221.

Route group: ``/llc/roles/{company_id}``

Steps 1-3 and 5 built services with no routes, which made every one of them
unreachable. This is that surface, so the Roles tab has something to call and
the services are wired rather than dormant.

Scoping is applied **twice on purpose**, and the redundancy is the point:

* :func:`assert_company_access` rejects a caller reaching outside their own
  company (404, so "not mine" is indistinguishable from "doesn't exist"), and
* every service query carries its own ``WHERE org_id`` / ``WHERE company_id``.

A route guard and a row filter fail in different ways, and a test exercising
only one cannot see the other — the gap this module has closed five separate
times (#13936, #13969, #13942, #14222, #14210).

``actor`` always comes from the authenticated session, never from the request
body. A client-supplied actor let the audit trail's identity be whatever the
caller typed (#13969 review M1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import assert_company_access
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..models.enums import RoleHolderType
from ..services.role import RoleService
from ..services.role_assignment import RoleAssignmentService
from ..services.authz import NotAuthorisedError
from ..services.role_permission import RolePermissionService
from ..services.role_workflow import RoleWorkflowService

router = APIRouter(prefix="/roles", tags=["llc-roles"])

_get_roles = lazy_singleton(RoleService)
_get_holders = lazy_singleton(RoleAssignmentService)
_get_permissions = lazy_singleton(RolePermissionService)
_get_workflows = lazy_singleton(RoleWorkflowService)

_NAME_MAX = 100  # matches Role.name = String(100)
_DESCRIPTION_MAX = 2000


def _actor_id(current_user: dict) -> uuid.UUID:
    """The acting user, from the session — never from the body or query."""
    raw = current_user.get("id") or current_user.get("user_id")
    return uuid.UUID(str(raw))


class RoleCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=_NAME_MAX)
    description: Optional[str] = Field(None, max_length=_DESCRIPTION_MAX)


class RoleUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=_NAME_MAX)
    description: Optional[str] = Field(None, max_length=_DESCRIPTION_MAX)


class RoleResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    description: Optional[str] = None
    is_system: bool = False


class HolderCreate(BaseModel):
    holder_type: RoleHolderType
    holder_id: uuid.UUID


class HolderResponse(BaseModel):
    id: uuid.UUID
    role_id: uuid.UUID
    holder_type: str
    holder_id: Optional[uuid.UUID] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None


class PermissionCreate(BaseModel):
    permission: str = Field(..., min_length=1, max_length=100)


class WorkflowAttach(BaseModel):
    workflow_id: str = Field(..., min_length=1, max_length=255)


def _as_role(role) -> RoleResponse:  # noqa: ANN001
    """``org_id`` is the company — see the service docstring for why they are one column."""
    return RoleResponse(
        id=role.id,
        company_id=role.org_id,
        name=role.name,
        description=role.description,
        is_system=bool(role.is_system),
    )


def _as_holder(assignment) -> HolderResponse:  # noqa: ANN001
    return HolderResponse(
        id=assignment.id,
        role_id=assignment.role_id,
        holder_type=assignment.holder_type,
        holder_id=assignment.holder_id,
        started_at=assignment.started_at,
        ended_at=assignment.ended_at,
    )


def _bad_request(exc: ValueError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


def _forbidden(exc: NotAuthorisedError) -> HTTPException:
    """403, distinct from 400.

    "You may not do this" and "what you asked makes no sense" are different
    answers, and collapsing them hides an authorisation failure behind what
    looks like a malformed request.
    """
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/{company_id}", response_model=List[RoleResponse])
async def list_roles(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[RoleResponse]:
    assert_company_access(ctx, company_id)
    return [_as_role(r) for r in await _get_roles().list_by_company(session, company_id)]


@router.post("/{company_id}", response_model=RoleResponse, status_code=status.HTTP_201_CREATED)
async def create_role(
    company_id: uuid.UUID,
    payload: RoleCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> RoleResponse:
    assert_company_access(ctx, company_id)
    try:
        role = await _get_roles().create(
            session,
            company_id=company_id,
            name=payload.name,
            description=payload.description,
            actor_user_id=_actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    await session.commit()
    return _as_role(role)


@router.patch("/{company_id}/{role_id}", response_model=RoleResponse)
async def update_role(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    payload: RoleUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> RoleResponse:
    assert_company_access(ctx, company_id)
    fields = payload.model_dump(exclude_unset=True)
    try:
        role = await _get_roles().update(session, company_id, role_id, actor_user_id=_actor_id(current_user), **fields)
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    await session.commit()
    return _as_role(role)


@router.delete("/{company_id}/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    assert_company_access(ctx, company_id)
    try:
        deleted = await _get_roles().delete(session, company_id, role_id, actor_user_id=_actor_id(current_user))
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    await session.commit()


@router.get("/{company_id}/{role_id}/holders", response_model=List[HolderResponse])
async def list_holders(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    include_past: bool = False,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[HolderResponse]:
    """Current holders, or the full tenure history when ``include_past`` is set."""
    assert_company_access(ctx, company_id)
    service = _get_holders()
    rows = (
        await service.history(session, company_id, role_id)
        if include_past
        else await service.current_holders(session, company_id, role_id)
    )
    return [_as_holder(row) for row in rows]


@router.post(
    "/{company_id}/{role_id}/holders",
    response_model=HolderResponse,
    status_code=status.HTTP_201_CREATED,
)
async def assign_holder(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    payload: HolderCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> HolderResponse:
    assert_company_access(ctx, company_id)
    try:
        assignment = await _get_holders().assign(
            session,
            company_id=company_id,
            role_id=role_id,
            holder_type=payload.holder_type,
            holder_id=payload.holder_id,
            actor_user_id=_actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    await session.commit()
    return _as_holder(assignment)


@router.delete("/{company_id}/{role_id}/holders/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def end_tenure(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    assignment_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Ends the tenure. The row survives — a DELETE here is not a row deletion."""
    assert_company_access(ctx, company_id)
    ended = await _get_holders().end_tenure(session, company_id, assignment_id, actor_user_id=_actor_id(current_user))
    if ended is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Open tenure not found")
    await session.commit()


@router.get("/{company_id}/{role_id}/permissions", response_model=List[str])
async def list_permissions(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[str]:
    assert_company_access(ctx, company_id)
    return await _get_permissions().list_for_role(session, company_id, role_id)


@router.post("/{company_id}/{role_id}/permissions", status_code=status.HTTP_204_NO_CONTENT)
async def grant_permission(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    payload: PermissionCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Admin-only — the service enforces it, so this route cannot forget to."""
    assert_company_access(ctx, company_id)
    try:
        await _get_permissions().grant(
            session,
            company_id=company_id,
            role_id=role_id,
            permission=payload.permission,
            actor_user_id=_actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    await session.commit()


@router.delete("/{company_id}/{role_id}/permissions/{permission}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_permission(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    permission: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    assert_company_access(ctx, company_id)
    try:
        revoked = await _get_permissions().revoke(
            session,
            company_id=company_id,
            role_id=role_id,
            permission=permission,
            actor_user_id=_actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    if not revoked:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Grant not found")
    await session.commit()


@router.get("/{company_id}/{role_id}/workflows", response_model=List[str])
async def list_role_workflows(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[str]:
    assert_company_access(ctx, company_id)
    attached = await _get_workflows().list_for_role(session, company_id, role_id)
    return [a.workflow_id for a in attached]


@router.post("/{company_id}/{role_id}/workflows", status_code=status.HTTP_204_NO_CONTENT)
async def attach_workflow(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    payload: WorkflowAttach,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    assert_company_access(ctx, company_id)
    try:
        await _get_workflows().attach(
            session,
            company_id=company_id,
            role_id=role_id,
            workflow_id=payload.workflow_id,
            actor_user_id=_actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    except ValueError as exc:
        raise _bad_request(exc) from exc
    await session.commit()


@router.delete("/{company_id}/{role_id}/workflows/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def detach_workflow(
    company_id: uuid.UUID,
    role_id: uuid.UUID,
    workflow_id: str,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    assert_company_access(ctx, company_id)
    try:
        detached = await _get_workflows().detach(
            session, company_id, role_id, workflow_id, actor_user_id=_actor_id(current_user)
        )
    except NotAuthorisedError as exc:
        raise _forbidden(exc) from exc
    if not detached:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    await session.commit()
