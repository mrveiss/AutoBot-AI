# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC per-agent knowledge wiki API (GH#9021).

Routes (user-facing, require org auth):
  GET    /llc/agents/{agent_id}/wiki/entries
  POST   /llc/agents/{agent_id}/wiki/entries
  GET    /llc/agents/{agent_id}/wiki/entries/{entry_id}
  PUT    /llc/agents/{agent_id}/wiki/entries/{entry_id}
  DELETE /llc/agents/{agent_id}/wiki/entries/{entry_id}

Routes (agent-facing, require LLC bearer token — served from agent_api.py):
  GET    /llc/agent/wiki/entries
  POST   /llc/agent/wiki/entries
"""

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..services.agent_wiki_service import AgentWikiService

router = APIRouter(prefix="/agents", tags=["llc-agent-wiki"])

_svc = AgentWikiService()


class WikiEntryCreate(BaseModel):
    namespace: str = Field(default="general", max_length=128)
    key: str = Field(..., max_length=256)
    title: str = Field(..., max_length=512)
    body: str = Field(default="")


class WikiEntryUpdate(BaseModel):
    namespace: Optional[str] = Field(default=None, max_length=128)
    key: Optional[str] = Field(default=None, max_length=256)
    title: Optional[str] = Field(default=None, max_length=512)
    body: Optional[str] = None


class WikiEntryRead(BaseModel):
    id: uuid.UUID
    agent_id: str
    company_id: uuid.UUID
    namespace: str
    key: str
    title: str
    body: str
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}

    @classmethod
    def from_orm_entry(cls, e) -> "WikiEntryRead":
        return cls(
            id=e.id,
            agent_id=e.agent_id,
            company_id=e.company_id,
            namespace=e.namespace,
            key=e.key,
            title=e.title,
            body=e.body,
            created_at=e.created_at.isoformat(),
            updated_at=e.updated_at.isoformat(),
        )


@router.get("/{agent_id}/wiki/entries", response_model=List[WikiEntryRead])
async def list_wiki_entries(
    agent_id: str,
    namespace: Optional[str] = None,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[WikiEntryRead]:
    entries = await _svc.list_entries(session, agent_id, ctx.org_id, namespace)
    return [WikiEntryRead.from_orm_entry(e) for e in entries]


@router.post("/{agent_id}/wiki/entries", response_model=WikiEntryRead, status_code=201)
async def create_wiki_entry(
    agent_id: str,
    body: WikiEntryCreate,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> WikiEntryRead:
    try:
        entry = await _svc.create_entry(
            session,
            agent_id=agent_id,
            company_id=ctx.org_id,
            namespace=body.namespace,
            key=body.key,
            title=body.title,
            body=body.body,
        )
        await session.commit()
        return WikiEntryRead.from_orm_entry(entry)
    except Exception as exc:
        await session.rollback()
        if "uq_agent_wiki_agent_ns_key" in str(exc):
            raise HTTPException(status_code=409, detail="Wiki entry with this namespace/key already exists")
        raise


@router.get("/{agent_id}/wiki/entries/{entry_id}", response_model=WikiEntryRead)
async def get_wiki_entry(
    agent_id: str,
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> WikiEntryRead:
    entry = await _svc.get_entry(session, entry_id, agent_id, ctx.org_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Wiki entry not found")
    return WikiEntryRead.from_orm_entry(entry)


@router.put("/{agent_id}/wiki/entries/{entry_id}", response_model=WikiEntryRead)
async def update_wiki_entry(
    agent_id: str,
    entry_id: uuid.UUID,
    body: WikiEntryUpdate,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> WikiEntryRead:
    entry = await _svc.get_entry(session, entry_id, agent_id, ctx.org_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Wiki entry not found")
    updated = await _svc.update_entry(
        session,
        entry,
        title=body.title,
        body=body.body,
        namespace=body.namespace,
        key=body.key,
    )
    await session.commit()
    return WikiEntryRead.from_orm_entry(updated)


@router.delete("/{agent_id}/wiki/entries/{entry_id}", status_code=204, response_model=None)
async def delete_wiki_entry(
    agent_id: str,
    entry_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    entry = await _svc.get_entry(session, entry_id, agent_id, ctx.org_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="Wiki entry not found")
    await _svc.delete_entry(session, entry)
    await session.commit()
