"""LLC WorkItemRelationService — add/remove work-item relations (GH#8252).

Mirror invariant: adding ``blocks`` A→B automatically creates ``blocked_by`` B→A.
Removing either leg (by relation id) removes both.

Transition guard (enforced in WorkItemService.transition_status):
  An item in ``blocked`` status cannot transition to ``in_progress`` while it has
  at least one ``blocked_by`` relation whose source item is not ``done`` or ``cancelled``.
"""

import logging
import uuid
from typing import Optional, Sequence

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import ActivityEventType, WorkItemRelationType, WorkItemStatus
from ..models.work_item import LLCWorkItem, LLCWorkItemRelation
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_MIRROR = {
    WorkItemRelationType.BLOCKS: WorkItemRelationType.BLOCKED_BY,
    WorkItemRelationType.BLOCKED_BY: WorkItemRelationType.BLOCKS,
}


class RelationConflict(Exception):
    """Raised when a relation already exists or would create a self-loop."""


class WorkItemRelationService(LLCServiceBase):
    """Service for LLC work item relation management."""

    async def add(
        self,
        session: AsyncSession,
        *,
        company_id: str,
        source_id: str,
        target_id: str,
        relation_type: WorkItemRelationType,
        created_by_agent_id: Optional[str] = None,
        created_by_user_id: Optional[str] = None,
    ) -> LLCWorkItemRelation:
        """Add a relation; if type is ``blocks`` also inserts the mirror ``blocked_by``."""
        src = uuid.UUID(source_id)
        tgt = uuid.UUID(target_id)
        cid = uuid.UUID(company_id)

        if src == tgt:
            raise RelationConflict("source_id and target_id must differ")

        relation = await self._insert_one(
            session,
            company_id=cid,
            source_id=src,
            target_id=tgt,
            relation_type=relation_type,
            created_by_agent_id=uuid.UUID(created_by_agent_id) if created_by_agent_id else None,
            created_by_user_id=uuid.UUID(created_by_user_id) if created_by_user_id else None,
        )

        if relation_type in _MIRROR:
            await self._insert_one(
                session,
                company_id=cid,
                source_id=tgt,
                target_id=src,
                relation_type=_MIRROR[relation_type],
                created_by_agent_id=uuid.UUID(created_by_agent_id) if created_by_agent_id else None,
                created_by_user_id=uuid.UUID(created_by_user_id) if created_by_user_id else None,
            )

        await session.flush()

        if self.activity_log:
            await self.activity_log.record(
                session,
                event_type=ActivityEventType.WORK_ITEM_RELATION_ADDED,
                company_id=company_id,
                entity_type="work_item",
                entity_id=source_id,
                actor_agent_id=created_by_agent_id,
                actor_user_id=created_by_user_id,
                metadata={
                    "relation_id": str(relation.id),
                    "relation_type": relation_type.value,
                    "target_id": target_id,
                },
            )

        return relation

    async def remove(
        self,
        session: AsyncSession,
        *,
        company_id: str,
        relation_id: str,
        actor_agent_id: Optional[str] = None,
        actor_user_id: Optional[str] = None,
    ) -> None:
        """Remove a relation by id; removes the mirror leg if present."""
        result = await session.execute(
            select(LLCWorkItemRelation).where(
                LLCWorkItemRelation.id == uuid.UUID(relation_id),
                LLCWorkItemRelation.company_id == uuid.UUID(company_id),
            )
        )
        relation = result.scalar_one_or_none()
        if relation is None:
            raise ValueError(f"Relation {relation_id} not found")

        source_id = str(relation.source_id)
        target_id = str(relation.target_id)
        rtype = WorkItemRelationType(relation.relation_type)

        await session.delete(relation)

        if rtype in _MIRROR:
            mirror_result = await session.execute(
                select(LLCWorkItemRelation).where(
                    LLCWorkItemRelation.source_id == relation.target_id,
                    LLCWorkItemRelation.target_id == relation.source_id,
                    LLCWorkItemRelation.relation_type == _MIRROR[rtype].value,
                    LLCWorkItemRelation.company_id == uuid.UUID(company_id),
                )
            )
            mirror = mirror_result.scalar_one_or_none()
            if mirror is not None:
                await session.delete(mirror)

        await session.flush()

        if self.activity_log:
            await self.activity_log.record(
                session,
                event_type=ActivityEventType.WORK_ITEM_RELATION_REMOVED,
                company_id=company_id,
                entity_type="work_item",
                entity_id=source_id,
                actor_agent_id=actor_agent_id,
                actor_user_id=actor_user_id,
                metadata={
                    "relation_id": relation_id,
                    "relation_type": rtype.value,
                    "target_id": target_id,
                },
            )

    async def list_for_item(
        self,
        session: AsyncSession,
        work_item_id: str,
        company_id: str,
    ) -> Sequence[LLCWorkItemRelation]:
        """Return all relations where the item is source or target."""
        wid = uuid.UUID(work_item_id)
        cid = uuid.UUID(company_id)
        result = await session.execute(
            select(LLCWorkItemRelation).where(
                LLCWorkItemRelation.company_id == cid,
                sa.or_(
                    LLCWorkItemRelation.source_id == wid,
                    LLCWorkItemRelation.target_id == wid,
                ),
            )
        )
        return result.scalars().all()

    async def has_unresolved_blockers(
        self,
        session: AsyncSession,
        work_item_id: str,
        company_id: str,
    ) -> bool:
        """Return True if item has any ``blocked_by`` relation whose source is not done/cancelled."""
        wid = uuid.UUID(work_item_id)
        cid = uuid.UUID(company_id)
        terminal = {WorkItemStatus.DONE.value, WorkItemStatus.CANCELLED.value}

        result = await session.execute(
            select(LLCWorkItemRelation)
            .join(LLCWorkItem, LLCWorkItem.id == LLCWorkItemRelation.source_id)
            .where(
                LLCWorkItemRelation.company_id == cid,
                LLCWorkItemRelation.target_id == wid,
                LLCWorkItemRelation.relation_type == WorkItemRelationType.BLOCKED_BY.value,
                LLCWorkItem.status.notin_(terminal),
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _insert_one(
        self,
        session: AsyncSession,
        *,
        company_id: uuid.UUID,
        source_id: uuid.UUID,
        target_id: uuid.UUID,
        relation_type: WorkItemRelationType,
        created_by_agent_id: Optional[uuid.UUID],
        created_by_user_id: Optional[uuid.UUID],
    ) -> LLCWorkItemRelation:
        existing = await session.execute(
            select(LLCWorkItemRelation).where(
                LLCWorkItemRelation.source_id == source_id,
                LLCWorkItemRelation.target_id == target_id,
                LLCWorkItemRelation.relation_type == relation_type.value,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise RelationConflict(f"Relation {relation_type.value} from {source_id} to {target_id} already exists")
        rel = LLCWorkItemRelation(
            id=uuid.uuid4(),
            company_id=company_id,
            source_id=source_id,
            target_id=target_id,
            relation_type=relation_type,
            created_by_agent_id=created_by_agent_id,
            created_by_user_id=created_by_user_id,
        )
        session.add(rel)
        return rel
