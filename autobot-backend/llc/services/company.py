# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""CompanyService — LLC lifecycle management for Organization entities (GH#8211).

Extends LLCServiceBase with CRUD operations, sub-company tree traversal,
ancestry lookup, budget enforcement, and status lifecycle transitions
(suspend / archive).
"""

import asyncio
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from autobot_shared.logging_manager import get_logger
from autobot_shared.time_utils import now_utc
from llc.models.company import CompanyCreate, CompanyRead, CompanyTreeNode, CompanyUpdate
from llc.models.enums import LLCCompanyStatus
from llc.services.base import LLCServiceBase
from user_management.models.organization import Organization

logger = get_logger(__name__)


class CompanyNotFoundError(Exception):
    """Raised when the requested company does not exist."""


class CompanyCycleError(Exception):
    """Raised when a parent_org_id assignment would create a hierarchy cycle."""


class CompanyBudgetError(Exception):
    """Raised when a child company budget would exceed parent remaining budget."""


class CompanyIssuePrefixConflictError(Exception):
    """Raised when the requested issue_prefix is already taken."""


class CompanyHasChildrenError(Exception):
    """Raised when attempting to delete a company that still has active child companies."""


class CompanyService(LLCServiceBase):
    """LLC service for company CRUD + lifecycle operations.

    All methods accept an ``AsyncSession`` so they can participate in the
    caller's transaction.  Callers are responsible for ``session.commit()``.
    """

    def __init__(self, session: AsyncSession, **kwargs) -> None:
        super().__init__(**kwargs)
        self.session = session

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def create(self, data: CompanyCreate) -> Organization:
        """Create a new company (Organization with LLC fields)."""
        await self._assert_prefix_unique(data.issue_prefix)

        if data.parent_org_id is not None:
            parent = await self._get_or_404(data.parent_org_id)
            await self._assert_budget_fits(parent, data.budget_monthly_cents)

        org = Organization(
            name=data.name,
            slug=data.slug,
            description=data.description,
            settings={},
            parent_org_id=data.parent_org_id,
            issue_prefix=data.issue_prefix,
            budget_monthly_cents=data.budget_monthly_cents,
            brand_color=data.brand_color,
            require_approval_for_hires=data.require_approval_for_hires,
            llc_status=data.llc_status.value,
        )
        self.session.add(org)
        await self.session.flush()

        if data.parent_org_id is not None:
            await self._assert_no_cycle(org.id, data.parent_org_id)

        logger.info("LLC company created: %s (id=%s)", org.name, org.id)
        return org

    async def get(self, company_id: uuid.UUID) -> Organization:
        """Return the company or raise CompanyNotFoundError."""
        return await self._get_or_404(company_id)

    async def update(self, company_id: uuid.UUID, data: CompanyUpdate) -> Organization:
        """Apply partial update to a company."""
        org = await self._get_or_404(company_id)

        if data.issue_prefix is not None and data.issue_prefix != org.issue_prefix:
            await self._assert_prefix_unique(data.issue_prefix)

        if data.parent_org_id is not None:
            await self._assert_no_cycle(company_id, data.parent_org_id)

        if data.budget_monthly_cents is not None and org.parent_org_id is not None:
            parent = await self._get_or_404(org.parent_org_id)
            await self._assert_budget_fits(parent, data.budget_monthly_cents, exclude_id=company_id)

        update_fields = data.model_dump(exclude_none=True)
        for field, value in update_fields.items():
            if field == "llc_status":
                setattr(org, field, value.value if isinstance(value, LLCCompanyStatus) else value)
            else:
                setattr(org, field, value)

        await self.session.flush()
        logger.info("LLC company updated: %s (id=%s)", org.name, org.id)
        return org

    async def list_root_companies(self) -> List[Organization]:
        """Return all top-level companies (parent_org_id IS NULL)."""
        result = await self.session.execute(
            select(Organization)
            .where(Organization.parent_org_id.is_(None))
            .where(Organization.deleted_at.is_(None))
            .order_by(Organization.name)
        )
        return list(result.scalars().all())

    async def list_children(self, parent_id: uuid.UUID) -> List[Organization]:
        """Return direct children of the given company."""
        result = await self.session.execute(
            select(Organization)
            .where(Organization.parent_org_id == parent_id)
            .where(Organization.deleted_at.is_(None))
            .order_by(Organization.name)
        )
        return list(result.scalars().all())

    async def delete(self, company_id: uuid.UUID) -> None:
        """Soft-delete a company.

        Raises CompanyHasChildrenError when active child companies exist, preventing
        orphaned children that ON DELETE SET NULL cannot handle for soft-deletes.
        """
        org = await self._get_or_404(company_id)
        children = await self.list_children(company_id)
        if children:
            raise CompanyHasChildrenError(
                f"Company {company_id} has {len(children)} active child company(s); "
                "re-parent or delete children before deleting the parent"
            )
        org.soft_delete()
        await self.session.flush()
        logger.info("LLC company soft-deleted: %s (id=%s)", org.name, org.id)

    # ------------------------------------------------------------------
    # Status transitions
    # ------------------------------------------------------------------

    # Valid states from which suspend() is allowed
    _SUSPEND_FROM: frozenset[str] = frozenset({LLCCompanyStatus.ONBOARDING.value, LLCCompanyStatus.ACTIVE.value})
    # Valid states from which archive() is allowed
    _ARCHIVE_FROM: frozenset[str] = frozenset({LLCCompanyStatus.PAUSED.value, LLCCompanyStatus.OFFBOARDING.value})

    async def suspend(self, company_id: uuid.UUID, reason: Optional[str] = None) -> Organization:
        """Transition company to PAUSED status.

        Only allowed from ONBOARDING or ACTIVE — raises ValueError otherwise.
        """
        org = await self._get_or_404(company_id)
        if org.llc_status not in self._SUSPEND_FROM:
            raise ValueError(
                f"Cannot suspend company in '{org.llc_status}' state "
                f"(allowed from: {', '.join(sorted(self._SUSPEND_FROM))})"
            )
        org.llc_status = LLCCompanyStatus.PAUSED.value
        org.pause_reason = reason
        org.paused_at = now_utc()
        await self.session.flush()
        logger.info("LLC company suspended: %s (id=%s)", org.name, org.id)
        return org

    async def archive(self, company_id: uuid.UUID) -> Organization:
        """Transition company to ARCHIVED status.

        Only allowed from PAUSED or OFFBOARDING — raises ValueError otherwise.
        """
        org = await self._get_or_404(company_id)
        if org.llc_status not in self._ARCHIVE_FROM:
            raise ValueError(
                f"Cannot archive company in '{org.llc_status}' state "
                f"(allowed from: {', '.join(sorted(self._ARCHIVE_FROM))})"
            )
        org.llc_status = LLCCompanyStatus.ARCHIVED.value
        await self.session.flush()
        logger.info("LLC company archived: %s (id=%s)", org.name, org.id)
        return org

    # ------------------------------------------------------------------
    # Tree / ancestry
    # ------------------------------------------------------------------

    async def get_sub_company_tree(self, org_id: uuid.UUID) -> CompanyTreeNode:
        """Return the recursive sub-company tree rooted at org_id."""
        root = await self._get_or_404(org_id)
        return await self._build_tree_node(root)

    async def get_ancestry(self, org_id: uuid.UUID) -> List[Organization]:
        """Return the chain of ancestors from root down to org_id (exclusive)."""
        org = await self._get_or_404(org_id)
        chain: List[Organization] = []
        visited: set[uuid.UUID] = {org.id}

        current_id = org.parent_org_id
        while current_id is not None:
            if current_id in visited:
                break
            parent = await self._get_or_404(current_id)
            chain.append(parent)
            visited.add(parent.id)
            current_id = parent.parent_org_id

        chain.reverse()
        return chain

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_or_404(self, company_id: uuid.UUID) -> Organization:
        result = await self.session.execute(
            select(Organization).where(Organization.id == company_id).where(Organization.deleted_at.is_(None))
        )
        org = result.scalar_one_or_none()
        if org is None:
            raise CompanyNotFoundError(f"Company {company_id} not found")
        return org

    async def _assert_prefix_unique(self, prefix: Optional[str]) -> None:
        if prefix is None:
            return
        result = await self.session.execute(
            select(Organization.id).where(Organization.issue_prefix == prefix).where(Organization.deleted_at.is_(None))
        )
        if result.scalar_one_or_none() is not None:
            raise CompanyIssuePrefixConflictError(f"issue_prefix '{prefix}' is already taken")

    async def _assert_budget_fits(
        self,
        parent: Organization,
        child_budget_cents: int,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> None:
        """Ensure child budget does not exceed parent remaining budget.

        Pass exclude_id=company_id when updating an existing child to avoid
        double-counting that child's current allocation.
        """
        if parent.budget_monthly_cents == 0:
            return
        existing_children_total = await self._sum_children_budget(parent.id, exclude_id=exclude_id)
        remaining = parent.budget_monthly_cents - parent.spent_monthly_cents - existing_children_total
        if child_budget_cents > remaining:
            raise CompanyBudgetError(
                f"Child budget {child_budget_cents} cents exceeds parent remaining " f"budget {remaining} cents"
            )

    async def _sum_children_budget(
        self,
        parent_id: uuid.UUID,
        exclude_id: Optional[uuid.UUID] = None,
    ) -> int:
        stmt = (
            select(Organization.budget_monthly_cents)
            .where(Organization.parent_org_id == parent_id)
            .where(Organization.deleted_at.is_(None))
        )
        if exclude_id is not None:
            stmt = stmt.where(Organization.id != exclude_id)
        result = await self.session.execute(stmt)
        return sum(row for row in result.scalars().all())

    async def _build_tree_node(
        self,
        org: Organization,
        visited: Optional[set[uuid.UUID]] = None,
    ) -> CompanyTreeNode:
        if visited is None:
            visited = set()
        if org.id in visited:
            raise CompanyCycleError(f"Cycle detected in company tree at id={org.id}")
        current_visited = visited | {org.id}
        children_orgs = await self.list_children(org.id)
        children_nodes = list(await asyncio.gather(*[self._build_tree_node(c, current_visited) for c in children_orgs]))
        return CompanyTreeNode(
            id=org.id,
            name=org.name,
            slug=org.slug,
            llc_status=LLCCompanyStatus(org.llc_status),
            children=children_nodes,
        )

    async def _assert_no_cycle(self, target_id: uuid.UUID, new_parent_id: uuid.UUID) -> None:
        """Raise CompanyCycleError if setting new_parent_id would create a cycle."""
        visited: set[uuid.UUID] = {target_id}
        current_id: Optional[uuid.UUID] = new_parent_id
        while current_id is not None:
            if current_id in visited:
                raise CompanyCycleError(f"Setting parent_org_id={new_parent_id} would create a hierarchy cycle")
            visited.add(current_id)
            result = await self.session.execute(select(Organization.parent_org_id).where(Organization.id == current_id))
            current_id = result.scalar_one_or_none()
