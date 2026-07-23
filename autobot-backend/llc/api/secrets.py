# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company-scoped secrets API routes (GH#8217).

Route group: /llc/secrets/{company_id}
  GET    /                   — list secret names and versions (no values)
  POST   /                   — set (create or update) a secret
  GET    /{name}             — get decrypted value for a named secret
  DELETE /{name}             — revoke a secret

Access control: the caller must present a valid authenticated session whose
tenant (`TenantContext.org_id`) matches the {company_id} path parameter
(GH#12147); platform admins are exempt. Values are NEVER returned in list
responses.
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.models.secret import LLCSecret
from llc.services.secret import SecretNotFound, SecretService
from user_management.database import get_async_session
from user_management.services import TenantContext

router = APIRouter(prefix="/secrets", tags=["llc-secrets"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------


class SecretSetRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    value: str = Field(..., min_length=1)
    actor: str = Field(..., description="Agent ID performing the operation")


class SecretSummary(BaseModel):
    name: str
    version: int
    created_by_agent_id: str
    created_at: datetime
    updated_at: datetime
    revoked_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class SecretSetResponse(BaseModel):
    name: str
    version: int
    company_id: str


class SecretValueResponse(BaseModel):
    name: str
    version: int
    value: str


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def _get_service() -> SecretService:
    return SecretService()


def _check_company_access(
    company_id: str,
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> str:
    """Verify the authenticated caller belongs to the requested company (GH#12147).

    Tenant is derived server-side from the validated JWT/session
    (``require_org_context``), never from a client-supplied header. Returns
    the validated company_id. Raises HTTP 404 (not 403) on mismatch so a
    cross-tenant caller can't distinguish "not my company" from "doesn't
    exist" — matches the goals.py/companies.py idiom (GH#12136). Platform
    admins are exempt.
    """
    if str(company_id) != str(ctx.org_id) and not ctx.is_platform_admin:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return company_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/{company_id}", response_model=List[SecretSummary])
async def list_secrets(
    company_id: str = Depends(_check_company_access),
    session: AsyncSession = Depends(get_async_session),
    svc: SecretService = Depends(_get_service),
) -> List[SecretSummary]:
    """List secret names and versions.  Values are never included."""
    entries = await svc.list(session, company_id)
    return [SecretSummary(**e) for e in entries]


@router.post(
    "/{company_id}",
    response_model=SecretSetResponse,
    status_code=status.HTTP_201_CREATED,
)
async def set_secret(
    body: SecretSetRequest,
    company_id: str = Depends(_check_company_access),
    session: AsyncSession = Depends(get_async_session),
    svc: SecretService = Depends(_get_service),
) -> SecretSetResponse:
    """Create or update a secret.  Version increments on update."""
    secret = await svc.set(
        session=session,
        company_id=company_id,
        name=body.name,
        value=body.value,
        actor=body.actor,
    )
    await session.commit()
    return SecretSetResponse(
        name=secret.name,
        version=secret.version,
        company_id=secret.company_id,
    )


@router.get("/{company_id}/{name}", response_model=SecretValueResponse)
async def get_secret(
    name: str,
    company_id: str = Depends(_check_company_access),
    session: AsyncSession = Depends(get_async_session),
    svc: SecretService = Depends(_get_service),
) -> SecretValueResponse:
    """Return the decrypted plaintext value for a named secret."""
    try:
        plaintext = await svc.get(session=session, company_id=company_id, name=name)
    except SecretNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error") from exc

    result = await session.execute(
        select(LLCSecret).where(
            LLCSecret.company_id == company_id,
            LLCSecret.name == name,
        )
    )
    row = result.scalar_one()
    return SecretValueResponse(name=row.name, version=row.version, value=plaintext)


@router.delete("/{company_id}/{name}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_secret(
    name: str,
    actor: str,
    company_id: str = Depends(_check_company_access),
    session: AsyncSession = Depends(get_async_session),
    svc: SecretService = Depends(_get_service),
) -> None:
    """Revoke a secret.  The value becomes permanently inaccessible."""
    try:
        await svc.revoke(session=session, company_id=company_id, name=name, actor=actor)
    except SecretNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal server error") from exc
    await session.commit()
