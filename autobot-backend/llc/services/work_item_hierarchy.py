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

from sqlalchemy import and_, func, literal, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from autobot_shared.env_utils import env_int_clamped

from ..models.enums import WorkItemType
from ..models.sprint import LLCProject
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

# Owner ruling (#18978): every work item of any type belongs to a project (children inherit it).
PROJECT_REQUIRED_TYPES: FrozenSet[WorkItemType] = frozenset(WorkItemType)

# Longest chain a walk will follow. The rule table allows five levels; the margin covers
# legacy rows, and the bound is what makes the walk terminate on cyclic data.
MAX_HIERARCHY_DEPTH = 32

# Violations one report returns; the query stops at this many (+1, to know there were more) in SQL (#20936).
HIERARCHY_VIOLATIONS_LIMIT = env_int_clamped("AUTOBOT_LLC_HIERARCHY_VIOLATIONS_LIMIT", 500, min_v=1, max_v=5000)

# Stable violation codes: the report's contract. The GUI renders each through an i18n key.
CYCLE = "parent_cycle"
PARENT_MISSING = "parent_missing"
PARENT_TYPE = "parent_type_not_allowed"
PROJECT_MISMATCH = "project_mismatch"
PROJECT_REQUIRED = "project_required"

# Ids per ``UPDATE ... WHERE id IN (...)`` when a subtree moves; well under the 32,767 bind-parameter limit.
SUBTREE_UPDATE_BATCH = 10_000


# ``WorkItemService.get`` -- the one place a work item is read by id, so it stays the one place to patch.
ItemGetter = Callable[..., Awaitable[Optional[LLCWorkItem]]]


class HierarchyViolation(ValueError):
    """A write would break the hierarchy rules. A ``ValueError`` like the sibling validation."""


class ProjectRequired(HierarchyViolation):
    """The item would have no project (and no parent to inherit one from)."""


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


async def _assert_project_in_company(session: AsyncSession, company_id: str, project_id: str) -> None:
    """A project of another company reads the same as one that does not exist: not found."""
    stmt = select(LLCProject.id).where(
        LLCProject.id == uuid.UUID(str(project_id)), LLCProject.company_id == uuid.UUID(str(company_id))
    )
    if (await session.execute(stmt)).scalar_one_or_none() is None:
        raise HierarchyViolation(f"project {project_id} not found in this company")


def _same_project(first: object, second: object) -> bool:
    """Whether two project ids name one project: compared as UUIDs, so an un-hyphenated spelling still matches."""
    try:
        return uuid.UUID(str(first)) == uuid.UUID(str(second))
    except ValueError:
        return str(first) == str(second)


def _resolve_project(
    item_type: WorkItemType, parent: Optional[LLCWorkItem], project_id: Optional[str], current: Optional[str] = None
):
    """Inherit the parent's project; a child may not name a different one.

    ``current`` is a moved item's existing project: it counts only when neither parent nor caller names one.
    """
    parent_project = str(parent.project_id) if parent is not None and parent.project_id else None
    if parent_project and project_id and not _same_project(project_id, parent_project):
        raise HierarchyViolation("a child must sit in the same project as its parent")
    resolved = parent_project or project_id or current
    if resolved is None and item_type in PROJECT_REQUIRED_TYPES:
        raise ProjectRequired(f"a {item_type.value} requires a project_id (or a parent that has one)")
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
    current_project: Optional[str] = None,
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
    resolved = _resolve_project(kind, parent, project_id, current_project)
    await _assert_project_in_company(session, company_id, resolved)
    return resolved, parent


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
    session: AsyncSession,
    get: ItemGetter,
    company_id: str,
    item_type,
    parent_id: Optional[str],
    project_id: Optional[str] = None,
) -> Optional[str]:
    """*parent_id* when a new *item_type* in *project_id* may sit under it, else None (for system-made items)."""
    if parent_id is None:
        return None
    try:
        await validate_create(session, get, company_id, item_type, parent_id, project_id)
    except HierarchyViolation:
        return None
    return parent_id


async def _descendant_ids(session: AsyncSession, root_id: uuid.UUID, company_id: uuid.UUID) -> List[uuid.UUID]:
    """Every descendant of *root_id* in *company_id*, to any depth. Cycle-safe: a row is visited once."""
    seen = {root_id}
    found: List[uuid.UUID] = []
    frontier = [root_id]
    while frontier:
        rows = await session.execute(
            select(LLCWorkItem.id).where(LLCWorkItem.parent_id.in_(frontier), LLCWorkItem.company_id == company_id)
        )
        frontier = [i for i in rows.scalars().all() if i not in seen]
        seen.update(frontier)
        found.extend(frontier)
    return found


async def move_subtree_to_project(
    session: AsyncSession, root_id: uuid.UUID, project_id: uuid.UUID, company_id: uuid.UUID
) -> int:
    """Set ``project_id`` on every descendant of *root_id* in *company_id*, at any depth. Returns the count.

    The whole subtree is read before anything is written, so a move can never stop half way down. The
    writes go out in batches of ``SUBTREE_UPDATE_BATCH`` ids in the caller's transaction: one ``IN (...)``
    over more ids than the driver's bind-parameter limit (32,767) would fail the whole move.
    """
    descendants = await _descendant_ids(session, root_id, company_id)
    for start in range(0, len(descendants), SUBTREE_UPDATE_BATCH):
        await session.execute(
            update(LLCWorkItem)
            .where(
                LLCWorkItem.id.in_(descendants[start : start + SUBTREE_UPDATE_BATCH]),
                LLCWorkItem.company_id == company_id,
            )
            .values(project_id=project_id)
        )
    return len(descendants)


async def reparent(
    session: AsyncSession, get: ItemGetter, item: LLCWorkItem, parent_id: Optional[str]
) -> Optional[uuid.UUID]:
    """Validate moving *item* under *parent_id* (None detaches it) and return the UUID to store.

    The item and its subtree take the new parent's project. A no-op when the parent is unchanged,
    so an update that leaves ``parent_id`` alone never revisits an invalid row. A detach is a real
    change, so a type that requires a project must still have one.
    """
    new_parent = uuid.UUID(str(parent_id)) if parent_id is not None else None
    if new_parent == item.parent_id:
        return new_parent
    project, _ = await validate_parent(
        session,
        get,
        company_id=str(item.company_id),
        item_type=item.type,
        item_id=str(item.id),
        parent_id=str(new_parent) if new_parent is not None else None,
        project_id=None,
        current_project=str(item.project_id) if item.project_id else None,
    )
    if project is not None and not (item.project_id and _same_project(item.project_id, project)):
        item.project_id = uuid.UUID(project)
        await move_subtree_to_project(session, item.id, item.project_id, item.company_id)
    return new_parent


def _cycle_members(company: uuid.UUID):
    """Recursive CTE: ids whose parent chain returns to them, or runs deeper than ``MAX_HIERARCHY_DEPTH``."""
    parent = aliased(LLCWorkItem)
    base = (
        select(LLCWorkItem.id.label("start"), parent.id.label("node"), literal(1).label("depth"))
        .join(parent, parent.id == LLCWorkItem.parent_id)
        .where(LLCWorkItem.company_id == company, parent.company_id == company)
        .cte("hierarchy_walk", recursive=True)
    )
    cur, nxt = aliased(LLCWorkItem), aliased(LLCWorkItem)
    walk = base.union_all(
        select(base.c.start, nxt.id, base.c.depth + 1)
        .join(cur, cur.id == base.c.node)
        .join(nxt, nxt.id == cur.parent_id)
        .where(base.c.depth < MAX_HIERARCHY_DEPTH, base.c.node != base.c.start, nxt.company_id == company)
    )
    looped = or_(walk.c.node == walk.c.start, walk.c.depth >= MAX_HIERARCHY_DEPTH)
    return select(walk.c.start).where(looped)


def _violation_filter(parent, cycle_ids):
    """SQL form of ``_row_violation``: a row matches iff it breaks at least one rule."""
    bad_type = [
        and_(LLCWorkItem.type == kind, parent.type.not_in(sorted(allowed, key=lambda t: t.value)))
        for kind, allowed in ALLOWED_PARENT_TYPES.items()
    ]
    return or_(
        LLCWorkItem.id.in_(cycle_ids),
        and_(LLCWorkItem.parent_id.is_not(None), parent.id.is_(None)),
        and_(parent.id.is_not(None), or_(*bad_type)),
        and_(
            parent.id.is_not(None),
            parent.project_id.is_not(None),
            LLCWorkItem.project_id.is_distinct_from(parent.project_id),
        ),
        and_(
            LLCWorkItem.type.in_(sorted(PROJECT_REQUIRED_TYPES, key=lambda t: t.value)),
            LLCWorkItem.project_id.is_(None),
        ),
    )


async def find_hierarchy_violations(
    session: AsyncSession, company_id: str, limit: int = HIERARCHY_VIOLATIONS_LIMIT
) -> Tuple[List[Dict[str, Optional[str]]], bool]:
    """Read-only report of existing rows that break the rules (#17038: never rewritten).

    Returns ``(rows, truncated)``. The rules are applied and the limit taken in SQL, so at most
    ``limit + 1`` rows leave the database; ``truncated`` says there were more than *limit*.
    """
    company = uuid.UUID(str(company_id))
    parent = aliased(LLCWorkItem)
    cycle_ids = _cycle_members(company)
    stmt = (
        select(LLCWorkItem, parent, LLCWorkItem.id.in_(cycle_ids))
        .outerjoin(parent, and_(parent.id == LLCWorkItem.parent_id, parent.company_id == company))
        .where(LLCWorkItem.company_id == company, _violation_filter(parent, cycle_ids))
        .order_by(LLCWorkItem.identifier, LLCWorkItem.id)
        .limit(limit + 1)
    )
    fetched = (await session.execute(stmt)).all()
    return [_report_row(*r) for r in fetched[:limit]], len(fetched) > limit


def _report_row(row: LLCWorkItem, parent: Optional[LLCWorkItem], in_cycle: bool) -> Dict[str, Optional[str]]:
    code, reason = _row_violation(row, parent, in_cycle)
    return {
        "id": str(row.id),
        "identifier": row.identifier,
        "code": code,
        "reason": reason,
        "type": _type_of(row.type).value,
        "parent_type": _type_of(parent.type).value if parent is not None else None,
    }


def _row_violation(row: LLCWorkItem, parent: Optional[LLCWorkItem], in_cycle: bool) -> Tuple[str, str]:
    """The first rule *row* breaks, as ``(stable code, English text for logs)``. Mirrors ``_violation_filter``."""
    kind = _type_of(row.type)
    if in_cycle:
        return CYCLE, "parent chain is cyclic or deeper than the allowed depth"
    if row.parent_id is not None and parent is None:
        return PARENT_MISSING, "parent is missing or in another company"
    if parent is not None and _type_of(parent.type) not in ALLOWED_PARENT_TYPES[kind]:
        return PARENT_TYPE, f"a {kind.value} cannot sit under a {_type_of(parent.type).value}"
    if parent is not None and parent.project_id and row.project_id != parent.project_id:
        return PROJECT_MISMATCH, "project differs from the parent's"
    return PROJECT_REQUIRED, f"a {kind.value} has no project_id"


async def count_items_without_project(session: AsyncSession) -> Dict[str, int]:
    """Read-only: work items with no ``project_id``, per company id (the backfill proposal's measure, #17038)."""
    stmt = (
        select(LLCWorkItem.company_id, func.count())
        .where(LLCWorkItem.project_id.is_(None))
        .group_by(LLCWorkItem.company_id)
    )
    return {str(company): n for company, n in (await session.execute(stmt)).all()}
