"""LLC BacklogService — priority-ordered backlog queries and bulk sprint assignment (GH#8222).

Priority ordering is CRITICAL > HIGH > MEDIUM > LOW, implemented via a SQL CASE
expression so the DB handles sorting rather than Python.  Bulk sprint assignment
is done in a single UPDATE … WHERE id = ANY(:ids) to avoid N round-trips.
"""

import logging
import uuid
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import WorkItemPriority, WorkItemStatus, WorkItemType
from ..models.work_item import LLCWorkItem
from . import LLCServiceBase

logger = logging.getLogger(__name__)

# Numeric rank for SQL ORDER BY — lower = higher priority
_PRIORITY_RANK = case(
    (LLCWorkItem.priority == WorkItemPriority.CRITICAL.value, 1),
    (LLCWorkItem.priority == WorkItemPriority.HIGH.value, 2),
    (LLCWorkItem.priority == WorkItemPriority.MEDIUM.value, 3),
    (LLCWorkItem.priority == WorkItemPriority.LOW.value, 4),
    else_=5,
)


class BacklogService(LLCServiceBase):
    """Backlog-specific queries: filtered list, pagination, bulk sprint assign."""

    async def list_backlog(
        self,
        session: AsyncSession,
        company_id: str,
        *,
        project_id: Optional[str] = None,
        status: Optional[WorkItemStatus] = None,
        type: Optional[WorkItemType] = None,
        sprint_id: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Tuple[Sequence[LLCWorkItem], int]:
        """Return (items, total_count) matching filters, ordered by priority then created_at."""
        q = select(LLCWorkItem).where(LLCWorkItem.company_id == uuid.UUID(company_id))

        if project_id:
            q = q.where(LLCWorkItem.project_id == uuid.UUID(project_id))
        if status:
            q = q.where(LLCWorkItem.status == status)
        if type:
            q = q.where(LLCWorkItem.type == type)
        if sprint_id:
            q = q.where(LLCWorkItem.sprint_id == uuid.UUID(sprint_id))
        else:
            # Default backlog view: items not yet assigned to any sprint
            q = q.where(LLCWorkItem.sprint_id.is_(None))

        count_q = select(func.count()).select_from(q.subquery())
        total = (await session.execute(count_q)).scalar_one()

        q = q.order_by(_PRIORITY_RANK, LLCWorkItem.created_at.asc()).limit(limit).offset(offset)
        rows = (await session.execute(q)).scalars().all()
        return rows, total

    async def bulk_assign_sprint(
        self,
        session: AsyncSession,
        company_id: str,
        work_item_ids: List[str],
        sprint_id: str,
    ) -> int:
        """Assign all given work items to a sprint in one UPDATE.

        Returns the number of rows actually updated.  Items that don't belong to
        company_id are silently excluded (safety guard).
        """
        if not work_item_ids:
            return 0

        parsed_ids = [uuid.UUID(wid) for wid in work_item_ids]
        stmt = (
            update(LLCWorkItem)
            .where(
                LLCWorkItem.id.in_(parsed_ids),
                LLCWorkItem.company_id == uuid.UUID(company_id),
            )
            .values(sprint_id=uuid.UUID(sprint_id))
            .execution_options(synchronize_session=False)
        )
        result = await session.execute(stmt)
        await session.flush()
        updated = result.rowcount
        logger.info(
            "bulk_assign_sprint: %d/%d items assigned to sprint %s for company %s",
            updated,
            len(parsed_ids),
            sprint_id,
            company_id,
        )
        return updated
