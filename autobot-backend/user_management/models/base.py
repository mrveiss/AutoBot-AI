# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Base SQLAlchemy Models and Mixins

Provides:
- Base declarative class for all models (includes created_at/updated_at)
- TenantMixin for multi-tenancy support
- TimestampMixin kept as no-op alias for backward compatibility (#4300)
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column
from sqlalchemy.types import Uuid

from autobot_shared.time_utils import now_utc


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all SQLAlchemy models.

    Provides automatic created_at/updated_at timestamp columns to all models.
    Models should inherit from Base only — do not inherit from TimestampMixin
    separately, as it will cause metaclass conflicts (#4300).

    #11684: mixes in ``AsyncAttrs`` so every model exposes ``awaitable_attrs`` —
    greenlet-safe async access to un-loaded relationships/columns under an
    AsyncSession. Purely additive (adds one accessor; no behavioral change).
    """

    # Timestamp columns provided to all models
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Use UUID as default type annotation for id columns
    type_annotation_map = {
        uuid.UUID: Uuid(as_uuid=True),
    }

    # #12322: eagerly fetch server-side default/onupdate columns (e.g.
    # ``updated_at``) via RETURNING on INSERT *and* UPDATE, for all models.
    # SQLAlchemy's default ``eager_defaults="auto"`` only does this for INSERT,
    # leaving onupdate columns expired after an UPDATE flush — a subsequent sync
    # attribute read (e.g. Pydantic response serialization outside the greenlet
    # context) then raises MissingGreenlet. This recurred twice (#12209 goals,
    # #12309 companies), each patched with a per-call ``session.refresh``.
    # Setting it here kills the whole class in one place and removes the extra
    # per-write refresh SELECT (RETURNING is fetched inline with the UPDATE).
    # Dialects without RETURNING (e.g. sqlite < 3.35) transparently fall back to
    # a post-UPDATE SELECT, so the column is still populated — never expired.
    __mapper_args__ = {"eager_defaults": True}


class TimestampMixin:
    """Backward compatibility alias for TimestampMixin.

    NOTE: Do NOT use this in class definitions anymore. All models should
    inherit from Base only. Base now includes created_at/updated_at columns
    automatically. This class is kept only for backward compatibility with
    imports/references (#4300).
    """


class TenantMixin:
    """
    Mixin for multi-tenant models.

    Adds org_id foreign key that references the organizations table.
    Models with this mixin are scoped to a specific organization.
    """

    @declared_attr
    def org_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(
            Uuid(as_uuid=True),
            ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        )


class SoftDeleteMixin:
    """Mixin for soft delete support."""

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )

    is_deleted: Mapped[bool] = mapped_column(
        default=False,
        nullable=False,
    )

    def soft_delete(self) -> None:
        """Mark the record as deleted."""
        self.is_deleted = True
        self.deleted_at = now_utc()

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.is_deleted = False
        self.deleted_at = None
