# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""ProgramService — CRUD for LLCProgram (GH#8219)."""

import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.program import LLCProgram
from . import LLCServiceBase

logger = get_logger(__name__)


class ProgramService(LLCServiceBase):
    """CRUD operations for LLCProgram (GH#8219)."""

    async def create(
        self,
        session: AsyncSession,
        portfolio_id: uuid.UUID,
        name: str,
        *,
        description: Optional[str] = None,
        status: str = "active",
    ) -> LLCProgram:
        program = LLCProgram(
            portfolio_id=portfolio_id,
            name=name,
            description=description,
            status=status,
        )
        session.add(program)
        await session.flush()
        logger.info("Created program %s under portfolio %s", program.id, portfolio_id)
        return program

    async def get(self, session: AsyncSession, program_id: uuid.UUID) -> Optional[LLCProgram]:
        result = await session.execute(
            select(LLCProgram).where(LLCProgram.id == program_id)
        )
        return result.scalar_one_or_none()

    async def list_by_portfolio(
        self, session: AsyncSession, portfolio_id: uuid.UUID, status: Optional[str] = None
    ) -> List[LLCProgram]:
        q = select(LLCProgram).where(LLCProgram.portfolio_id == portfolio_id)
        if status is not None:
            q = q.where(LLCProgram.status == status)
        q = q.order_by(LLCProgram.created_at.asc())
        result = await session.execute(q)
        return list(result.scalars().all())

    async def update(
        self, session: AsyncSession, program_id: uuid.UUID, **kwargs: object
    ) -> Optional[LLCProgram]:
        program = await self.get(session, program_id)
        if program is None:
            return None
        for key, value in kwargs.items():
            setattr(program, key, value)
        await session.flush()
        return program

    async def delete(self, session: AsyncSession, program_id: uuid.UUID) -> bool:
        program = await self.get(session, program_id)
        if program is None:
            return False
        await session.delete(program)
        await session.flush()
        return True
