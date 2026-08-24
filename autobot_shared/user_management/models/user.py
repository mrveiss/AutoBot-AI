# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical ``User`` core shared by both backends (#12647).

``user_management/models/user.py`` was one of the last two files still forked
between ``autobot-backend`` and ``autobot-slm-backend``. Unlike the six model
files relocated in #13130, the drift here is **not** cosmetic: SLM is a strict
subset, and backend additionally carries five activity-tracking relationships
(#871) pointing at ``models.activities`` classes that exist only in
``autobot-backend``.

Per the owner's decision on #12645/#12647, the shape is an **abstract core**,
not a single concrete class:

- ``UserCore`` (here) owns every column, relationship and method the two
  backends already share — one definition, one place to fix a bug.
- Each backend keeps its own concrete ``User(UserCore)`` with
  ``__tablename__`` and whatever is genuinely local to it. Backend's activity
  relationships stay in ``autobot-backend`` because
  ``TerminalActivityModel`` & co. do not exist in SLM's registry; declaring
  them on the shared core would fail ``configure_mappers()`` on the SLM side.

This carries **no database change on either side**: the abstract class is not
mapped (no ``__tablename__``), and every column it contributes is one both
backends already had, with identical type, nullability and index. Only the
physical location of the declaration moved.

Style note: the two forks disagreed on ``Mapped[Optional["X"]]`` (backend) vs
``Mapped["X | None"]`` (SLM). Resolved toward the ``X | None`` form already
canonical in ``autobot_shared/user_management/models/base.py`` and the six
models moved in #13130.

Foreign-key columns and relationships are wrapped in ``declared_attr`` — a
SQLAlchemy requirement for declarative mixins/abstract bases, since neither a
``ForeignKey`` nor a ``relationship()`` object can be shared between two mapped
classes. ``TenantMixin.org_id`` in ``base.py`` already follows this pattern.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, declared_attr, mapped_column, relationship

from autobot_shared.time_utils import now_utc
from autobot_shared.user_management.models.base import Base

if TYPE_CHECKING:
    from user_management.models.api_key import APIKey
    from user_management.models.mfa import UserMFA
    from user_management.models.organization import Organization
    from user_management.models.role import UserRole
    from user_management.models.sso import UserSSOLink
    from user_management.models.team import TeamMembership


def resolve_display_name(
    display_name: str | None,
    username: str | None,
    fallback: str | None = None,
) -> str | None:
    """The display-label rule for callers that hold columns, not an entity (#13957).

    :attr:`UserCore.full_name` is the same rule and is preferred wherever a
    loaded ``User`` (or a ``select(User.full_name)`` column) is available. This
    function exists for the case ``full_name`` genuinely cannot serve: a LEFT
    OUTER JOIN onto ``users`` where the user row may be absent entirely, so
    ``username`` — ``NOT NULL`` in the table — still arrives as ``NULL``.

    It carries the **union** of the fallback depths the five copies had drifted
    to, rather than picking one and silently shortening the others:

    - ``display_name``, then ``username`` — every copy agreed this far;
    - then *fallback*, the extra rung ``llc.api.companies._compose_human_nodes``
      needed so an orphaned membership renders its user id instead of nothing;
    - then ``None``, which ``llc.api.work_items._assignee_display`` relies on to
      distinguish "no assignee" from a named one.

    Passing no *fallback* therefore reproduces the two-rung behaviour exactly;
    no call site loses a rung it had.

    Args:
        display_name: The user's optional display name.
        username: The user's username; ``None`` only when the row is absent.
        fallback: Final rung when neither name is present — e.g. ``str(user_id)``.

    Returns:
        The first non-empty value of the three, or ``None`` if all are empty.
    """
    return display_name or username or fallback or None


class UserCore(Base):
    """Shared core of the ``users`` table.

    Abstract: it declares no ``__tablename__`` and is never mapped. Each
    backend's concrete ``User`` subclasses it and supplies ``__tablename__``.

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

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    # Organization association (nullable for platform admins in provider mode)
    @declared_attr
    def org_id(cls) -> Mapped[uuid.UUID | None]:
        return mapped_column(
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

    password_hash: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,  # Nullable for SSO-only users
    )

    # Profile
    display_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    avatar_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    bio: Mapped[str | None] = mapped_column(
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
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Soft delete
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Relationships
    @declared_attr
    def organization(cls) -> Mapped["Organization | None"]:
        return relationship(
            "Organization",
            back_populates="users",
        )

    @declared_attr
    def team_memberships(cls) -> Mapped[list["TeamMembership"]]:
        return relationship(
            "TeamMembership",
            back_populates="user",
            cascade="all, delete-orphan",
        )

    @declared_attr
    def user_roles(cls) -> Mapped[list["UserRole"]]:
        return relationship(
            "UserRole",
            back_populates="user",
            foreign_keys="[UserRole.user_id]",
            cascade="all, delete-orphan",
        )

    @declared_attr
    def api_keys(cls) -> Mapped[list["APIKey"]]:
        return relationship(
            "APIKey",
            back_populates="user",
            foreign_keys="[APIKey.user_id]",
            cascade="all, delete-orphan",
        )

    @declared_attr
    def sso_links(cls) -> Mapped[list["UserSSOLink"]]:
        return relationship(
            "UserSSOLink",
            back_populates="user",
            cascade="all, delete-orphan",
        )

    @declared_attr
    def mfa(cls) -> Mapped["UserMFA | None"]:
        return relationship(
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
        self.deleted_at = now_utc()
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

    @hybrid_property
    def full_name(self) -> str:
        """The person's display label: ``display_name``, falling back to ``username``.

        A ``hybrid_property`` rather than a plain ``property`` (#13957). The rule
        was re-implemented at five call sites for one reason: a plain property is
        only reachable from a loaded entity, so any ``select(User.display_name,
        User.username)`` column tuple had to spell the fallback out again. Three
        of those copies had already drifted to different fallback depths. The
        ``expression`` half below makes the identical rule usable directly in a
        column select, so there is one place to change how a person is named.

        ``username`` is ``NOT NULL``, so this is non-``None`` for any row that
        exists. It is **not** safe for an outer join, where the whole user row
        may be absent and both columns arrive as ``NULL`` — that case needs a
        third fallback rung and belongs to :func:`resolve_display_name`.
        """
        return self.display_name or self.username

    @full_name.expression  # type: ignore[no-redef]
    def full_name(cls):  # noqa: N805 - SQLAlchemy hybrid expression takes the class
        """SQL half of :meth:`full_name`, usable inside ``select(...)``.

        ``coalesce`` and Python's ``or`` are not the same test: ``coalesce``
        returns the first non-NULL, while ``or`` skips any falsy value. They
        differ only for an empty-string ``display_name``, which the Python half
        skips and this would return. ``display_name`` is normalised to ``None``
        rather than ``""`` on write (see ``user_service.create_user``), so no
        stored row distinguishes them; ``NULLIF`` keeps the two halves identical
        even if one ever does.
        """
        return func.coalesce(func.nullif(cls.display_name, ""), cls.username)

    def record_login(self) -> None:
        """Record a successful login."""
        self.last_login_at = now_utc()

    def verify_email(self) -> None:
        """Mark email as verified."""
        self.is_verified = True
        self.email_verified_at = now_utc()
