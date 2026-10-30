# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC company membership service (GH#8223).

Manages human-user membership within an LLC company.
Only members (any role) may claim work items as human assignees.
"""

import logging
import uuid
from typing import Any, Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.activity import ActorType
from ..models.enums import ActivityEventType, MembershipRole
from ..models.membership import LLCCompanyMembership
from .base import LLCServiceBase

logger = logging.getLogger(__name__)


class MemberAlreadyExistsError(Exception):
    """Raised when a membership already exists for (company, user)."""


class MemberNotFoundError(Exception):
    """Raised when a membership does not exist for (company, user)."""


class MembershipService(LLCServiceBase):
    """Service for LLC company membership management."""

    async def _log(
        self, session: AsyncSession, company_id: str, actor_id: str, event: Any, entity_id: str, **change: Any
    ) -> None:
        """Audit one change, in the caller's transaction: a change that cannot be audited does not commit."""
        if self.activity_log:
            await self.activity_log.record(
                session,
                company_id=company_id,
                actor_type=ActorType.USER,
                actor_id=actor_id,
                event_type=event,
                entity_type="membership",
                entity_id=entity_id,
                **change,
            )

    async def add_member(
        self,
        session: AsyncSession,
        company_id: str,
        user_id: str,
        role: MembershipRole = MembershipRole.MEMBER,
        actor_id: Optional[str] = None,
    ) -> LLCCompanyMembership:
        """Add a user to a company. Raises MemberAlreadyExistsError on conflict.

        *actor_id* is who did it; with none given, the user is adding themselves (company creation).
        """
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
        await self._log(
            session,
            company_id,
            actor_id or user_id,
            ActivityEventType.AGENT_ASSIGNED,
            str(membership.id),
            after={"user_id": user_id, "role": role.value},
        )
        return membership

    async def change_role(
        self, session: AsyncSession, company_id: str, user_id: str, role: MembershipRole, actor_id: str
    ) -> LLCCompanyMembership:
        """Change a member's role in place. Raises MemberNotFoundError if absent."""
        existing = await self.get_member(session, company_id, user_id)
        if existing is None:
            raise MemberNotFoundError(f"User {user_id} is not a member of company {company_id}")
        before = str(getattr(existing.role, "value", existing.role))
        existing.role = role
        await session.flush()
        await self._log(
            session,
            company_id,
            actor_id,
            ActivityEventType.AGENT_ASSIGNED,
            str(existing.id),
            before={"user_id": user_id, "role": before},
            after={"user_id": user_id, "role": role.value},
        )
        return existing

    async def remove_member(
        self,
        session: AsyncSession,
        company_id: str,
        user_id: str,
        actor_id: Optional[str] = None,
    ) -> None:
        """Remove a user from a company. Raises MemberNotFoundError if absent."""
        existing = await self.get_member(session, company_id, user_id)
        if existing is None:
            raise MemberNotFoundError(f"User {user_id} is not a member of company {company_id}")
        await self._log(
            session,
            company_id,
            actor_id or user_id,
            ActivityEventType.AGENT_UNASSIGNED,
            str(existing.id),
            before={"user_id": user_id, "role": str(getattr(existing.role, "value", existing.role))},
        )
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

    async def list_member_company_ids(
        self,
        session: AsyncSession,
        user_id: str,
    ) -> set[uuid.UUID]:
        """Return the set of company ids *user_id* is a member of (#12325).

        A single ``SELECT company_id ... WHERE user_id = :uid`` — the caller
        filters candidate companies against this set in memory, replacing an
        ``is_member`` round-trip per company (an N+1 that scaled with the total
        system-wide tenant count, not the caller's own memberships).
        """
        result = await session.execute(
            select(LLCCompanyMembership.company_id).where(
                LLCCompanyMembership.user_id == uuid.UUID(user_id),
            )
        )
        return {row[0] for row in result.all()}
