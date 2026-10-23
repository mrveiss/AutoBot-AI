# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company-scoped CRUD for processes (#18390).

A process is reusable across workflows and has exactly one owner role. It may
require skills; whether the role holds them is a validation *warning* on the
workflow graph, not a constraint here, because the role's skills change
independently of the process.
"""

from __future__ import annotations

import uuid
from typing import Any, List, Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.company_os import LLCProcess, LLCWorkflowNode
from llc.models.company_os_enums import WorkflowTriggerKind
from llc.services.authz import require_company_admin
from llc.services.base import LLCServiceBase
from models.workflow import Workflow

from .errors import CompanyOsConflict, CompanyOsError
from .loaders import get_process_row, require_role_in_company


def _clean_skills(skills: Optional[List[str]]) -> List[str]:
    cleaned = [s.strip() for s in (skills or [])]
    if any(not s for s in cleaned):
        raise CompanyOsError("required_skills may not contain an empty name")
    return sorted(set(cleaned))


class ProcessService(LLCServiceBase):
    async def create(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        *,
        process_key: str,
        name: str,
        owner_role_id: uuid.UUID,
        actor: Optional[uuid.UUID],
        description: Optional[str] = None,
        required_skills: Optional[List[str]] = None,
    ) -> LLCProcess:
        await require_company_admin(session, company_id, actor)
        await require_role_in_company(session, company_id, owner_role_id)
        row = LLCProcess(
            company_id=company_id,
            process_key=process_key,
            name=name,
            description=description,
            owner_role_id=owner_role_id,
            required_skills=_clean_skills(required_skills),
            created_by=actor,
        )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError as exc:
            await session.rollback()
            raise CompanyOsConflict(f"process {process_key!r} already exists") from exc
        return row

    async def get(self, session: AsyncSession, company_id: uuid.UUID, process_key: str) -> LLCProcess:
        return await get_process_row(session, company_id, process_key)

    async def list(
        self, session: AsyncSession, company_id: uuid.UUID, owner_role_id: Optional[uuid.UUID] = None
    ) -> List[LLCProcess]:
        stmt = select(LLCProcess).where(LLCProcess.company_id == company_id).order_by(LLCProcess.process_key)
        if owner_role_id is not None:
            stmt = stmt.where(LLCProcess.owner_role_id == owner_role_id)
        return list((await session.execute(stmt)).scalars().all())

    async def update(
        self,
        session: AsyncSession,
        company_id: uuid.UUID,
        process_key: str,
        *,
        actor: Optional[uuid.UUID],
        **fields: Any,
    ) -> LLCProcess:
        """Apply only the keys present in *fields* (``exclude_unset`` semantics)."""
        await require_company_admin(session, company_id, actor)
        row = await get_process_row(session, company_id, process_key)
        if fields.get("owner_role_id") is not None:
            await require_role_in_company(session, company_id, fields["owner_role_id"])
        if "required_skills" in fields:
            fields["required_skills"] = _clean_skills(fields["required_skills"])
        for key in ("name", "description", "owner_role_id", "required_skills"):
            if key in fields and not (fields[key] is None and key in ("name", "owner_role_id", "required_skills")):
                setattr(row, key, fields[key])
        await session.flush()
        return row

    async def delete(
        self, session: AsyncSession, company_id: uuid.UUID, process_key: str, *, actor: Optional[uuid.UUID]
    ) -> None:
        await require_company_admin(session, company_id, actor)
        row = await get_process_row(session, company_id, process_key)
        used = await session.execute(
            select(func.count())
            .select_from(LLCWorkflowNode)
            .where(LLCWorkflowNode.company_id == company_id, LLCWorkflowNode.process_id == row.id)
        )
        if used.scalar_one() or await self._is_trigger_source(session, company_id, process_key):
            raise CompanyOsConflict(f"process {process_key!r} is used by a workflow graph or trigger")
        await session.delete(row)
        await session.flush()

    async def _is_trigger_source(self, session: AsyncSession, company_id: uuid.UUID, process_key: str) -> bool:
        rows = await session.execute(
            select(Workflow.trigger_config).where(
                Workflow.company_id == company_id, Workflow.trigger_type == WorkflowTriggerKind.PROCESS_RESULT.value
            )
        )
        return any((cfg or {}).get("process_key") == process_key for (cfg,) in rows)
