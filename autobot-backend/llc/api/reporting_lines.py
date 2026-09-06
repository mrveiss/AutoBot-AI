# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Reporting-line routes (#15763).

Route group: ``/llc/reporting-lines/{company_id}``

The reachable surface for :class:`ReportingLineService`. A service with no route
is the defect this module has shipped four times (#14221 steps 1-3 and 5): the
code exists, every unit test passes, and nothing can call it.

**The write gate is a declared route dependency, deliberately.** Changing a
reporting line is not ordinary data editing — the hierarchy is an authorization
input (#15765), so re-parenting someone hands their new manager edit rights over
them and, at depth two, over everyone that manager manages. A reader asking
"what does it take to do that?" must get the answer from the route, and a gate
called inside a handler body never enters the ``Dependant`` tree: #15743's fix
closed its hole while the posture suite kept reporting the route as merely
authenticated, precisely because the check sat in a function body (#15737).

That is why this differs from the rest of this surface, where the gate lives in
the service (``CompanyToolService.upsert``, every role route). Those guard
company *data*, and a service-layer check holding for every caller is the right
property. This guards the authorization graph itself, and a check that cannot be
read from the route is a check nobody can audit.

The gate is ``require_reporting_line_write`` — the ``admin.reporting_line.write``
permission (#15793). It replaced a deliberately narrower placeholder that was
declared here from the first commit: a route gated in the service and
"promoted" later spends the interval reading as unguarded to anything that
inspects routes, which is the state #15737 documents. Because the placeholder
was declared rather than called, the swap was one line at each decorator and
``test_the_write_gate_is_a_declared_dependency`` held across it.

The permission is deliberately unable to see hierarchy data: its dependency
takes only the tenant context and the current user — no subject id — so a later
edit cannot make it consult the very graph it guards without first changing a
signature that fails loudly.

"No session" was claimed here too and was overstated (#15805): the dependency
declares no session parameter, but ``context`` used to reach one transitively
through ``get_tenant_context``. The permission is now decided from the JWT alone
before that context resolves, so the refusal costs no session — but the property
that closes the escalation is the absent subject id, not the absent session.
"""

from __future__ import annotations

import uuid
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import (
    get_current_user,
    require_org_context,
    require_reporting_line_write,
)
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import assert_company_access
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..models.enums import RoleHolderType
from ..services.authz import NotAuthorisedError
from ..services.reporting_line import Holder, ReportingLineService
from ._common import actor_id, bad_request, forbidden

router = APIRouter(prefix="/reporting-lines", tags=["llc-reporting-lines"])

_get_lines = lazy_singleton(ReportingLineService)

_HOLDER_TYPES = (RoleHolderType.USER.value, RoleHolderType.AGENT.value)


class HolderRef(BaseModel):
    """One end of a reporting edge."""

    type: str = Field(..., description="user or agent")
    id: uuid.UUID


class ReportingLineWrite(BaseModel):
    manager: HolderRef


class ChainResponse(BaseModel):
    """The upward walk from one subject, and why it stopped."""

    managers: List[HolderRef]
    #: ``owner`` / ``depth`` / ``cycle`` / ``no_ceo``. Carried because a walk
    #: that ran out of edges with no CEO to fall back on is indistinguishable
    #: from one that reached the top unless the reason travels with it.
    ended: str


def _holder(ref: HolderRef) -> Holder:
    if ref.type not in _HOLDER_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"holder type must be one of {list(_HOLDER_TYPES)}",
        )
    return Holder(type=ref.type, id=ref.id)


def _ref(holder: Holder) -> HolderRef:
    return HolderRef(type=holder.type, id=holder.id)


@router.get("/{company_id}/{subject_type}/{subject_id}", response_model=ChainResponse)
async def get_chain(
    company_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ChainResponse:
    """Who this subject reports to, walking up to the bounded depth."""
    assert_company_access(ctx, company_id)
    subject = _holder(HolderRef(type=subject_type, id=subject_id))
    chain = await _get_lines().chain_up(session, company_id, subject)
    return ChainResponse(managers=[_ref(h) for h in chain.managers], ended=chain.ended.value)


@router.get("/{company_id}/{subject_type}/{subject_id}/reports", response_model=List[HolderRef])
async def get_direct_reports(
    company_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[HolderRef]:
    """Who reports to this holder — derived from the stored edge, never stored."""
    assert_company_access(ctx, company_id)
    manager = _holder(HolderRef(type=subject_type, id=subject_id))
    return [_ref(h) for h in await _get_lines().direct_reports(session, company_id, manager)]


@router.put(
    "/{company_id}/{subject_type}/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_reporting_line_write)],
)
async def set_reporting_line(
    company_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    payload: ReportingLineWrite,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    assert_company_access(ctx, company_id)
    try:
        await _get_lines().set_line(
            session,
            company_id=company_id,
            subject=_holder(HolderRef(type=subject_type, id=subject_id)),
            manager=_holder(payload.manager),
            actor_user_id=actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise forbidden(exc) from exc
    except ValueError as exc:
        raise bad_request(exc) from exc
    await session.commit()


@router.delete(
    "/{company_id}/{subject_type}/{subject_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_reporting_line_write)],
)
async def clear_reporting_line(
    company_id: uuid.UUID,
    subject_type: str,
    subject_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Clearing returns the subject to the default chain, it does not orphan them."""
    assert_company_access(ctx, company_id)
    try:
        removed = await _get_lines().clear_line(
            session,
            company_id=company_id,
            subject=_holder(HolderRef(type=subject_type, id=subject_id)),
            actor_user_id=actor_id(current_user),
        )
    except NotAuthorisedError as exc:
        raise forbidden(exc) from exc
    if not removed:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No reporting line to clear")
    await session.commit()
