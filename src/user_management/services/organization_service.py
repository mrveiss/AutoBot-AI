# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Organization Service

Business logic for organization (tenant) management operations.
Used in multi_company and provider deployment modes.
"""

import asyncio
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.user_management.models import Organization, Team, User
from src.user_management.models.audit import AuditAction, AuditLog, AuditResourceType
from src.user_management.services.base_service import BaseService, TenantContext

logger = logging.getLogger(__name__)


class OrganizationServiceError(Exception):
    """Base exception for organization service errors."""


class OrganizationNotFoundError(OrganizationServiceError):
    """Raised when organization is not found."""


class DuplicateOrganizationError(OrganizationServiceError):
    """Raised when attempting to create a duplicate organization."""


class OrganizationLimitError(OrganizationServiceError):
    """Raised when organization limits are exceeded."""


class OrganizationService(BaseService):
    """
    Organization management service.

    Provides CRUD operations for organizations (tenants) with
    quota management for provider mode.
    """

    def __init__(self, session: AsyncSession, context: Optional[TenantContext] = None):
        """Initialize organization service."""
        super().__init__(session, context)

    # -------------------------------------------------------------------------
    # Organization CRUD Operations
    # -------------------------------------------------------------------------

    async def create_organization(
        self,
        name: str,
        slug: Optional[str] = None,
        description: Optional[str] = None,
        settings: Optional[dict] = None,
        subscription_tier: str = "free",
        max_users: int = -1,
    ) -> Organization:
        """
        Create a new organization.

        Args:
            name: Organization name
            slug: URL-safe slug (auto-generated if not provided)
            description: Organization description
            settings: Organization settings JSON
            subscription_tier: Subscription tier (free, pro, enterprise)
            max_users: Maximum users allowed (-1 for unlimited)

        Returns:
            Created Organization instance

        Raises:
            DuplicateOrganizationError: If slug already exists
        """
        self._require_platform_admin()

        # Generate slug if not provided
        if not slug:
            slug = self._generate_slug(name)

        # Check for duplicate slug
        existing = await self.get_organization_by_slug(slug)
        if existing:
            raise DuplicateOrganizationError(
                f"Organization with slug '{slug}' already exists"
            )

        org = Organization(
            id=uuid.uuid4(),
            name=name,
            slug=slug,
            description=description,
            settings=settings or {},
            subscription_tier=subscription_tier,
            max_users=max_users,
            is_active=True,
        )

        self.session.add(org)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.ORG_CREATED,
            resource_type=AuditResourceType.ORGANIZATION,
            resource_id=org.id,
            org_id=org.id,
            details={
                "name": name,
                "slug": slug,
                "subscription_tier": subscription_tier,
            },
        )

        logger.info("Created organization: %s (id=%s, slug=%s)", name, org.id, slug)
        return org

    async def get_organization(self, org_id: uuid.UUID) -> Optional[Organization]:
        """
        Get organization by ID.

        Args:
            org_id: Organization UUID

        Returns:
            Organization instance or None
        """
        result = await self.session.execute(
            select(Organization)
            .where(Organization.id == org_id)
            .where(Organization.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def get_organization_by_slug(self, slug: str) -> Optional[Organization]:
        """
        Get organization by slug.

        Args:
            slug: Organization slug (case-insensitive)

        Returns:
            Organization instance or None
        """
        result = await self.session.execute(
            select(Organization)
            .where(func.lower(Organization.slug) == slug.lower())
            .where(Organization.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_organizations(
        self,
        limit: int = 50,
        offset: int = 0,
        include_inactive: bool = False,
        search: Optional[str] = None,
    ) -> tuple[List[Organization], int]:
        """
        List organizations with pagination.

        Args:
            limit: Maximum number of organizations to return
            offset: Number of organizations to skip
            include_inactive: Include inactive organizations
            search: Search term for name or slug

        Returns:
            Tuple of (organizations list, total count)
        """
        self._require_platform_admin()

        base_query = select(Organization).where(Organization.deleted_at.is_(None))

        if not include_inactive:
            base_query = base_query.where(Organization.is_active.is_(True))

        if search:
            search_pattern = f"%{search}%"
            base_query = base_query.where(
                or_(
                    Organization.name.ilike(search_pattern),
                    Organization.slug.ilike(search_pattern),
                )
            )

        # Get total count
        count_query = select(func.count()).select_from(base_query.subquery())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar() or 0

        # Get paginated results
        query = base_query.order_by(Organization.name).limit(limit).offset(offset)

        result = await self.session.execute(query)
        orgs = list(result.scalars().all())

        return orgs, total

    async def update_organization(
        self,
        org_id: uuid.UUID,
        name: Optional[str] = None,
        description: Optional[str] = None,
        settings: Optional[dict] = None,
        subscription_tier: Optional[str] = None,
        max_users: Optional[int] = None,
    ) -> Organization:
        """
        Update organization.

        Args:
            org_id: Organization ID to update
            name: New name (optional)
            description: New description (optional)
            settings: New settings (optional)
            subscription_tier: New subscription tier (optional)
            max_users: New max users (optional)

        Returns:
            Updated Organization instance

        Raises:
            OrganizationNotFoundError: If organization not found
        """
        org = await self.get_organization(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization {org_id} not found")

        changes = {}

        if name and name != org.name:
            changes["name"] = {"old": org.name, "new": name}
            org.name = name

        if description is not None:
            changes["description"] = {"old": org.description, "new": description}
            org.description = description

        if settings is not None:
            org.settings = settings

        if subscription_tier is not None:
            changes["subscription_tier"] = {
                "old": org.subscription_tier,
                "new": subscription_tier,
            }
            org.subscription_tier = subscription_tier

        if max_users is not None:
            changes["max_users"] = {"old": org.max_users, "new": max_users}
            org.max_users = max_users

        org.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        if changes:
            await self._audit_log(
                action=AuditAction.ORG_UPDATED,
                resource_type=AuditResourceType.ORGANIZATION,
                resource_id=org_id,
                org_id=org_id,
                details={"changes": changes},
            )

        return org

    async def deactivate_organization(self, org_id: uuid.UUID) -> bool:
        """
        Deactivate an organization.

        Args:
            org_id: Organization ID to deactivate

        Returns:
            True if deactivated
        """
        self._require_platform_admin()

        org = await self.get_organization(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization {org_id} not found")

        org.is_active = False
        org.updated_at = datetime.now(timezone.utc)
        await self.session.flush()

        await self._audit_log(
            action=AuditAction.ORG_UPDATED,
            resource_type=AuditResourceType.ORGANIZATION,
            resource_id=org_id,
            org_id=org_id,
            details={"action": "deactivated"},
        )

        logger.info("Deactivated organization: %s", org_id)
        return True

    async def delete_organization(
        self, org_id: uuid.UUID, hard_delete: bool = False
    ) -> bool:
        """
        Delete an organization.

        Args:
            org_id: Organization ID to delete
            hard_delete: If True, permanently delete

        Returns:
            True if deleted
        """
        self._require_platform_admin()

        org = await self.get_organization(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization {org_id} not found")

        if hard_delete:
            await self.session.delete(org)
        else:
            org.deleted_at = datetime.now(timezone.utc)
            org.is_active = False

        await self.session.flush()

        await self._audit_log(
            action=AuditAction.ORG_DELETED,
            resource_type=AuditResourceType.ORGANIZATION,
            resource_id=org_id,
            org_id=org_id,
            details={"hard_delete": hard_delete, "name": org.name},
        )

        logger.info("Deleted organization: %s (hard=%s)", org_id, hard_delete)
        return True

    # -------------------------------------------------------------------------
    # Quota Management
    # -------------------------------------------------------------------------

    async def get_user_count(self, org_id: uuid.UUID) -> int:
        """
        Get the number of active users in an organization.

        Args:
            org_id: Organization ID

        Returns:
            Number of active users
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(User)
            .where(User.org_id == org_id)
            .where(User.is_active.is_(True))
            .where(User.deleted_at.is_(None))
        )
        return result.scalar() or 0

    async def get_team_count(self, org_id: uuid.UUID) -> int:
        """
        Get the number of teams in an organization.

        Args:
            org_id: Organization ID

        Returns:
            Number of teams
        """
        result = await self.session.execute(
            select(func.count())
            .select_from(Team)
            .where(Team.org_id == org_id)
            .where(Team.deleted_at.is_(None))
        )
        return result.scalar() or 0

    async def can_add_user(self, org_id: uuid.UUID) -> bool:
        """
        Check if organization can add more users.

        Args:
            org_id: Organization ID

        Returns:
            True if user can be added
        """
        org = await self.get_organization(org_id)
        if not org:
            return False

        # -1 means unlimited
        if org.max_users == -1:
            return True

        current_count = await self.get_user_count(org_id)
        return current_count < org.max_users

    async def get_organization_stats(self, org_id: uuid.UUID) -> dict:
        """
        Get organization statistics.

        Args:
            org_id: Organization ID

        Returns:
            Dict with organization statistics
        """
        org = await self.get_organization(org_id)
        if not org:
            raise OrganizationNotFoundError(f"Organization {org_id} not found")

        # Issue #619: Parallelize independent async operations
        user_count, team_count, can_add = await asyncio.gather(
            self.get_user_count(org_id),
            self.get_team_count(org_id),
            self.can_add_user(org_id),
        )

        return {
            "organization_id": str(org_id),
            "name": org.name,
            "slug": org.slug,
            "subscription_tier": org.subscription_tier,
            "users": {
                "current": user_count,
                "max": org.max_users if org.max_users != -1 else "unlimited",
                "can_add": can_add,
            },
            "teams": {
                "current": team_count,
            },
            "is_active": org.is_active,
            "created_at": org.created_at.isoformat() if org.created_at else None,
        }

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _generate_slug(self, name: str) -> str:
        """Generate URL-safe slug from name."""
        # Convert to lowercase
        slug = name.lower()
        # Replace spaces and special chars with hyphens
        slug = re.sub(r"[^a-z0-9]+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        # Limit length
        return slug[:100]

    async def _audit_log(
        self,
        action: str,
        resource_type: str,
        resource_id: Optional[uuid.UUID],
        org_id: Optional[uuid.UUID],
        details: dict,
        outcome: str = "success",
    ) -> None:
        """Create audit log entry."""
        audit_entry = AuditLog(
            id=uuid.uuid4(),
            org_id=org_id,
            user_id=self.context.user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            outcome=outcome,
            details=details,
        )
        self.session.add(audit_entry)
