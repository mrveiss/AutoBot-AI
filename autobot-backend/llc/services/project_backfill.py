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

1. the project of its nearest ancestor that has one of THIS company's projects (a project of another company,
   from bad old data, counts as none and is reported separately);
2. else the company's default project (``DEFAULT_PROJECT_NAME``), created if the company has none.

An item whose child already sits in ANOTHER project than the one it would take is a conflict: giving it the
project would break the rule that a child shares its parent's project. Conflicts are listed in the preview,
skipped by apply, and reported by id in its result; a person resolves them.

Both functions recount from the rows, so a preview is never trusted at apply time and a second run finds
nothing to do.
"""

from __future__ import annotations

import uuid
from typing import Dict, Optional, Set, Tuple

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


def _ancestor_project(item_id: uuid.UUID, rows: _Rows, valid: Set[uuid.UUID]) -> Tuple[Optional[uuid.UUID], bool]:
    """(project of the nearest ancestor with one of THIS company's projects, whether a foreign one was passed over).

    Bounded, and safe on a cyclic chain. An ancestor whose project is not in *valid* counts as having none.
    """
    seen, foreign = {item_id}, False
    node = rows[item_id][0]
    for _ in range(MAX_HIERARCHY_DEPTH):
        if node is None or node in seen or node not in rows:
            break
        project = rows[node][1]
        if project is not None and project in valid:
            return project, foreign
        foreign = foreign or project is not None
        seen.add(node)
        node = rows[node][0]
    return None, foreign


_Plan = Dict[uuid.UUID, Tuple[Optional[uuid.UUID], bool]]  # item id -> (ancestor's project or None = default, foreign)


def _plan(rows: _Rows, valid: Set[uuid.UUID]) -> _Plan:
    """For every item with no project: where it goes, and whether a foreign ancestor project was passed over."""
    return {i: _ancestor_project(i, rows, valid) for i, (_, project) in rows.items() if project is None}


async def _company_projects(session: AsyncSession, company_id: uuid.UUID) -> Set[uuid.UUID]:
    stmt = select(LLCProject.id).where(LLCProject.company_id == company_id)
    return set((await session.execute(stmt)).scalars().all())


async def _default_project(session: AsyncSession, company_id: uuid.UUID) -> Optional[uuid.UUID]:
    stmt = select(LLCProject.id).where(LLCProject.company_id == company_id, LLCProject.name == DEFAULT_PROJECT_NAME)
    return (await session.execute(stmt)).scalars().first()


def _conflicting(plan: _Plan, rows: _Rows, default_id: Optional[uuid.UUID]) -> Set[uuid.UUID]:
    """Items in *plan* with a child that already has a project other than the one the item would take."""
    child_projects: Dict[uuid.UUID, Set[uuid.UUID]] = {}
    for parent, project in rows.values():
        if parent is not None and project is not None:
            child_projects.setdefault(parent, set()).add(project)
    return {
        i
        for i, (project, _) in plan.items()
        if child_projects.get(i, set()) - {project if project is not None else default_id}
    }


def _counts(plan: _Plan, default_exists: bool, conflicts: Set[uuid.UUID]) -> Dict[str, object]:
    """Counts of the items that will be filled; *conflicts* are reported apart and never filled."""
    to_default = sum(1 for project, _ in plan.values() if project is None)
    return {
        "missing": len(plan) + len(conflicts),
        "conflicts": len(conflicts),
        "conflicting_item_ids": sorted(str(i) for i in conflicts),
        "from_ancestor": len(plan) - to_default,
        "to_default": to_default,
        "foreign_ancestor_project_skipped": sum(1 for _, foreign in plan.values() if foreign),
        "default_project_exists": default_exists,
        "default_project_would_be_created": to_default > 0 and not default_exists,
    }


async def _plan_for(session: AsyncSession, company_id: uuid.UUID) -> Tuple[_Plan, Set[uuid.UUID], Optional[uuid.UUID]]:
    """(the items to fill, the conflicting items left out of it, the company's default project if it has one)."""
    rows = await _company_rows(session, company_id)
    full = _plan(rows, await _company_projects(session, company_id))
    default_id = await _default_project(session, company_id)
    conflicts = _conflicting(full, rows, default_id)
    return {i: v for i, v in full.items() if i not in conflicts}, conflicts, default_id


async def preview_project_backfill(session: AsyncSession, company_id: uuid.UUID) -> Dict[str, object]:
    """What the backfill would do for one company. Read-only: nothing is written or created."""
    plan, conflicts, default_id = await _plan_for(session, company_id)
    return _counts(plan, default_id is not None, conflicts)


async def apply_project_backfill(session: AsyncSession, company_id: uuid.UUID) -> Dict[str, object]:
    """Perform the backfill for one company, recounting first. Only the approved action calls this.

    Conflicting items are skipped; their ids are in the result's ``conflicting_item_ids``.
    """
    plan, conflicts, default_id = await _plan_for(session, company_id)
    result = _counts(plan, default_id is not None, conflicts)
    if result["default_project_would_be_created"]:
        default_id = uuid.uuid4()
        session.add(LLCProject(id=default_id, company_id=company_id, name=DEFAULT_PROJECT_NAME))
        await session.flush()
    target = {i: (p if p is not None else default_id) for i, (p, _) in plan.items()}
    updated = 0
    for project in set(target.values()):
        ids = [i for i, t in target.items() if t == project]
        stmt = (
            update(LLCWorkItem)
            .where(LLCWorkItem.id.in_(ids), LLCWorkItem.project_id.is_(None))  # one that got a project since keeps it
            .values(project_id=project)
        )
        updated += (await session.execute(stmt)).rowcount or 0
    await session.flush()
    result["updated"] = updated
    result["skipped_already_in_project"] = len(target) - updated
    result["default_project_id"] = str(default_id) if default_id else None
    return result
