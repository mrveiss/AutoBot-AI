# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLCLabelService — label CRUD and work-item assignment (GH#8254)."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.label import LLCLabel, LLCWorkItemLabel, _next_default_color
from ..models.work_item import LLCWorkItem
from .base import LLCServiceBase

logger = logging.getLogger(__name__)


class LabelNotFound(Exception):
    pass


class WorkItemNotFound(Exception):
    pass


class LabelNameConflict(Exception):
    pass


class LLCLabelService(LLCServiceBase):
    """Service for LLC label management and work-item assignment."""

    # ------------------------------------------------------------------
    # Label CRUD
    # ------------------------------------------------------------------

    async def create(
        self,
        session: AsyncSession,
        company_id: str,
        name: str,
        color: Optional[str] = None,
        description: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> LLCLabel:
        # Determine color — cycle through palette if not specified
        if color is None:
            count_result = await session.execute(
                select(func.count()).where(LLCLabel.company_id == uuid.UUID(company_id))
            )
            count = count_result.scalar_one()
            color = _next_default_color(count)

        label = LLCLabel(
            company_id=uuid.UUID(company_id),
            name=name,
            color=color,
            description=description,
            created_by=created_by,
        )
        session.add(label)
        await session.flush()
        await session.refresh(label)
        return label

    async def list_labels(
        self,
        session: AsyncSession,
        company_id: str,
    ) -> List[Dict[str, Any]]:
        """Return labels with usage counts."""
        stmt = (
            select(
                LLCLabel,
                func.count(LLCWorkItemLabel.work_item_id).label("usage_count"),
            )
            .outerjoin(
                LLCWorkItemLabel,
                LLCWorkItemLabel.label_id == LLCLabel.id,
            )
            .where(LLCLabel.company_id == uuid.UUID(company_id))
            .group_by(LLCLabel.id)
            .order_by(LLCLabel.name)
        )
        rows = await session.execute(stmt)
        result = []
        for label, usage_count in rows:
            result.append({**_label_to_dict(label), "usage_count": usage_count})
        return result

    async def get(self, session: AsyncSession, label_id: str) -> Optional[LLCLabel]:
        result = await session.execute(select(LLCLabel).where(LLCLabel.id == uuid.UUID(label_id)))
        return result.scalar_one_or_none()

    async def update(
        self,
        session: AsyncSession,
        label_id: str,
        name: Optional[str] = None,
        color: Optional[str] = None,
        description: Optional[str] = None,
    ) -> LLCLabel:
        label = await self.get(session, label_id)
        if label is None:
            raise LabelNotFound(label_id)
        if name is not None:
            label.name = name
        if color is not None:
            label.color = color
        if description is not None:
            label.description = description
        await session.flush()
        return label

    async def delete(self, session: AsyncSession, label_id: str) -> None:
        label = await self.get(session, label_id)
        if label is None:
            raise LabelNotFound(label_id)
        await session.delete(label)
        await session.flush()

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    async def assign_labels(
        self,
        session: AsyncSession,
        work_item_id: str,
        label_ids: List[str],
        assigned_by: Optional[str] = None,
    ) -> List[LLCWorkItemLabel]:
        wi_result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)))
        work_item = wi_result.scalar_one_or_none()
        if work_item is None:
            raise WorkItemNotFound(work_item_id)

        added: List[LLCWorkItemLabel] = []
        for lid in label_ids:
            existing = await session.get(LLCWorkItemLabel, (uuid.UUID(work_item_id), uuid.UUID(lid)))
            if existing is not None:
                continue
            wil = LLCWorkItemLabel(
                work_item_id=uuid.UUID(work_item_id),
                label_id=uuid.UUID(lid),
                assigned_by=assigned_by,
            )
            session.add(wil)
            added.append(wil)

        await session.flush()

        if added and self.activity_log:
            from .activity_log import ActivityEventType

            await self.activity_log.record(
                session,
                company_id=str(work_item.company_id),
                event_type=ActivityEventType.WORK_ITEM_UPDATED,
                entity_type="work_item",
                entity_id=work_item_id,
                after_state={"labels_assigned": [str(a.label_id) for a in added]},
            )

        return added

    async def remove_label(
        self,
        session: AsyncSession,
        work_item_id: str,
        label_id: str,
    ) -> None:
        wi_result = await session.execute(select(LLCWorkItem).where(LLCWorkItem.id == uuid.UUID(work_item_id)))
        work_item = wi_result.scalar_one_or_none()
        if work_item is None:
            raise WorkItemNotFound(work_item_id)

        await session.execute(
            delete(LLCWorkItemLabel).where(
                LLCWorkItemLabel.work_item_id == uuid.UUID(work_item_id),
                LLCWorkItemLabel.label_id == uuid.UUID(label_id),
            )
        )
        await session.flush()

        if self.activity_log:
            from .activity_log import ActivityEventType

            await self.activity_log.record(
                session,
                company_id=str(work_item.company_id),
                event_type=ActivityEventType.WORK_ITEM_UPDATED,
                entity_type="work_item",
                entity_id=work_item_id,
                after_state={"label_removed": label_id},
            )

    async def get_work_item_label_ids(
        self,
        session: AsyncSession,
        work_item_id: str,
    ) -> List[str]:
        result = await session.execute(
            select(LLCWorkItemLabel.label_id).where(LLCWorkItemLabel.work_item_id == uuid.UUID(work_item_id))
        )
        return [str(r) for r in result.scalars().all()]


def _label_to_dict(label: LLCLabel) -> Dict[str, Any]:
    return {
        "id": str(label.id),
        "company_id": str(label.company_id),
        "name": label.name,
        "color": label.color,
        "description": label.description,
        "created_at": label.created_at.isoformat() if label.created_at else None,
        "created_by": label.created_by,
    }
