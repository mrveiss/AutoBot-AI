# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""SprintService — CRUD + start/close transitions for LLCSprint (GH#8219)."""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.enums import SprintStatus
from ..models.sprint import LLCSprint
from . import LLCServiceBase

logger = get_logger(__name__)

_VALID_STARTS = {SprintStatus.PLANNING}
_VALID_CLOSES = {SprintStatus.ACTIVE, SprintStatus.REVIEW, SprintStatus.RETROSPECTIVE}


class SprintService(LLCServiceBase):
    """CRUD + lifecycle transitions for LLCSprint (GH#8219)."""

    async def create(
        self,
        session: AsyncSession,
        project_id: uuid.UUID,
        name: str,
        *,
        status: SprintStatus = SprintStatus.PLANNING,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        capacity_points: Optional[int] = None,
    ) -> LLCSprint:
        sprint = LLCSprint(
            project_id=project_id,
            name=name,
            status=status.value,
            start_date=start_date,
            end_date=end_date,
            capacity_points=capacity_points,
        )
        session.add(sprint)
        await session.flush()
        logger.info("Created sprint %s under project %s", sprint.id, project_id)
        return sprint

    async def get(self, session: AsyncSession, sprint_id: uuid.UUID) -> Optional[LLCSprint]:
        result = await session.execute(
            select(LLCSprint).where(LLCSprint.id == sprint_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(
        self, session: AsyncSession, project_id: uuid.UUID, status: Optional[str] = None
    ) -> List[LLCSprint]:
        q = select(LLCSprint).where(LLCSprint.project_id == project_id)
        if status is not None:
            q = q.where(LLCSprint.status == status)
        q = q.order_by(LLCSprint.created_at.asc())
        result = await session.execute(q)
        return list(result.scalars().all())

    async def update(
        self, session: AsyncSession, sprint_id: uuid.UUID, **kwargs: object
    ) -> Optional[LLCSprint]:
        sprint = await self.get(session, sprint_id)
        if sprint is None:
            return None
        for key, value in kwargs.items():
            setattr(sprint, key, value)
        await session.flush()
        return sprint

    async def delete(self, session: AsyncSession, sprint_id: uuid.UUID) -> bool:
        sprint = await self.get(session, sprint_id)
        if sprint is None:
            return False
        await session.delete(sprint)
        await session.flush()
        return True

    async def start(self, session: AsyncSession, sprint_id: uuid.UUID) -> LLCSprint:
        """Transition sprint from planning → active."""
        sprint = await self.get(session, sprint_id)
        if sprint is None:
            raise HTTPException(status_code=404, detail="Sprint not found")
        current = SprintStatus(sprint.status)
        if current not in _VALID_STARTS:
            raise HTTPException(
                status_code=422,
                detail=f"Cannot start sprint in status '{sprint.status}'; must be 'planning'",
            )
        sprint.status = SprintStatus.ACTIVE.value
        if sprint.start_date is None:
            sprint.start_date = datetime.now(timezone.utc)
        await session.flush()
        logger.info("Started sprint %s", sprint_id)
        return sprint

    async def close(
        self, session: AsyncSession, sprint_id: uuid.UUID, velocity_actual: Optional[int] = None
    ) -> LLCSprint:
        """Transition sprint to closed; optionally record actual velocity."""
        sprint = await self.get(session, sprint_id)
        if sprint is None:
            raise HTTPException(status_code=404, detail="Sprint not found")
        current = SprintStatus(sprint.status)
        if current not in _VALID_CLOSES:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Cannot close sprint in status '{sprint.status}'; "
                    "must be active, review, or retrospective"
                ),
            )
        sprint.status = SprintStatus.CLOSED.value
        if velocity_actual is not None:
            sprint.velocity_actual = velocity_actual
        if sprint.end_date is None:
            sprint.end_date = datetime.now(timezone.utc)
        await session.flush()
        logger.info("Closed sprint %s (velocity=%s)", sprint_id, velocity_actual)
        return sprint
