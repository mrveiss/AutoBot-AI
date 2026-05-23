# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""ProjectService — CRUD for LLCProject (GH#8219)."""

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.project import LLCProject
from . import LLCServiceBase

logger = get_logger(__name__)


class ProjectService(LLCServiceBase):
    """CRUD operations for LLCProject (GH#8219)."""

    async def create(
        self,
        session: AsyncSession,
        program_id: uuid.UUID,
        name: str,
        *,
        description: Optional[str] = None,
        status: str = "active",
        owner_agent_id: Optional[str] = None,
    ) -> LLCProject:
        project = LLCProject(
            program_id=program_id,
            name=name,
            description=description,
            status=status,
            owner_agent_id=owner_agent_id,
        )
        session.add(project)
        await session.flush()
        logger.info("Created project %s under program %s", project.id, program_id)
        return project

    async def get(self, session: AsyncSession, project_id: uuid.UUID) -> Optional[LLCProject]:
        result = await session.execute(
            select(LLCProject).where(LLCProject.id == project_id)
        )
        return result.scalar_one_or_none()

    async def list_by_program(
        self, session: AsyncSession, program_id: uuid.UUID, status: Optional[str] = None
    ) -> List[LLCProject]:
        q = select(LLCProject).where(LLCProject.program_id == program_id)
        if status is not None:
            q = q.where(LLCProject.status == status)
        q = q.order_by(LLCProject.created_at.asc())
        result = await session.execute(q)
        return list(result.scalars().all())

    async def update(
        self, session: AsyncSession, project_id: uuid.UUID, **kwargs: object
    ) -> Optional[LLCProject]:
        project = await self.get(session, project_id)
        if project is None:
            return None
        for key, value in kwargs.items():
            setattr(project, key, value)
        await session.flush()
        return project

    async def delete(self, session: AsyncSession, project_id: uuid.UUID) -> bool:
        project = await self.get(session, project_id)
        if project is None:
            return False
        await session.delete(project)
        await session.flush()
        return True
