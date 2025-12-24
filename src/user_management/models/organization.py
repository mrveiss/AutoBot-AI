# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Organization Model

Represents a tenant/organization in the system.
In multi_company and provider modes, each organization is isolated.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.user_management.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.user_management.models.user import User
    from src.user_management.models.team import Team
    from src.user_management.models.role import Role
    from src.user_management.models.sso import SSOProvider


class Organization(Base, TimestampMixin):
    """
    Organization/Tenant model.

    Attributes:
        id: Unique identifier (UUID)
        name: Display name of the organization
        slug: URL-friendly unique identifier
        settings: JSON settings (branding, policies, etc.)
        subscription_tier: For provider mode - free, pro, enterprise
        max_users: Maximum allowed users (-1 for unlimited)
        is_active: Whether the organization is active
    """

    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    slug: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # JSON settings for flexible configuration
    settings: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Provider mode: subscription management
    subscription_tier: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        default="free",
    )

    max_users: Mapped[int] = mapped_column(
        Integer,
        default=-1,  # -1 means unlimited
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    users: Mapped[list["User"]] = relationship(
        "User",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    teams: Mapped[list["Team"]] = relationship(
        "Team",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    roles: Mapped[list["Role"]] = relationship(
        "Role",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    sso_providers: Mapped[list["SSOProvider"]] = relationship(
        "SSOProvider",
        back_populates="organization",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, name={self.name}, slug={self.slug})>"

    @property
    def is_deleted(self) -> bool:
        """Check if organization is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Soft delete the organization."""
        self.deleted_at = datetime.utcnow()
        self.is_active = False

    def get_setting(self, key: str, default=None):
        """Get a setting value by key with dot notation support."""
        keys = key.split(".")
        value = self.settings
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set_setting(self, key: str, value) -> None:
        """Set a setting value by key with dot notation support."""
        keys = key.split(".")
        settings = self.settings.copy()
        current = settings
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
        self.settings = settings
