# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical ``Organization`` core shared by both backends (#12647).

Together with ``models/user.py``, this was the last file still forked between
``autobot-backend`` and ``autobot-slm-backend``. SLM is a strict subset;
backend additionally carries the LLC extension columns (#8211), external PM
sync config (#8257), the KB inheritance weight (#8241) and the per-org
LLM/embedding model config helpers (#4451).

Per the owner's decision on #12645/#12647, the shape is an **abstract core**,
not a single concrete class carrying the union of both schemas:

- ``OrganizationCore`` (here) owns every column, relationship and method the
  two backends already share.
- Each backend keeps its own concrete ``Organization(OrganizationCore)`` with
  ``__tablename__`` and its local extras. Backend's LLC/PM columns stay in
  ``autobot-backend`` — folding them into the shared core would force a
  migration adding ~12 unused columns to SLM's ``organizations`` table for a
  feature SLM does not have.

This carries **no database change on either side**: the abstract class is not
mapped, and every column it contributes is one both backends already had, with
identical type, nullability and index.

See ``models/user.py`` for the ``declared_attr`` rationale (foreign keys and
relationships cannot be shared objects across mapped classes) and for the
``Mapped["X | None"]`` style decision.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.models.base import Base

if TYPE_CHECKING:
    from user_management.models.role import Role
    from user_management.models.sso import SSOProvider
    from user_management.models.team import Team
    from user_management.models.user import User


class OrganizationCore(Base):
    """Shared core of the ``organizations`` table.

    Abstract: it declares no ``__tablename__`` and is never mapped. Each
    backend's concrete ``Organization`` subclasses it and supplies
    ``__tablename__``.

    Attributes:
        id: Unique identifier (UUID)
        name: Display name of the organization
        slug: URL-friendly unique identifier
        settings: JSON settings (branding, policies, etc.)
        subscription_tier: For provider mode - free, pro, enterprise
        max_users: Maximum allowed users (-1 for unlimited)
        is_active: Whether the organization is active
    """

    __abstract__ = True

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

    # Relationships
    @declared_attr
    def users(cls) -> Mapped[list["User"]]:
        return relationship(
            "User",
            back_populates="organization",
            cascade="all, delete-orphan",
        )

    @declared_attr
    def teams(cls) -> Mapped[list["Team"]]:
        return relationship(
            "Team",
            back_populates="organization",
            cascade="all, delete-orphan",
        )

    @declared_attr
    def roles(cls) -> Mapped[list["Role"]]:
        return relationship(
            "Role",
            back_populates="organization",
            cascade="all, delete-orphan",
        )

    @declared_attr
    def sso_providers(cls) -> Mapped[list["SSOProvider"]]:
        return relationship(
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
