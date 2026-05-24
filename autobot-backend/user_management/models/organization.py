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

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from autobot_shared.time_utils import now_utc
from user_management.models.base import Base

if TYPE_CHECKING:
    from user_management.models.role import Role
    from user_management.models.sso import SSOProvider
    from user_management.models.team import Team
    from user_management.models.user import User


class Organization(Base):
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
        Uuid(as_uuid=True),
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

    description: Mapped[str | None] = mapped_column(
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
    subscription_tier: Mapped[str | None] = mapped_column(
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # LLC extension columns (GH#8211)                                     #
    # ------------------------------------------------------------------ #

    # Sub-company hierarchy: nullable for root companies
    parent_org_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Per-company issue numbering (e.g. "ABO", "MVA")
    issue_prefix: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        unique=True,
        index=True,
    )
    issue_counter: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Budget tracking in cents to avoid floating-point precision issues
    budget_monthly_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    spent_monthly_cents: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Branding
    brand_color: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Governance
    require_approval_for_hires: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # LLC lifecycle status — stored as string, validated by LLCCompanyStatus enum
    llc_status: Mapped[str] = mapped_column(
        String(32),
        default="onboarding",
        nullable=False,
    )
    pause_reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    paused_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # ------------------------------------------------------------------ #
    # External PM sync config (GH#8257)                                   #
    # ------------------------------------------------------------------ #

    external_pm_type: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )

    # AES-256-encrypted JSON blob — never store plaintext credentials
    external_pm_config: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    # Self-referential relationships for sub-company tree
    children: Mapped[list["Organization"]] = relationship(
        "Organization",
        back_populates="parent",
        foreign_keys="Organization.parent_org_id",
        lazy="select",
    )
    parent: Mapped[Optional["Organization"]] = relationship(
        "Organization",
        back_populates="children",
        foreign_keys="Organization.parent_org_id",
        remote_side="Organization.id",
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
        self.deleted_at = now_utc()
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

    # ------------------------------------------------------------------
    # Per-org LLM + embedding model config (Issue #4451)
    # ------------------------------------------------------------------

    def get_model_config(self) -> dict:
        """Return the org's persisted LLM/embedding model config.

        Known keys: ``llm_provider``, ``llm_model``, ``embedding_model``,
        ``embedding_dimension``.  Missing keys indicate "use SSOT default".
        """
        return {
            "llm_provider": self.get_setting("llm_provider"),
            "llm_model": self.get_setting("llm_model"),
            "embedding_model": self.get_setting("embedding_model"),
            "embedding_dimension": self.get_setting("embedding_dimension"),
        }

    def set_model_config(self, config: dict) -> None:
        """Persist the org's LLM/embedding model config.

        Only the four well-known keys are accepted.  Passing ``None`` for a
        key clears that field; omitting the key leaves the existing value
        untouched.
        """
        known = {"llm_provider", "llm_model", "embedding_model", "embedding_dimension"}
        for key in known & set(config.keys()):
            self.set_setting(key, config[key])
