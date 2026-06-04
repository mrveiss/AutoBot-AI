# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC company membership service (GH#8223).

Manages human-user membership within an LLC company.
Only members (any role) may claim work items as human assignees.
"""

import logging
import uuid
from typing import Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import MembershipRole
from ..models.membership import LLCCompanyMembership
from .base import LLCServiceBase

logger = logging.getLogger(__name__)


class MemberAlreadyExistsError(Exception):
    """Raised when a membership already exists for (company, user)."""


class MemberNotFoundError(Exception):
    """Raised when a membership does not exist for (company, user)."""


class MembershipService(LLCServiceBase):
    """Service for LLC company membership management."""

    async def add_member(
        self,
        session: AsyncSession,
        company_id: str,
        user_id: str,
        role: MembershipRole = MembershipRole.MEMBER,
    ) -> LLCCompanyMembership:
        """Add a user to a company. Raises MemberAlreadyExistsError on conflict."""
        existing = await self.get_member(session, company_id, user_id)
        if existing is not None:
            raise MemberAlreadyExistsError(f"User {user_id} is already a member of company {company_id}")
        membership = LLCCompanyMembership(
            id=uuid.uuid4(),
            company_id=uuid.UUID(company_id),
            user_id=uuid.UUID(user_id),
            role=role,
        )
        session.add(membership)
        await session.flush()

        if self.activity_log:
            try:
                from ..models.enums import ActivityEventType

                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_id=user_id,
                    event_type=ActivityEventType.AGENT_ASSIGNED,
                    entity_type="membership",
                    entity_id=str(membership.id),
                    after={"user_id": user_id, "role": role.value},
                )
            except Exception:
                logger.warning("Activity log failed for add_member %s/%s", company_id, user_id)

        return membership

    async def remove_member(
        self,
        session: AsyncSession,
        company_id: str,
        user_id: str,
    ) -> None:
        """Remove a user from a company. Raises MemberNotFoundError if absent."""
        existing = await self.get_member(session, company_id, user_id)
        if existing is None:
            raise MemberNotFoundError(f"User {user_id} is not a member of company {company_id}")

        if self.activity_log:
            try:
                from ..models.enums import ActivityEventType

                await self.activity_log.record(
                    session,
                    company_id=company_id,
                    actor_id=user_id,
                    event_type=ActivityEventType.AGENT_UNASSIGNED,
                    entity_type="membership",
                    entity_id=str(existing.id),
                    before={"user_id": user_id, "role": existing.role},
                )
            except Exception:
                logger.warning("Activity log failed for remove_member %s/%s", company_id, user_id)

        await session.execute(
            delete(LLCCompanyMembership).where(
                LLCCompanyMembership.company_id == uuid.UUID(company_id),
                LLCCompanyMembership.user_id == uuid.UUID(user_id),
            )
        )
        await session.flush()

    async def get_member(
        self,
        session: AsyncSession,
        company_id: str,
        user_id: str,
    ) -> Optional[LLCCompanyMembership]:
        result = await session.execute(
            select(LLCCompanyMembership).where(
                LLCCompanyMembership.company_id == uuid.UUID(company_id),
                LLCCompanyMembership.user_id == uuid.UUID(user_id),
            )
        )
        return result.scalar_one_or_none()

    async def list_members(
        self,
        session: AsyncSession,
        company_id: str,
    ) -> Sequence[LLCCompanyMembership]:
        result = await session.execute(
            select(LLCCompanyMembership)
            .where(LLCCompanyMembership.company_id == uuid.UUID(company_id))
            .order_by(LLCCompanyMembership.created_at)
        )
        return result.scalars().all()

    async def is_member(
        self,
        session: AsyncSession,
        company_id: str,
        user_id: str,
    ) -> bool:
        m = await self.get_member(session, company_id, user_id)
        return m is not None
