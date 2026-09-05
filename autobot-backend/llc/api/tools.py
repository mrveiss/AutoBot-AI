# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company tool catalogue routes (#14852).

Route group: ``/llc/tools/{company_id}``

Three reads and one write over :class:`CompanyToolService`. The catalogue is
driven by the tool registry and carries this company's own URL and logo where
they have been recorded; ``usage`` answers "which roles carry this tool, and
which workflows do those roles run", which was previously only answerable by
scanning every role.

Scoping is applied twice, deliberately, as everywhere else on this surface:
:func:`assert_company_access` rejects a caller reaching outside their own
company, and every service query carries its own ``WHERE company_id``. A route
guard and a row filter fail in different ways, and a test exercising one cannot
see the other.

``actor`` always comes from the authenticated session, never the request body.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from autobot_shared.singleton_factory import lazy_singleton
from llc.deps import assert_company_access
from user_management.database import get_async_session
from user_management.services import TenantContext

from ..models.company_tool import URL_LENGTH
from ..services.authz import NotAuthorisedError
from ..services.company_tool import CompanyToolService
from ..services.tool_registry_ref import ToolRegistryUnavailable
from ._common import actor_id, bad_request, forbidden, registry_unavailable

router = APIRouter(prefix="/tools", tags=["llc-tools"])

_get_tools = lazy_singleton(CompanyToolService)


class ToolCatalogueEntry(BaseModel):
    """One tool: registry identity, this company's facts, and its reach."""

    name: str
    description: str
    #: The registry's ``tags``. This is the grouping — #14852 asked for a
    #: ``group`` field and the registry already documents tags as exactly that.
    tags: List[str]
    url: Optional[str] = None
    logo_url: Optional[str] = None
    role_count: int


class ToolUsage(BaseModel):
    """Which roles carry a tool, and which workflows those roles run."""

    role_ids: List[str]
    workflow_ids: List[str]


class ToolOverlayUpdate(BaseModel):
    """This company's own facts about a tool. Both optional, both clearable."""

    url: Optional[str] = Field(default=None, max_length=URL_LENGTH)
    logo_url: Optional[str] = Field(default=None, max_length=URL_LENGTH)


@router.get("/{company_id}", response_model=List[ToolCatalogueEntry])
async def list_tools(
    company_id: uuid.UUID,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> List[ToolCatalogueEntry]:
    assert_company_access(ctx, company_id)
    try:
        entries = await _get_tools().catalogue(session, company_id)
    except ToolRegistryUnavailable as exc:
        raise registry_unavailable(exc) from exc
    return [
        ToolCatalogueEntry(
            name=entry.name,
            description=entry.description,
            tags=list(entry.tags),
            url=entry.url,
            logo_url=entry.logo_url,
            role_count=entry.role_count,
        )
        for entry in entries
    ]


@router.get("/{company_id}/{tool_name}/usage", response_model=ToolUsage)
async def tool_usage(
    company_id: uuid.UUID,
    tool_name: str,
    session: AsyncSession = Depends(get_async_session),
    _current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ToolUsage:
    assert_company_access(ctx, company_id)
    usage = await _get_tools().usage(session, company_id, tool_name)
    return ToolUsage(role_ids=usage["role_ids"], workflow_ids=usage["workflow_ids"])


@router.put("/{company_id}/{tool_name}", response_model=ToolCatalogueEntry)
async def upsert_tool_overlay(
    company_id: uuid.UUID,
    tool_name: str,
    payload: ToolOverlayUpdate,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> ToolCatalogueEntry:
    assert_company_access(ctx, company_id)
    try:
        await _get_tools().upsert(
            session,
            company_id=company_id,
            tool_name=tool_name,
            url=payload.url,
            logo_url=payload.logo_url,
            actor_user_id=actor_id(current_user),
        )
        await session.commit()
        entries = await _get_tools().catalogue(session, company_id)
    except ToolRegistryUnavailable as exc:
        raise registry_unavailable(exc) from exc
    except NotAuthorisedError as exc:
        raise forbidden(exc) from exc
    except ValueError as exc:
        raise bad_request(exc) from exc

    match = next(entry for entry in entries if entry.name == tool_name.strip())
    return ToolCatalogueEntry(
        name=match.name,
        description=match.description,
        tags=list(match.tags),
        url=match.url,
        logo_url=match.logo_url,
        role_count=match.role_count,
    )
