# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Skills and meta skills held by a role (#18390).

The grant belongs to the role, not to its holder: when the holder changes, the
next holder reaches the same skills. A role holds a skill directly or through a
meta skill; ``held_skills`` resolves both and reports the source of each.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from llc.models.company_os import LLCRoleSkill
from llc.models.company_os_enums import WorkflowKind
from llc.services.authz import require_company_admin
from llc.services.base import LLCServiceBase
from models.workflow import Workflow

from .errors import CompanyOsConflict, CompanyOsError, CompanyOsNotFound
from .loaders import get_workflow_row, load_meta_skills, require_role_in_company
from .skill_resolution import HeldSkill, resolve_held_skills

logger = get_logger(__name__)


class RoleSkillService(LLCServiceBase):
    """Grant, revoke and resolve the skills of one role in one company."""

    async def held_skills(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> List[HeldSkill]:
        """Every skill the role holds, transitively, each with its sources."""
        await require_role_in_company(session, company_id, role_id)
        grants = await self.list_grants(session, company_id, role_id)
        metas = await load_meta_skills(session, company_id)
        row_to_id = await self._meta_ids(
            session, company_id, {g.meta_skill_row_id for g in grants if g.meta_skill_row_id}
        )
        return resolve_held_skills([g.skill_name for g in grants if g.skill_name], list(row_to_id.values()), metas)

    async def grants_view(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> List[tuple]:
        """``(grant_id, skill_name, meta_skill_workflow_id)`` for each grant."""
        grants = await self.list_grants(session, company_id, role_id)
        ids = await self._meta_ids(session, company_id, {g.meta_skill_row_id for g in grants if g.meta_skill_row_id})
        return [(g.id, g.skill_name, ids.get(g.meta_skill_row_id)) for g in grants]

    async def held_skill_names(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> frozenset:
        return frozenset(h.skill for h in await self.held_skills(session, company_id, role_id))

    async def list_grants(self, session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> List[LLCRoleSkill]:
        result = await session.execute(
            select(LLCRoleSkill)
            .where(LLCRoleSkill.company_id == company_id, LLCRoleSkill.role_id == role_id)
            .order_by(LLCRoleSkill.created_at)
        )
        return list(result.scalars().all())

    async def _meta_ids(self, session: AsyncSession, company_id: uuid.UUID, row_ids: set) -> dict:
        if not row_ids:
            return {}
        rows = await session.execute(
            select(Workflow.id, Workflow.workflow_id).where(Workflow.company_id == company_id, Workflow.id.in_(row_ids))
        )
        return {r.id: r.workflow_id for r in rows}

    async def grant(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        *,
        actor: Optional[uuid.UUID],
        skill_name: Optional[str] = None,
        meta_skill_id: Optional[str] = None,
    ) -> LLCRoleSkill:
        """Grant exactly one of a skill name or a meta skill."""
        await require_company_admin(session, company_id, actor)
        if (skill_name is None) == (meta_skill_id is None):
            raise CompanyOsError("give exactly one of skill_name and meta_skill_id")
        await require_role_in_company(session, company_id, role_id)
        meta_row_id = await self._meta_row(session, company_id, meta_skill_id)
        grant = LLCRoleSkill(
            company_id=company_id,
            role_id=role_id,
            skill_name=skill_name,
            meta_skill_row_id=meta_row_id,
            created_by=actor,
        )
        session.add(grant)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise CompanyOsConflict("the role already holds this skill") from exc
        return grant

    async def _meta_row(self, session: AsyncSession, company_id: uuid.UUID, meta_skill_id: Optional[str]):
        if meta_skill_id is None:
            return None
        row = await get_workflow_row(session, company_id, meta_skill_id)
        if row.kind != WorkflowKind.META_SKILL.value:
            raise CompanyOsError(f"{meta_skill_id!r} is a workflow, not a meta skill")
        return row.id

    async def revoke(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        role_id: uuid.UUID,
        grant_id: uuid.UUID,
        *,
        actor: Optional[uuid.UUID],
    ) -> None:
        await require_company_admin(session, company_id, actor)
        result = await session.execute(
            delete(LLCRoleSkill).where(
                LLCRoleSkill.id == grant_id, LLCRoleSkill.role_id == role_id, LLCRoleSkill.company_id == company_id
            )
        )
        if result.rowcount == 0:
            raise CompanyOsNotFound("grant not found")
