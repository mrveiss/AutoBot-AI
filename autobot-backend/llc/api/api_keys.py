# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

from llc.models.api_key import LLCApiKey
from llc.services.api_key import ApiKeyService
from user_management.database import get_async_session

router = APIRouter(prefix="/agents", tags=["llc-api-keys"])
_svc = ApiKeyService()


class ApiKeyCreate(BaseModel):
    name: str
    company_id: str


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
) -> ApiKeyCreated:
    record, plaintext = await _svc.issue_key(session, agent_id=agent_id, company_id=body.company_id, name=body.name)
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
) -> None:
    try:
        await _svc.revoke_key(session, agent_id=agent_id, key_id=key_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{agent_id}/api-keys", response_model=List[ApiKeyRead])
async def list_api_keys(
    agent_id: str,
    session: AsyncSession = Depends(get_async_session),
) -> List[ApiKeyRead]:
    result = await session.execute(select(LLCApiKey).where(LLCApiKey.agent_id == agent_id))
    return [ApiKeyRead.model_validate(r) for r in result.scalars().all()]
