# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical Base SQLAlchemy Models and Mixins (#12647)

``user_management/models/base.py`` was forked across ``autobot-backend`` and
``autobot-slm-backend`` with two different, deliberate designs:

- **Backend** — ``Base(AsyncAttrs, DeclarativeBase)`` with ``created_at`` /
  ``updated_at`` baked directly into ``Base`` (every subclass gets them for
  free), ``eager_defaults=True`` (#12322), and ``AsyncAttrs`` (#11684) for
  greenlet-safe ``awaitable_attrs``. Backend's ``Base`` is also the
  declarative base for ~40 non-``user_management`` model files
  (``llc/models/*``, ``models/*.py``, ``canvas/models.py``), so its
  timestamp behaviour cannot change without touching all of them.
- **SLM** — plain ``Base(DeclarativeBase)`` with a *separate*
  ``TimestampMixin`` that models opt into per-table, and
  ``sqlalchemy.dialects.postgresql.UUID`` for UUID columns.

Per the owner's 2026-07-31 decision on #12645/#12647, this is a **new**
canonical base, not an adoption of either fork:

1. ``AsyncAttrs`` and ``eager_defaults=True`` are preserved (the properties
   #4300/#11684 exist to protect).
2. The UUID column type is SLM's ``sqlalchemy.dialects.postgresql.UUID``, not
   backend's ``sqlalchemy.types.Uuid``. In SQLAlchemy 2.0, ``postgresql.UUID``
   is itself a subclass of the generic ``Uuid`` (``Emulated`` /
   ``NativeForEmulated``), so it compiles to the *same* native ``UUID`` DDL on
   Postgres and falls back to the same CHAR(32) emulation SQLite already used
   under the generic type — verified by compiling ``CREATE TABLE`` under both
   dialects. No migration is needed for this part of the change on either
   side.
3. Timestamps stay **baked into Base**, unconditionally, matching backend's
   existing (already-migrated, #10636-hardened) design — *not* switched to an
   opt-in mixin. Backend's ``Base`` backs ~40 non-``user_management`` models
   that rely on this today; making timestamps opt-in would silently drop
   ``created_at``/``updated_at`` ORM mapping from all of them. ``TimestampMixin``
   is kept as the no-op backward-compatibility alias backend already uses
   (#4300) — SLM's model files that spell out ``(Base, TimestampMixin)``
   keep working unchanged, since Base already supplies the same columns.

The one place this is *not* free: SLM's ``RolePermission`` and ``AuditLog``
models never opted into a ``TimestampMixin`` and have no ``updated_at``
column in the live SLM database (``AuditLog`` also lacks a matching
``created_at`` server-side column only via a locally-declared field, which is
unaffected). Baking timestamps into ``Base`` means these two SLM models start
expecting ``updated_at`` (and, for ``RolePermission``, ``created_at`` too).
This is the exact drift the backend itself hit and fixed in #10636 ("Base
gives every model both created_at and updated_at, but ... some tables [were]
created without updated_at") — the SLM migration added alongside this change
mirrors that already-shipped, idempotent, forward-safe pattern.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, declared_attr, mapped_column

from autobot_shared.time_utils import now_utc


class Base(AsyncAttrs, DeclarativeBase):
    """Base class for all ``user_management`` SQLAlchemy models.

    Provides automatic ``created_at``/``updated_at`` timestamp columns to all
    models (backend's design, #4300) — do not inherit from ``TimestampMixin``
    separately; it is a no-op alias kept only for backward compatibility.

    ``AsyncAttrs`` (#11684) mixes in ``awaitable_attrs`` — greenlet-safe async
    access to un-loaded relationships/columns under an ``AsyncSession``.

    UUID columns use ``sqlalchemy.dialects.postgresql.UUID`` (SLM's existing
    typing) rather than the generic ``sqlalchemy.types.Uuid`` — see module
    docstring: same compiled DDL on Postgres and SQLite, no migration implied
    by the type itself.
    """

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
        uuid.UUID: UUID(as_uuid=True),
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
    imports/references (#4300), and so SLM's existing ``(Base, TimestampMixin)``
    class declarations keep working unchanged (#12647): Base already supplies
    the same columns, so combining both is a no-op, not a duplicate mapping.
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
            UUID(as_uuid=True),
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
