# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC GoalService — CRUD, ancestry traversal, KB indexing (GH#8212)."""

import asyncio
import uuid
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import delete, event, select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.goal import GoalLevel, GoalStatus, LLCGoal
from .base import LLCServiceBase

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


def _as_goal_level(value: Any) -> GoalLevel:
    """Coerce a string or GoalLevel to GoalLevel enum."""
    if isinstance(value, GoalLevel):
        return value
    return GoalLevel(value)


def _validate_level_order(child_level: GoalLevel, parent_level: GoalLevel) -> None:
    """Raise 422 if child_level is not exactly one step below parent_level."""
    parent_idx = _GOAL_LEVEL_ORDER.index(parent_level)
    expected_idx = parent_idx + 1
    if expected_idx >= len(_GOAL_LEVEL_ORDER):
        raise HTTPException(
            status_code=422,
            detail=f"A '{parent_level.value}' goal cannot have children (it is the deepest level)",
        )
    expected = _GOAL_LEVEL_ORDER[expected_idx]
    if child_level != expected:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid level hierarchy: a child of '{parent_level.value}' must be "
                f"'{expected.value}', not '{child_level.value}'"
            ),
        )


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
        # Fix #3: Validate level hierarchy when parent is set
        if parent_goal_id is not None:
            parent = await self.get(session, parent_goal_id)
            if parent is None:
                raise HTTPException(status_code=404, detail="Parent goal not found")
            _validate_level_order(level, _as_goal_level(parent.level))

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
        # Fix #2: Index after commit, not after flush, to avoid phantom entries on rollback
        self._schedule_post_commit_index(session, goal)
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

    async def get(self, session: AsyncSession, goal_id: uuid.UUID) -> Optional[LLCGoal]:
        result = await session.execute(select(LLCGoal).where(LLCGoal.id == goal_id))
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

        # Resolve effective parent (may be new or unchanged)
        parent: Optional[LLCGoal] = None
        if "parent_goal_id" in fields:
            new_parent_id = fields["parent_goal_id"]
            if new_parent_id is not None:
                parent = await self.get(session, new_parent_id)
                if parent is None:
                    raise HTTPException(status_code=404, detail="Parent goal not found")
                # Fix #1: Reject cross-tenant parent assignment
                if parent.company_id != goal.company_id:
                    raise HTTPException(
                        status_code=400,
                        detail="Parent goal belongs to a different company",
                    )
        elif goal.parent_goal_id is not None:
            parent = await self.get(session, goal.parent_goal_id)

        # Fix #3: Validate level hierarchy when parent or level is changing
        if "parent_goal_id" in fields or "level" in fields:
            new_level = _as_goal_level(fields.get("level", goal.level))
            if parent is not None:
                _validate_level_order(new_level, _as_goal_level(parent.level))

        allowed = {
            "title",
            "description",
            "level",
            "status",
            "owner_agent_id",
            "due_date",
            "parent_goal_id",
        }
        for key, value in fields.items():
            if key in allowed:
                if isinstance(value, (GoalLevel, GoalStatus)):
                    setattr(goal, key, value.value)
                else:
                    setattr(goal, key, value)
        await session.flush()
        # Fix #2: Index after commit, not after flush
        self._schedule_post_commit_index(session, goal)
        return goal

    async def delete(self, session: AsyncSession, goal_id: uuid.UUID) -> bool:
        # Fix #4: Collect subtree IDs before deletion so ChromaDB can be cleaned up
        subtree = await self.get_subtree(session, goal_id)
        if not subtree:
            return False

        company_id = subtree[0].company_id
        subtree_ids = [str(g.id) for g in subtree]

        result = await session.execute(delete(LLCGoal).where(LLCGoal.id == goal_id))
        if result.rowcount == 0:
            return False

        # Fix #4: Remove ChromaDB entries for goal and entire subtree after commit
        self._schedule_post_commit_chromadb_delete(session, company_id, subtree_ids)
        return True

    # ----------------------------------------------------------- Traversal

    async def get_ancestors(self, session: AsyncSession, goal_id: uuid.UUID) -> List[LLCGoal]:
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

    async def get_goal_ancestry_for_work_item(
        self,
        session: AsyncSession,
        goal_id: uuid.UUID,
    ) -> List[dict]:
        """Return root-first goal ancestry chain for a goal_id (GH#6469).

        Includes the goal itself as the last element.  Returns plain dicts
        (``id``, ``title``, ``level``, ``status``) so callers avoid importing
        LLCGoal.  Returns ``[]`` when the goal is not found.
        """
        goal = await self.get(session, goal_id)
        if goal is None:
            return []
        ancestors = await self.get_ancestors(session, goal_id)
        chain = ancestors + [goal]
        return [
            {
                "id": str(g.id),
                "title": g.title,
                "level": g.level,
                "status": g.status,
            }
            for g in chain
        ]

    async def get_subtree(self, session: AsyncSession, goal_id: uuid.UUID) -> List[LLCGoal]:
        """Return all descendants of goal_id (BFS, inclusive of goal_id)."""
        root = await self.get(session, goal_id)
        if root is None:
            return []
        result: List[LLCGoal] = [root]
        queue: List[LLCGoal] = [root]
        visited: set = {goal_id}
        while queue:
            node = queue.pop(0)
            children_result = await session.execute(select(LLCGoal).where(LLCGoal.parent_goal_id == node.id))
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
            collection = await client.get_or_create_collection(_goal_collection_name(goal.company_id))
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
            logger.exception("Failed to index goal %s into KB — non-fatal", goal.id)

    async def _delete_from_chromadb(self, company_id: str, ids: List[str]) -> None:
        """Remove goal entries from the company-scoped KB collection."""
        try:
            from utils.async_chromadb_client import get_async_chromadb_client

            client = await get_async_chromadb_client()
            collection = await client.get_or_create_collection(_goal_collection_name(company_id))
            await collection.delete(ids=ids)
        except Exception:
            logger.exception("Failed to remove goals %s from KB — non-fatal", ids)

    def _schedule_post_commit_index(self, session: AsyncSession, goal: LLCGoal) -> None:
        """Register ChromaDB indexing to fire after DB commit (not after flush)."""
        goal_ref = goal
        svc_ref = self

        try:
            sync_sess = session.sync_session
        except AttributeError:
            return  # Not a real AsyncSession (e.g. test mock); skip registration

        @event.listens_for(sync_sess, "after_commit", once=True)
        def _after_commit(ss: Any) -> None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(svc_ref._index_goal(goal_ref))
            except Exception:
                logger.exception("Could not schedule goal indexing post-commit for %s", goal_ref.id)

    def _schedule_post_commit_chromadb_delete(self, session: AsyncSession, company_id: str, ids: List[str]) -> None:
        """Register ChromaDB bulk delete to fire after DB commit."""
        svc_ref = self

        try:
            sync_sess = session.sync_session
        except AttributeError:
            return

        @event.listens_for(sync_sess, "after_commit", once=True)
        def _after_commit(ss: Any) -> None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(svc_ref._delete_from_chromadb(company_id, ids))
            except Exception:
                logger.exception("Could not schedule ChromaDB cleanup post-commit for goals %s", ids)
