# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Skills a role holds, resolved through meta skills (#18390).

Route group: /llc/company-os/roles/{role_id}/skills

Owner decision 2026-10-12: a skill delivered through a held meta skill counts as
held, transitively, and the response says which meta skill each came through.
Tenancy comes from the authenticated org context, as in ``company_os.py``.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from api.user_management.dependencies import get_current_user, require_org_context
from llc.deps import get_session
from llc.services.authz import NotAuthorisedError
from llc.services.company_os.errors import CompanyOsError
from llc.services.company_os.role_skills import RoleSkillService
from user_management.services import TenantContext

from ._common import actor_id
from .company_os import http_error
from .company_os_schemas import (
    GrantResponse,
    HeldSkillResponse,
    RoleSkillGrant,
    RoleSkillsResponse,
    SkillSourceResponse,
)

router = APIRouter(prefix="/company-os/roles", tags=["llc-company-os"])

_skills = RoleSkillService()


async def _view(session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> RoleSkillsResponse:
    held = await _skills.held_skills(session, company_id, role_id)
    grants = await _skills.grants_view(session, company_id, role_id)
    return RoleSkillsResponse(
        role_id=role_id,
        skills=[
            HeldSkillResponse(
                skill=h.skill,
                sources=[
                    SkillSourceResponse(
                        kind=s.kind, meta_skill_id=s.meta_skill_id, meta_skill_name=s.meta_skill_name, via=list(s.via)
                    )
                    for s in h.sources
                ],
            )
            for h in held
        ],
        grants=[GrantResponse(id=g, skill_name=n, meta_skill_id=m) for g, n, m in grants],
    )


@router.get("/{role_id}/skills", response_model=RoleSkillsResponse)
async def get_role_skills(
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    _user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> RoleSkillsResponse:
    """Every skill the role holds, directly or through a meta skill, with sources."""
    try:
        return await _view(session, ctx.org_id, role_id)
    except CompanyOsError as exc:
        raise http_error(exc) from exc


@router.post("/{role_id}/skills", response_model=GrantResponse, status_code=status.HTTP_201_CREATED)
async def grant_role_skill(
    role_id: uuid.UUID,
    body: RoleSkillGrant,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> GrantResponse:
    try:
        grant = await _skills.grant(
            session,
            ctx.org_id,
            role_id,
            actor=actor_id(user),
            skill_name=body.skill_name,
            meta_skill_id=body.meta_skill_id,
        )
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()
    return GrantResponse(id=grant.id, skill_name=grant.skill_name, meta_skill_id=body.meta_skill_id)


@router.delete("/{role_id}/skills/{grant_id}", status_code=status.HTTP_204_NO_CONTENT, response_model=None)
async def revoke_role_skill(
    role_id: uuid.UUID,
    grant_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
    user: dict = Depends(get_current_user),
    ctx: TenantContext = Depends(require_org_context),
) -> None:
    try:
        await _skills.revoke(session, ctx.org_id, role_id, grant_id, actor=actor_id(user))
    except (CompanyOsError, NotAuthorisedError) as exc:
        raise http_error(exc) from exc
    await session.commit()
