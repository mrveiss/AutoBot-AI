# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read, set and clear a company's CEO designation (#15872).

`CompanyCEOService.set_ceo` and `.clear` existed and were reachable only from
service code. A company was provisioned with a default agent CEO and the org
chart resolved through it, but **an owner could not appoint a human CEO or
change the designation at all** -- through the API or the GUI. #15770's fourth
criterion ("designation changeable to a person") was met at the service layer
and genuinely satisfied as written; this is the gap between that and the feature
being usable.

WHY A SEPARATE MODULE, not three more routes in `companies.py`. That file is
grandfathered at exactly 1,780 lines and a grandfathered file may not grow
(#14236) -- the exemption freezes the size it was granted for. The prefix is
shared, so the routes appear at `/companies/{company_id}/ceo` either way.

WHAT THE ROUTES ADD OVER THE SERVICE is the tenant boundary. `set_ceo` already
refuses a holder from another company (`_require_in_company`, CWE-639), but
nothing stopped a caller naming a *company* that is not theirs -- the service
takes `company_id` as an argument and trusts it. `assert_company_access` is what
turns that argument into the caller's own company, and it 404s rather than 403s
so a cross-tenant caller cannot distinguish "not mine" from "does not exist".
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from autobot_shared.user_management.base_service import TenantContext
from llc.deps import assert_company_access, get_session
from llc.models.enums import RoleHolderType
from llc.services.company_ceo import CompanyCEOService

logger = get_logger(__name__)

router = APIRouter(prefix="/companies", tags=["llc-companies"])


class CEODesignationRead(BaseModel):
    """The designation as stored, plus whether it currently resolves.

    `holder_exists` is not redundant with `holder_id`. A designation can name a
    holder that has been deleted or has left the company, and the org chart
    treats that exactly like no designation at all -- so a UI reading only
    `holder_id` would show a CEO the chart does not render.
    """

    company_id: uuid.UUID
    holder_type: Optional[str] = None
    holder_id: Optional[uuid.UUID] = None
    holder_exists: bool


class CEODesignationWrite(BaseModel):
    holder_type: str = Field(..., description="'user' or 'agent'")
    holder_id: uuid.UUID


@router.get("/{company_id}/ceo", response_model=CEODesignationRead)
async def get_company_ceo(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CEODesignationRead:
    """The current designation, whether or not its holder still exists."""
    assert_company_access(ctx, company_id)

    svc = CompanyCEOService()
    row = await svc.designation(session, company_id)
    if row is None:
        return CEODesignationRead(company_id=company_id, holder_exists=False)

    resolved = await svc.resolve(session, company_id)
    return CEODesignationRead(
        company_id=company_id,
        holder_type=row.holder_type,
        holder_id=row.holder_id,
        holder_exists=resolved is not None,
    )


@router.put("/{company_id}/ceo", response_model=CEODesignationRead)
async def set_company_ceo(
    company_id: uuid.UUID,
    body: CEODesignationWrite,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> CEODesignationRead:
    """Designate a user or an agent as CEO, replacing any existing designation.

    PUT rather than POST: the position is single-valued and the write is
    idempotent -- setting the same holder twice leaves one row, which is what
    the unique constraint on `company_id` enforces anyway.

    422 rather than 404 for a holder outside the company. The company is the
    caller's own (`assert_company_access` has already run), so this is a
    well-formed request naming a holder that cannot hold the position -- a
    client-actionable condition, and one that says nothing about whether some
    other company's holder exists.
    """
    assert_company_access(ctx, company_id)

    svc = CompanyCEOService()
    try:
        row = await svc.set_ceo(session, company_id, body.holder_type, body.holder_id)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    holder_type, holder_id = row.holder_type, row.holder_id
    # Derived, not hardcoded `True`. `set_ceo` has just validated the holder via
    # `_require_in_company`, so this will be True -- but a field that means
    # "resolves now" in the GET response and "was valid at write time" here is a
    # field a client cannot interpret without knowing which route produced it.
    # One extra query buys one meaning.
    resolved = await svc.resolve(session, company_id)
    await session.commit()

    logger.info("CEO designation set for company %s: %s", company_id, holder_type)
    return CEODesignationRead(
        company_id=company_id,
        holder_type=holder_type,
        holder_id=holder_id,
        holder_exists=resolved is not None,
    )


@router.delete("/{company_id}/ceo", status_code=status.HTTP_204_NO_CONTENT)
async def clear_company_ceo(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    """Remove the designation. 404 when there was none.

    Distinguished on purpose: `clear` returns whether it removed anything, and
    collapsing that into an unconditional 204 would make "you cleared it" and
    "there was nothing there" indistinguishable to a caller retrying a failed
    request.
    """
    assert_company_access(ctx, company_id)

    removed = await CompanyCEOService().clear(session, company_id)
    if not removed:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No CEO designation for this company")
    await session.commit()


__all__ = ["CEODesignationRead", "CEODesignationWrite", "RoleHolderType", "router"]
