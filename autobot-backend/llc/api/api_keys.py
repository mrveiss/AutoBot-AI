# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC API key management routes (GH#8218).

Routes:
  POST   /agents/{agent_id}/api-keys
  DELETE /agents/{agent_id}/api-keys/{key_id}
  GET    /agents/{agent_id}/api-keys
"""

import uuid
from typing import Any, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.logging_manager import get_logger
from llc.models.api_key import LLCApiKey
from llc.services.api_key import ApiKeyService
from user_management.database import get_async_session
from user_management.services import TenantContext

logger = get_logger(__name__)
router = APIRouter(prefix="/agents", tags=["llc-api-keys"])
_svc = ApiKeyService()


class ApiKeyCreate(BaseModel):
    name: str
    # #13771: the key's company comes from the caller's tenant context. Kept
    # optional for compatibility with existing clients, and honoured only as an
    # assertion — a value naming another company is refused, never applied.
    company_id: Optional[str] = None


class ApiKeyRead(BaseModel):
    id: uuid.UUID
    agent_id: str
    company_id: str
    name: str
    last_used_at: Optional[Any] = None
    revoked_at: Optional[Any] = None
    created_at: Any

    model_config = {"from_attributes": True}


class ApiKeyCreated(ApiKeyRead):
    plaintext: str


@router.post("/{agent_id}/api-keys", response_model=ApiKeyCreated, status_code=201)
async def create_api_key(
    agent_id: str,
    body: ApiKeyCreate,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ApiKeyCreated:
    # #13771: the company a key is minted for is the caller's, never the body's.
    # ``company_id`` stays in the payload for compatibility, but only as an
    # assertion — naming another company is refused, not silently honoured.
    company_id = str(ctx.org_id)
    if body.company_id and str(body.company_id) != company_id:
        raise HTTPException(status_code=403, detail="Cannot issue an API key for another company")
    record, plaintext = await _svc.issue_key(session, agent_id=agent_id, company_id=company_id, name=body.name)
    return ApiKeyCreated(
        id=record.id,
        agent_id=record.agent_id,
        company_id=record.company_id,
        name=record.name,
        last_used_at=record.last_used_at,
        revoked_at=record.revoked_at,
        created_at=record.created_at,
        plaintext=plaintext,
    )


@router.delete("/{agent_id}/api-keys/{key_id}", status_code=204)
async def revoke_api_key(
    agent_id: str,
    key_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    try:
        await _svc.revoke_key(session, agent_id=agent_id, key_id=key_id, company_id=str(ctx.org_id))
    except KeyError as exc:
        logger.error("Exception in API handler: %s", exc, exc_info=True)
        raise HTTPException(status_code=404, detail="Internal server error") from exc


@router.get("/{agent_id}/api-keys", response_model=List[ApiKeyRead])
async def list_api_keys(
    agent_id: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[ApiKeyRead]:
    result = await session.execute(
        select(LLCApiKey).where(
            LLCApiKey.agent_id == agent_id,
            LLCApiKey.company_id == str(ctx.org_id),  # #13771
        )
    )
    return [ApiKeyRead.model_validate(r) for r in result.scalars().all()]
