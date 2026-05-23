# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""PortfolioService — CRUD for LLCPortfolio (GH#8219)."""

import uuid
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger

from ..models.portfolio import LLCPortfolio
from . import LLCServiceBase

logger = get_logger(__name__)


class PortfolioService(LLCServiceBase):
    """CRUD operations for LLCPortfolio (GH#8219)."""

    async def create(
        self,
        session: AsyncSession,
        company_id: str,
        name: str,
        *,
        description: Optional[str] = None,
        status: str = "active",
    ) -> LLCPortfolio:
        portfolio = LLCPortfolio(
            company_id=company_id,
            name=name,
            description=description,
            status=status,
        )
        session.add(portfolio)
        await session.flush()
        logger.info("Created portfolio %s for company %s", portfolio.id, company_id)
        return portfolio

    async def get(self, session: AsyncSession, portfolio_id: uuid.UUID) -> Optional[LLCPortfolio]:
        result = await session.execute(
            select(LLCPortfolio).where(LLCPortfolio.id == portfolio_id)
        )
        return result.scalar_one_or_none()

    async def list_by_company(
        self, session: AsyncSession, company_id: str, status: Optional[str] = None
    ) -> List[LLCPortfolio]:
        q = select(LLCPortfolio).where(LLCPortfolio.company_id == company_id)
        if status is not None:
            q = q.where(LLCPortfolio.status == status)
        q = q.order_by(LLCPortfolio.created_at.asc())
        result = await session.execute(q)
        return list(result.scalars().all())

    async def update(
        self, session: AsyncSession, portfolio_id: uuid.UUID, **kwargs: object
    ) -> Optional[LLCPortfolio]:
        portfolio = await self.get(session, portfolio_id)
        if portfolio is None:
            return None
        for key, value in kwargs.items():
            setattr(portfolio, key, value)
        await session.flush()
        return portfolio

    async def delete(self, session: AsyncSession, portfolio_id: uuid.UUID) -> bool:
        portfolio = await self.get(session, portfolio_id)
        if portfolio is None:
            return False
        await session.delete(portfolio)
        await session.flush()
        return True
