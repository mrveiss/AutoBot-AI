# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Parent/child rules for LLC work items (#18978, umbrella #18977).

The rules are data: ``ALLOWED_PARENT_TYPES`` and ``PROJECT_REQUIRED_TYPES`` are the single
source (also what a GUI endpoint should serve). Amending a rule is a one-line change there.

The rules apply to *writes* (``WorkItemService.create`` / ``update``). Existing rows that break
them are only reported (``find_hierarchy_violations``), never rewritten (#17038).
"""

import uuid
from typing import Awaitable, Callable, Dict, FrozenSet, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import WorkItemType
from ..models.work_item import LLCWorkItem

T = WorkItemType

# Child type -> the parent types it may sit under. An empty set means "no parent".
# A child may also have no parent at all (a backlog item not yet placed in the tree).
ALLOWED_PARENT_TYPES: Dict[WorkItemType, FrozenSet[WorkItemType]] = {
    T.EPIC: frozenset(),
    T.FEATURE: frozenset({T.EPIC}),
    T.PBI: frozenset({T.EPIC, T.FEATURE}),  # decision (a): Feature is optional
    T.TASK: frozenset({T.PBI}),
    T.SPIKE: frozenset({T.PBI}),
    T.RISK: frozenset({T.PBI}),
    T.BUG: frozenset({T.PBI, T.EPIC}),  # decision (b): a Bug sits under a PBI or an Epic
    T.SUBTASK: frozenset({T.TASK, T.BUG}),
}

# Decision (c): these types must name a project (their children inherit it).
PROJECT_REQUIRED_TYPES: FrozenSet[WorkItemType] = frozenset({T.EPIC})

# Longest chain a walk will follow. The rule table allows five levels; the margin covers
# legacy rows, and the bound is what makes the walk terminate on cyclic data.
MAX_HIERARCHY_DEPTH = 32


# ``WorkItemService.get`` -- the one place a work item is read by id, so it stays the one place to patch.
ItemGetter = Callable[..., Awaitable[Optional[LLCWorkItem]]]


class HierarchyViolation(ValueError):
    """A write would break the hierarchy rules. A ``ValueError`` like the sibling validation."""


def _type_of(raw) -> WorkItemType:
    return raw if isinstance(raw, WorkItemType) else WorkItemType(raw)


async def _fetch_parent(session: AsyncSession, get: ItemGetter, company_id: str, parent_id: str) -> LLCWorkItem:
    parent = await get(session, parent_id, company_id=company_id)
    if parent is None:
        raise HierarchyViolation(f"parent {parent_id} not found in this company")
    return parent


async def _assert_no_cycle(session: AsyncSession, get: ItemGetter, item_id: Optional[str], parent: LLCWorkItem) -> None:
    """Walk the parent chain up; refuse if it reaches the item, loops, or is too deep."""
    seen = set()
    node: Optional[LLCWorkItem] = parent
    while node is not None:
        if item_id is not None and str(node.id) == str(item_id):
            raise HierarchyViolation("parent would create a cycle")
        if node.id in seen or len(seen) >= MAX_HIERARCHY_DEPTH:
            raise HierarchyViolation("parent chain is cyclic or deeper than the allowed depth")
        seen.add(node.id)
        node = None if node.parent_id is None else await get(session, node.parent_id)


def _resolve_project(item_type: WorkItemType, parent: Optional[LLCWorkItem], project_id: Optional[str]):
    """Inherit the parent's project; a child may not name a different one."""
    parent_project = str(parent.project_id) if parent is not None and parent.project_id else None
    if parent_project and project_id and str(project_id) != parent_project:
        raise HierarchyViolation("a child must sit in the same project as its parent")
    resolved = parent_project or project_id
    if resolved is None and item_type in PROJECT_REQUIRED_TYPES:
        raise HierarchyViolation(f"a {item_type.value} requires a project_id")
    return resolved


async def validate_parent(
    session: AsyncSession,
    get: ItemGetter,
    *,
    company_id: str,
    item_type,
    item_id: Optional[str],
    parent_id: Optional[str],
    project_id: Optional[str],
) -> Tuple[Optional[str], Optional[LLCWorkItem]]:
    """Check a write against the rules; return the project the item ends up in and its parent row.

    Raises ``HierarchyViolation`` on a refusal. ``item_id`` is None for a create.
    """
    kind = _type_of(item_type)
    parent: Optional[LLCWorkItem] = None
    if parent_id is not None:
        if item_id is not None and str(parent_id) == str(item_id):
            raise HierarchyViolation("a work item cannot be its own parent")
        parent = await _fetch_parent(session, get, company_id, parent_id)
        if _type_of(parent.type) not in ALLOWED_PARENT_TYPES[kind]:
            allowed = sorted(t.value for t in ALLOWED_PARENT_TYPES[kind]) or ["none"]
            raise HierarchyViolation(
                f"a {kind.value} cannot sit under a {_type_of(parent.type).value}; allowed: {allowed}"
            )
        await _assert_no_cycle(session, get, item_id, parent)
    return _resolve_project(kind, parent, project_id), parent


async def validate_create(
    session: AsyncSession,
    get: ItemGetter,
    company_id: str,
    item_type,
    parent_id: Optional[str],
    project_id: Optional[str],
) -> Tuple[Optional[str], Optional[LLCWorkItem]]:
    """``validate_parent`` for a row not yet written: returns the project it takes and its parent row."""
    return await validate_parent(
        session,
        get,
        company_id=company_id,
        item_type=item_type,
        item_id=None,
        parent_id=parent_id,
        project_id=project_id,
    )


async def parent_if_allowed(
    session: AsyncSession, get: ItemGetter, company_id: str, item_type, parent_id: Optional[str]
) -> Optional[str]:
    """*parent_id* when a new *item_type* may sit under it, else None (for system-made items)."""
    if parent_id is None:
        return None
    try:
        await validate_create(session, get, company_id, item_type, parent_id, None)
    except HierarchyViolation:
        return None
    return parent_id


async def move_subtree_to_project(session: AsyncSession, root_id: uuid.UUID, project_id: uuid.UUID) -> int:
    """Set ``project_id`` on every descendant of *root_id*; bounded and cycle-safe. Returns the row count."""
    seen = {root_id}
    frontier = [root_id]
    moved = 0
    for _ in range(MAX_HIERARCHY_DEPTH):
        rows = await session.execute(select(LLCWorkItem.id).where(LLCWorkItem.parent_id.in_(frontier)))
        frontier = [i for i in rows.scalars().all() if i not in seen]
        if not frontier:
            break
        seen.update(frontier)
        await session.execute(update(LLCWorkItem).where(LLCWorkItem.id.in_(frontier)).values(project_id=project_id))
        moved += len(frontier)
    return moved


async def reparent(
    session: AsyncSession, get: ItemGetter, item: LLCWorkItem, parent_id: Optional[str]
) -> Optional[uuid.UUID]:
    """Validate moving *item* under *parent_id* and return the UUID to store.

    The item and its subtree take the new parent's project. A no-op when the parent is unchanged
    or being cleared, so an update that leaves ``parent_id`` alone never revisits an invalid row.
    """
    if parent_id is None:
        return None
    new_parent = uuid.UUID(str(parent_id))
    if new_parent == item.parent_id:
        return new_parent
    project, _ = await validate_parent(
        session,
        get,
        company_id=str(item.company_id),
        item_type=item.type,
        item_id=str(item.id),
        parent_id=str(new_parent),
        project_id=None,
    )
    if project is not None and str(item.project_id) != project:
        item.project_id = uuid.UUID(project)
        await move_subtree_to_project(session, item.id, item.project_id)
    return new_parent


async def find_hierarchy_violations(session: AsyncSession, company_id: str) -> List[Dict[str, str]]:
    """Read-only report of existing rows that break the rules (#17038: never rewritten)."""
    rows = (
        (await session.execute(select(LLCWorkItem).where(LLCWorkItem.company_id == uuid.UUID(str(company_id)))))
        .scalars()
        .all()
    )
    by_id = {r.id: r for r in rows}
    found = []
    for row in rows:
        reason = _row_violation(row, by_id.get(row.parent_id), by_id)
        if reason:
            found.append({"id": str(row.id), "identifier": row.identifier, "reason": reason})
    return found


def _in_cycle(row: LLCWorkItem, by_id: Dict[uuid.UUID, LLCWorkItem]) -> bool:
    node = by_id.get(row.parent_id)
    for _ in range(MAX_HIERARCHY_DEPTH):
        if node is None:
            return False
        if node.id == row.id:
            return True
        node = by_id.get(node.parent_id)
    return True


def _row_violation(row: LLCWorkItem, parent: Optional[LLCWorkItem], by_id=None) -> Optional[str]:
    kind = _type_of(row.type)
    if by_id is not None and _in_cycle(row, by_id):
        return "parent chain is cyclic or deeper than the allowed depth"
    if row.parent_id is not None and parent is None:
        return "parent is missing or in another company"
    if parent is not None and _type_of(parent.type) not in ALLOWED_PARENT_TYPES[kind]:
        return f"a {kind.value} cannot sit under a {_type_of(parent.type).value}"
    if parent is not None and parent.project_id and row.project_id != parent.project_id:
        return "project differs from the parent's"
    if kind in PROJECT_REQUIRED_TYPES and row.project_id is None:
        return f"a {kind.value} has no project_id"
    return None
