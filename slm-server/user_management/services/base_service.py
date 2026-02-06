# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Base Service Class

Provides tenant context management and common service patterns.
"""

import logging
import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass
class TenantContext:
    """
    Tenant context for multi-tenancy operations.

    In single_user mode, org_id is None.
    In single_company mode, org_id is the implicit organization.
    In multi_company/provider modes, org_id is set from JWT/session.
    """

    org_id: Optional[uuid.UUID] = None
    user_id: Optional[uuid.UUID] = None
    is_platform_admin: bool = False

    @property
    def is_authenticated(self) -> bool:
        """Check if context has an authenticated user."""
        return self.user_id is not None

    @property
    def is_org_scoped(self) -> bool:
        """Check if context has organization scope."""
        return self.org_id is not None


class BaseService:
    """
    Base service class with tenant context support.

    All tenant-scoped services should inherit from this.
    """

    def __init__(self, session: AsyncSession, context: Optional[TenantContext] = None):
        """
        Initialize service with database session and tenant context.

        Args:
            session: Async SQLAlchemy session
            context: Optional tenant context for multi-tenancy
        """
        self.session = session
        self.context = context or TenantContext()

    def apply_tenant_filter(self, query: Select, model_class) -> Select:
        """
        Apply tenant filter to query if organization-scoped.

        Args:
            query: SQLAlchemy select query
            model_class: Model class with org_id column

        Returns:
            Filtered query
        """
        if self.context.org_id and hasattr(model_class, "org_id"):
            return query.where(model_class.org_id == self.context.org_id)
        return query

    async def _get_by_id(self, model_class, entity_id: uuid.UUID):
        """
        Get entity by ID with tenant filtering.

        Args:
            model_class: SQLAlchemy model class
            entity_id: Entity UUID

        Returns:
            Entity instance or None
        """
        query = select(model_class).where(model_class.id == entity_id)
        query = self.apply_tenant_filter(query, model_class)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def _soft_delete(self, entity) -> bool:
        """
        Soft delete an entity if it has soft delete support.

        Args:
            entity: Entity instance with soft_delete method

        Returns:
            True if deleted
        """
        if hasattr(entity, "soft_delete"):
            entity.soft_delete()
            await self.session.flush()
            return True
        return False

    def _require_org_context(self):
        """Raise error if no organization context is set."""
        if not self.context.org_id:
            raise ValueError(
                "Organization context required for this operation. "
                "Ensure deployment mode supports multi-tenancy."
            )

    def _require_auth_context(self):
        """Raise error if no authenticated user context."""
        if not self.context.user_id:
            raise ValueError("Authenticated user context required for this operation.")

    def _require_platform_admin(self):
        """Raise error if current user is not a platform admin."""
        if not self.context.is_platform_admin:
            raise PermissionError(
                "Platform admin privileges required for this operation."
            )
