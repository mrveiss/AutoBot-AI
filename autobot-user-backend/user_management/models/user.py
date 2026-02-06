# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
User Model

Core user model with authentication, profile, and tenant association.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.user_management.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from src.user_management.models.organization import Organization
    from src.user_management.models.team import TeamMembership
    from src.user_management.models.role import UserRole
    from src.user_management.models.api_key import APIKey
    from src.user_management.models.sso import UserSSOLink
    from src.user_management.models.mfa import UserMFA


class User(Base, TimestampMixin):
    """
    User model.

    Attributes:
        id: Unique identifier (UUID)
        org_id: Organization this user belongs to (nullable for platform admins)
        email: Unique email address
        username: Unique username
        password_hash: Bcrypt hashed password (nullable for SSO-only users)
        display_name: User's display name
        avatar_url: URL to avatar image
        is_active: Whether the user can log in
        is_verified: Email verification status
        mfa_enabled: Whether 2FA is enabled
        preferences: User preferences (theme, language, etc.)
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Organization association (nullable for platform admins in provider mode)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Authentication
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
    )

    password_hash: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,  # Nullable for SSO-only users
    )

    # Profile
    display_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    avatar_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )

    bio: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Status flags
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    mfa_enabled: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Platform admin flag (provider mode only)
    is_platform_admin: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # User preferences (theme, language, notifications, etc.)
    preferences: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Timestamps
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    email_verified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Soft delete
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="users",
    )

    team_memberships: Mapped[list["TeamMembership"]] = relationship(
        "TeamMembership",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    user_roles: Mapped[list["UserRole"]] = relationship(
        "UserRole",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    api_keys: Mapped[list["APIKey"]] = relationship(
        "APIKey",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    sso_links: Mapped[list["UserSSOLink"]] = relationship(
        "UserSSOLink",
        back_populates="user",
        cascade="all, delete-orphan",
    )

    mfa: Mapped[Optional["UserMFA"]] = relationship(
        "UserMFA",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, username={self.username}, email={self.email})>"

    @property
    def is_deleted(self) -> bool:
        """Check if user is soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Soft delete the user."""
        self.deleted_at = datetime.utcnow()
        self.is_active = False

    def get_preference(self, key: str, default=None):
        """Get a preference value by key with dot notation support."""
        keys = key.split(".")
        value = self.preferences
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value

    def set_preference(self, key: str, value) -> None:
        """Set a preference value by key with dot notation support."""
        keys = key.split(".")
        preferences = self.preferences.copy()
        current = preferences
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            current = current[k]
        current[keys[-1]] = value
        self.preferences = preferences

    @property
    def full_name(self) -> str:
        """Return display name or username as fallback."""
        return self.display_name or self.username

    def record_login(self) -> None:
        """Record a successful login."""
        self.last_login_at = datetime.utcnow()

    def verify_email(self) -> None:
        """Mark email as verified."""
        self.is_verified = True
        self.email_verified_at = datetime.utcnow()
