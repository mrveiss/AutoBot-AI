# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC ReviewGatePolicyService — per-company, per-item-type human review gates (GH#8234).

Default policy: bug → requires_human_review=True, all others → False.
Call seed_defaults(session, company_id) on company creation to install these.
"""

import logging
import uuid
from typing import Optional, Sequence

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.enums import WorkItemType
from ..models.review_gate import LLCReviewGatePolicy
from .base import LLCServiceBase

logger = logging.getLogger(__name__)

_DEFAULT_POLICIES: dict[WorkItemType, bool] = {
    WorkItemType.BUG: True,
}


class ReviewGatePolicyNotFoundError(Exception):
    """Raised when the requested policy does not exist."""


class ReviewGatePolicyConflictError(Exception):
    """Raised when a policy already exists for (company_id, item_type)."""


class ReviewGatePolicyService(LLCServiceBase):
    """CRUD + query service for llc_review_gate_policies."""

    async def create_policy(
        self,
        session: AsyncSession,
        company_id: str,
        item_type: WorkItemType,
        *,
        requires_human_review: bool = False,
        reviewer_role: Optional[str] = None,
    ) -> LLCReviewGatePolicy:
        """Create a review gate policy. Raises ReviewGatePolicyConflictError on duplicate."""
        policy = LLCReviewGatePolicy(
            id=uuid.uuid4(),
            company_id=uuid.UUID(company_id),
            item_type=item_type,
            requires_human_review=requires_human_review,
            reviewer_role=reviewer_role,
        )
        session.add(policy)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise ReviewGatePolicyConflictError(
                f"Policy already exists for company {company_id} / item_type {item_type.value}"
            )
        return policy

    async def get_policy(
        self,
        session: AsyncSession,
        company_id: str,
        item_type: WorkItemType,
    ) -> Optional[LLCReviewGatePolicy]:
        """Return the policy for (company_id, item_type) or None."""
        result = await session.execute(
            select(LLCReviewGatePolicy).where(
                LLCReviewGatePolicy.company_id == uuid.UUID(company_id),
                LLCReviewGatePolicy.item_type == item_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_policy_by_id(
        self,
        session: AsyncSession,
        policy_id: str,
    ) -> Optional[LLCReviewGatePolicy]:
        result = await session.execute(
            select(LLCReviewGatePolicy).where(LLCReviewGatePolicy.id == uuid.UUID(policy_id))
        )
        return result.scalar_one_or_none()

    async def list_policies(
        self,
        session: AsyncSession,
        company_id: str,
    ) -> Sequence[LLCReviewGatePolicy]:
        result = await session.execute(
            select(LLCReviewGatePolicy)
            .where(LLCReviewGatePolicy.company_id == uuid.UUID(company_id))
            .order_by(LLCReviewGatePolicy.item_type)
        )
        return result.scalars().all()

    async def update_policy(
        self,
        session: AsyncSession,
        policy_id: str,
        *,
        requires_human_review: Optional[bool] = None,
        reviewer_role: Optional[str] = None,
    ) -> LLCReviewGatePolicy:
        """Update mutable fields. Raises ReviewGatePolicyNotFoundError if missing."""
        policy = await self.get_policy_by_id(session, policy_id)
        if policy is None:
            raise ReviewGatePolicyNotFoundError(f"Policy {policy_id} not found")
        if requires_human_review is not None:
            policy.requires_human_review = requires_human_review
        if reviewer_role is not None:
            policy.reviewer_role = reviewer_role
        await session.flush()
        return policy

    async def delete_policy(
        self,
        session: AsyncSession,
        policy_id: str,
    ) -> bool:
        """Delete a policy. Returns True if deleted, False if not found."""
        result = await session.execute(
            delete(LLCReviewGatePolicy)
            .where(LLCReviewGatePolicy.id == uuid.UUID(policy_id))
            .returning(LLCReviewGatePolicy.id)
        )
        deleted = result.scalar_one_or_none()
        await session.flush()
        return deleted is not None

    async def seed_defaults(
        self,
        session: AsyncSession,
        company_id: str,
    ) -> list[LLCReviewGatePolicy]:
        """Install default review gate policies for a new company.

        bug → requires_human_review=True
        All other work item types → requires_human_review=False

        Skips types that already have a policy (idempotent).
        """
        created = []
        for item_type in WorkItemType:
            existing = await self.get_policy(session, company_id, item_type)
            if existing is not None:
                continue
            requires = _DEFAULT_POLICIES.get(item_type, False)
            policy = LLCReviewGatePolicy(
                id=uuid.uuid4(),
                company_id=uuid.UUID(company_id),
                item_type=item_type,
                requires_human_review=requires,
                reviewer_role=None,
            )
            session.add(policy)
            created.append(policy)
        if created:
            await session.flush()
        return created

    async def requires_review(
        self,
        session: AsyncSession,
        company_id: str,
        item_type: WorkItemType,
    ) -> tuple[bool, Optional[str]]:
        """Return (requires_human_review, reviewer_role) for this type, defaulting to False."""
        policy = await self.get_policy(session, company_id, item_type)
        if policy is None:
            return False, None
        return policy.requires_human_review, policy.reviewer_role
