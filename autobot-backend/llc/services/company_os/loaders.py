# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Company-scoped lookups shared by the Company OS services (#18390).

Every query here filters on ``company_id`` in the statement itself. An id that
exists only in another company therefore never comes back, and the callers report
it exactly as they report an id that exists nowhere.
"""

from __future__ import annotations

import uuid
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llc.models.company_os import LLCProcess, LLCWorkflowNode
from llc.models.company_os_enums import NodeKind, WorkflowKind
from models.workflow import Workflow

from .._role_guard import role_exists_in_company
from .errors import CompanyOsNotFound
from .skill_resolution import MetaSkillDef


async def require_role_in_company(session: AsyncSession, company_id: uuid.UUID, role_id: uuid.UUID) -> None:
    if not await role_exists_in_company(session, company_id, role_id):
        raise CompanyOsNotFound(f"role {role_id} does not exist in this company")


def is_company_os_row(row: object) -> bool:
    """True for a meta skill or a role-owned workflow: rows the Company OS rules govern.

    ``isinstance`` on the owner, not truthiness, so a stand-in object cannot pass.
    """
    return getattr(row, "kind", None) == WorkflowKind.META_SKILL.value or isinstance(
        getattr(row, "owner_role_id", None), uuid.UUID
    )


async def get_workflow_row(
    session: AsyncSession, company_id: uuid.UUID, workflow_id: str, *, lock: bool = False
) -> Workflow:
    """Load a workflow of this company. ``lock`` takes ``SELECT ... FOR UPDATE`` on the row."""
    stmt = select(Workflow).where(Workflow.company_id == company_id, Workflow.workflow_id == workflow_id)
    result = await session.execute(stmt.with_for_update() if lock else stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise CompanyOsNotFound(f"workflow {workflow_id!r} does not exist in this company")
    return row


async def get_process_row(session: AsyncSession, company_id: uuid.UUID, process_key: str) -> LLCProcess:
    result = await session.execute(
        select(LLCProcess).where(LLCProcess.company_id == company_id, LLCProcess.process_key == process_key)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise CompanyOsNotFound(f"process {process_key!r} does not exist in this company")
    return row


async def load_meta_skills(session: AsyncSession, company_id: uuid.UUID) -> Dict[str, MetaSkillDef]:
    """Every meta skill of the company, keyed by ``workflow_id``, with the skills
    its own graph requires and the meta skills it calls."""
    metas = (
        await session.execute(
            select(Workflow.id, Workflow.workflow_id, Workflow.name).where(
                Workflow.company_id == company_id, Workflow.kind == WorkflowKind.META_SKILL.value
            )
        )
    ).all()
    by_row = {m.id: m for m in metas}
    if not by_row:
        return {}
    nodes = (
        (
            await session.execute(
                select(LLCWorkflowNode).where(
                    LLCWorkflowNode.company_id == company_id, LLCWorkflowNode.workflow_row_id.in_(by_row)
                )
            )
        )
        .scalars()
        .all()
    )
    skills = await _process_skills(session, company_id, {n.process_id for n in nodes if n.process_id})
    out: Dict[str, MetaSkillDef] = {}
    for row_id, meta in by_row.items():
        mine = [n for n in nodes if n.workflow_row_id == row_id]
        own = tuple(sorted({s for n in mine if n.kind == NodeKind.PROCESS.value for s in skills.get(n.process_id, [])}))
        calls = tuple(by_row[n.meta_skill_row_id].workflow_id for n in mine if n.meta_skill_row_id in by_row)
        out[meta.workflow_id] = MetaSkillDef(meta.workflow_id, meta.name or meta.workflow_id, own, calls)
    return out


async def _process_skills(session: AsyncSession, company_id: uuid.UUID, ids: set) -> Dict[uuid.UUID, list]:
    if not ids:
        return {}
    rows = await session.execute(
        select(LLCProcess.id, LLCProcess.required_skills).where(
            LLCProcess.company_id == company_id, LLCProcess.id.in_(ids)
        )
    )
    return {r.id: list(r.required_skills or []) for r in rows}


async def workflow_id_of(session: AsyncSession, company_id: uuid.UUID, row_id: Optional[uuid.UUID]) -> Optional[str]:
    if row_id is None:
        return None
    result = await session.execute(
        select(Workflow.workflow_id).where(Workflow.id == row_id, Workflow.company_id == company_id)
    )
    return result.scalar_one_or_none()
