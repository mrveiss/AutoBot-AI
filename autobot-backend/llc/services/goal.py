# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC GoalService — CRUD, ancestry traversal, KB indexing (GH#8212)."""

import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.goal import GoalLevel, GoalStatus, LLCGoal
from . import LLCServiceBase

logger = get_logger(__name__)

_GOAL_LEVEL_ORDER = [
    GoalLevel.VISION,
    GoalLevel.MISSION,
    GoalLevel.OBJECTIVE,
    GoalLevel.KEY_RESULT,
]

_GOAL_COLLECTION_SUFFIX = "llc_goals"


def _goal_collection_name(company_id: str) -> str:
    return f"{company_id}_{_GOAL_COLLECTION_SUFFIX}"


class GoalService(LLCServiceBase):
    """CRUD + traversal + KB indexing for LLCGoal rows (GH#8212)."""

    # ------------------------------------------------------------------ CRUD

    async def create(
        self,
        session: AsyncSession,
        company_id: str,
        title: str,
        level: GoalLevel,
        *,
        description: Optional[str] = None,
        parent_goal_id: Optional[uuid.UUID] = None,
        owner_agent_id: Optional[str] = None,
        due_date: Optional[Any] = None,
        status: GoalStatus = GoalStatus.DRAFT,
    ) -> LLCGoal:
        goal = LLCGoal(
            company_id=company_id,
            parent_goal_id=parent_goal_id,
            title=title,
            description=description,
            level=level.value,
            status=status.value,
            owner_agent_id=owner_agent_id,
            due_date=due_date,
        )
        session.add(goal)
        await session.flush()
        await self._index_goal(goal)
        if self.activity_log:
            await self.activity_log.record(
                session,
                company_id=company_id,
                actor_id=owner_agent_id or "system",
                event_type="goal.created",
                entity_type="llc_goal",
                entity_id=str(goal.id),
                after={"title": title, "level": level.value, "status": status.value},
            )
        return goal

    async def get(
        self, session: AsyncSession, goal_id: uuid.UUID
    ) -> Optional[LLCGoal]:
        result = await session.execute(
            select(LLCGoal).where(LLCGoal.id == goal_id)
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self,
        session: AsyncSession,
        company_id: str,
        parent_goal_id: Optional[uuid.UUID] = None,
    ) -> List[LLCGoal]:
        stmt = select(LLCGoal).where(LLCGoal.company_id == company_id)
        if parent_goal_id is not None:
            stmt = stmt.where(LLCGoal.parent_goal_id == parent_goal_id)
        else:
            stmt = stmt.where(LLCGoal.parent_goal_id.is_(None))
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update(
        self,
        session: AsyncSession,
        goal_id: uuid.UUID,
        **fields: Any,
    ) -> Optional[LLCGoal]:
        goal = await self.get(session, goal_id)
        if goal is None:
            return None
        allowed = {
            "title", "description", "level", "status",
            "owner_agent_id", "due_date", "parent_goal_id",
        }
        for key, value in fields.items():
            if key in allowed:
                if isinstance(value, (GoalLevel, GoalStatus)):
                    setattr(goal, key, value.value)
                else:
                    setattr(goal, key, value)
        await session.flush()
        await self._index_goal(goal)
        return goal

    async def delete(
        self, session: AsyncSession, goal_id: uuid.UUID
    ) -> bool:
        result = await session.execute(
            delete(LLCGoal).where(LLCGoal.id == goal_id)
        )
        return result.rowcount > 0

    # ----------------------------------------------------------- Traversal

    async def get_ancestors(
        self, session: AsyncSession, goal_id: uuid.UUID
    ) -> List[LLCGoal]:
        """Walk parent chain from goal_id up to the root (exclusive of goal_id)."""
        ancestors: List[LLCGoal] = []
        current_id: Optional[uuid.UUID] = goal_id
        visited: set = set()
        while current_id is not None:
            if current_id in visited:
                logger.warning("Cycle detected in goal ancestry at %s", current_id)
                break
            visited.add(current_id)
            goal = await self.get(session, current_id)
            if goal is None:
                break
            if current_id != goal_id:
                ancestors.append(goal)
            current_id = goal.parent_goal_id
        return list(reversed(ancestors))

    async def get_subtree(
        self, session: AsyncSession, goal_id: uuid.UUID
    ) -> List[LLCGoal]:
        """Return all descendants of goal_id (BFS, inclusive of goal_id)."""
        root = await self.get(session, goal_id)
        if root is None:
            return []
        result: List[LLCGoal] = [root]
        queue: List[LLCGoal] = [root]
        visited: set = {goal_id}
        while queue:
            node = queue.pop(0)
            children_result = await session.execute(
                select(LLCGoal).where(LLCGoal.parent_goal_id == node.id)
            )
            for child in children_result.scalars().all():
                if child.id not in visited:
                    visited.add(child.id)
                    result.append(child)
                    queue.append(child)
        return result

    # --------------------------------------------------------- KB indexing

    async def _index_goal(self, goal: LLCGoal) -> None:
        """Index goal text into the company-scoped goal KB collection."""
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            collection = await client.get_or_create_collection(
                _goal_collection_name(goal.company_id)
            )
            doc_id = str(goal.id)
            text = f"{goal.title}\n{goal.description or ''}".strip()
            metadata: Dict[str, Any] = {
                "company_id": goal.company_id,
                "level": goal.level,
                "status": goal.status,
                "owner_agent_id": goal.owner_agent_id or "",
            }
            await collection.upsert(
                ids=[doc_id],
                documents=[text],
                metadatas=[metadata],
            )
        except Exception:
            logger.exception(
                "Failed to index goal %s into KB — non-fatal", goal.id
            )
