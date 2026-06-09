# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""LLC label SQLAlchemy models (GH#8254).

``llc_labels``            — per-company label definitions.
``llc_work_item_labels``  — M:N join table between work items and labels.
"""

import uuid
from datetime import datetime
from typing import List, Optional

import sqlalchemy as sa
from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base

_DEFAULT_COLORS = [
    "#ef4444",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#3b82f6",
    "#8b5cf6",
    "#ec4899",
    "#6b7280",
    "#0ea5e9",
    "#84cc16",
    "#f43f5e",
]


def _next_default_color(index: int) -> str:
    return _DEFAULT_COLORS[index % len(_DEFAULT_COLORS)]


class LLCLabel(Base):
    """A named, coloured tag that can be attached to work items."""

    __tablename__ = "llc_labels"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_llc_labels_company_name"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    color: Mapped[str] = mapped_column(String(7), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    created_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    work_item_labels: Mapped[List["LLCWorkItemLabel"]] = relationship(
        "LLCWorkItemLabel",
        back_populates="label",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class LLCWorkItemLabel(Base):
    """Join table — assignment of a label to a work item."""

    __tablename__ = "llc_work_item_labels"
    __table_args__ = (UniqueConstraint("work_item_id", "label_id", name="uq_llc_work_item_labels"),)

    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_work_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    label_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("llc_labels.id", ondelete="CASCADE"),
        primary_key=True,
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
    assigned_by: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    label: Mapped["LLCLabel"] = relationship("LLCLabel", back_populates="work_item_labels")
