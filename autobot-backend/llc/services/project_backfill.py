# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Give the work items that have no project one (#18978; owner ruling, option A).

Every work item belongs to a project, but older rows have none. This module only PLANS and APPLIES that
backfill; nothing here runs by itself. An agent never calls ``apply_project_backfill``: it is reached only
from the post-approval action (``services.project_backfill_action``) after a person approves, and a
migration must never do it (#17038).

An item with no project takes, in order:

1. the project of its nearest ancestor that has one;
2. else the company's default project (``DEFAULT_PROJECT_NAME``), created if the company has none.

Both functions recount from the rows, so a preview is never trusted at apply time and a second run finds
nothing to do.
"""

from __future__ import annotations

import uuid
from typing import Dict, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.sprint import LLCProject
from ..models.work_item import LLCWorkItem
from .work_item_hierarchy import MAX_HIERARCHY_DEPTH

# A working label (owner ruling): the stored name of the per-company default project.
DEFAULT_PROJECT_NAME = "Unassigned"

_Rows = Dict[uuid.UUID, Tuple[Optional[uuid.UUID], Optional[uuid.UUID]]]  # id -> (parent_id, project_id)


async def _company_rows(session: AsyncSession, company_id: uuid.UUID) -> _Rows:
    stmt = select(LLCWorkItem.id, LLCWorkItem.parent_id, LLCWorkItem.project_id).where(
        LLCWorkItem.company_id == company_id
    )
    return {i: (parent, project) for i, parent, project in (await session.execute(stmt)).all()}


def _ancestor_project(item_id: uuid.UUID, rows: _Rows) -> Optional[uuid.UUID]:
    """The project of the nearest ancestor that has one; bounded, and safe on a cyclic chain."""
    seen = {item_id}
    node = rows[item_id][0]
    for _ in range(MAX_HIERARCHY_DEPTH):
        if node is None or node in seen or node not in rows:
            return None
        if rows[node][1] is not None:
            return rows[node][1]
        seen.add(node)
        node = rows[node][0]
    return None


def _plan(rows: _Rows) -> Dict[uuid.UUID, Optional[uuid.UUID]]:
    """item id -> the ancestor's project, or None for "the default", for every item with no project."""
    return {i: _ancestor_project(i, rows) for i, (_, project) in rows.items() if project is None}


async def _default_project(session: AsyncSession, company_id: uuid.UUID) -> Optional[uuid.UUID]:
    stmt = select(LLCProject.id).where(LLCProject.company_id == company_id, LLCProject.name == DEFAULT_PROJECT_NAME)
    return (await session.execute(stmt)).scalars().first()


def _counts(plan: Dict[uuid.UUID, Optional[uuid.UUID]], default_exists: bool) -> Dict[str, object]:
    to_default = sum(1 for project in plan.values() if project is None)
    return {
        "missing": len(plan),
        "from_ancestor": len(plan) - to_default,
        "to_default": to_default,
        "default_project_exists": default_exists,
        "default_project_would_be_created": to_default > 0 and not default_exists,
    }


async def preview_project_backfill(session: AsyncSession, company_id: uuid.UUID) -> Dict[str, object]:
    """What the backfill would do for one company. Read-only: nothing is written or created."""
    plan = _plan(await _company_rows(session, company_id))
    return _counts(plan, await _default_project(session, company_id) is not None)


async def apply_project_backfill(session: AsyncSession, company_id: uuid.UUID) -> Dict[str, object]:
    """Perform the backfill for one company, recounting first. Only the approved action calls this."""
    plan = _plan(await _company_rows(session, company_id))
    default_id = await _default_project(session, company_id)
    result = _counts(plan, default_id is not None)
    if result["default_project_would_be_created"]:
        default_id = uuid.uuid4()
        session.add(LLCProject(id=default_id, company_id=company_id, name=DEFAULT_PROJECT_NAME))
        await session.flush()
    for project in {p if p is not None else default_id for p in plan.values()}:
        ids = [i for i, p in plan.items() if (p if p is not None else default_id) == project]
        await session.execute(update(LLCWorkItem).where(LLCWorkItem.id.in_(ids)).values(project_id=project))
    await session.flush()
    result["default_project_id"] = str(default_id) if default_id else None
    return result
