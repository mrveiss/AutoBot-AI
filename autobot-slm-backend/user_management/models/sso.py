# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
SSO Provider and User SSO Link Models

Supports multiple SSO providers:
- Enterprise: LDAP/AD, SAML 2.0, Microsoft Entra ID, Google Workspace
- Social: Google OAuth, Facebook, GitHub
"""

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from user_management.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from user_management.models.organization import Organization
    from user_management.models.user import User


class SSOProviderType(str, Enum):
    """SSO Provider types."""

    # Enterprise SSO
    LDAP = "ldap"
    ACTIVE_DIRECTORY = "active_directory"
    SAML = "saml"
    MICROSOFT_ENTRA = "microsoft_entra"
    GOOGLE_WORKSPACE = "google_workspace"

    # Social Login (provider mode)
    GOOGLE = "google"
    FACEBOOK = "facebook"
    GITHUB = "github"


class SSOProvider(Base, TimestampMixin):
    """
    SSO Provider configuration.

    Stores configuration for SSO providers. Config is encrypted at rest.
    Can be organization-specific or global (for social login in provider mode).
    """

    __tablename__ = "sso_providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Organization (nullable for global/social providers)
    org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Provider type
    provider_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
    )

    # Display name
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # Provider configuration (encrypted JSON)
    # Contains client_id, client_secret, endpoints, etc.
    config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    # Status
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Whether this is a social login provider (vs enterprise SSO)
    is_social: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # Allow user creation via this provider
    allow_user_creation: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
    )

    # Default role for users created via this provider
    default_role: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        default="user",
    )

    # Group/team mapping configuration
    group_mapping: Mapped[dict] = mapped_column(
        JSONB,
        default=dict,
        nullable=False,
    )

    # Last successful sync (for LDAP/AD)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="sso_providers",
    )

    user_links: Mapped[list["UserSSOLink"]] = relationship(
        "UserSSOLink",
        back_populates="provider",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        scope = f"org:{self.org_id}" if self.org_id else "global"
        return (
            f"<SSOProvider(type={self.provider_type}, name={self.name}, scope={scope})>"
        )

    @property
    def is_enterprise(self) -> bool:
        """Check if this is an enterprise SSO provider."""
        return self.provider_type in (
            SSOProviderType.LDAP.value,
            SSOProviderType.ACTIVE_DIRECTORY.value,
            SSOProviderType.SAML.value,
            SSOProviderType.MICROSOFT_ENTRA.value,
            SSOProviderType.GOOGLE_WORKSPACE.value,
        )

    def get_config_value(self, key: str, default=None):
        """Get a configuration value safely."""
        return self.config.get(key, default)


class UserSSOLink(Base, TimestampMixin):
    """
    Link between a user and an SSO provider.

    Stores the external ID from the SSO provider.
    A user can have multiple SSO links (e.g., both Google and GitHub).
    """

    __tablename__ = "user_sso_links"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    provider_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sso_providers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # External ID from the SSO provider
    external_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # External email (may differ from user's primary email)
    external_email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )

    # Additional data from SSO provider (renamed from 'metadata' to avoid SQLAlchemy conflict)
    sso_metadata: Mapped[dict] = mapped_column(
        "metadata",  # Keep original column name in database
        JSONB,
        default=dict,
        nullable=False,
    )

    # Last login via this SSO provider
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Unique constraint: one link per provider external ID
    __table_args__ = (
        UniqueConstraint("provider_id", "external_id", name="uq_provider_external_id"),
    )

    # Relationships
    user: Mapped["User"] = relationship(
        "User",
        back_populates="sso_links",
    )

    provider: Mapped["SSOProvider"] = relationship(
        "SSOProvider",
        back_populates="user_links",
    )

    def __repr__(self) -> str:
        return (
            f"<UserSSOLink(user_id={self.user_id}, "
            f"provider_id={self.provider_id}, external_id={self.external_id})>"
        )

    def record_login(self) -> None:
        """Record a login via this SSO link."""
        self.last_login_at = datetime.utcnow()
