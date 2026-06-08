# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC review gate policy model (GH#8234).

One row per (company, item_type) pair — defines whether human review is
required before a work item of that type can be marked done.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

from .enums import WorkItemType


class LLCReviewGatePolicy(Base):
    """Per-company, per-item-type review gate configuration."""

    __tablename__ = "llc_review_gate_policies"
    __table_args__ = (sa.UniqueConstraint("company_id", "item_type", name="uq_review_gate_company_item_type"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    item_type: Mapped[str] = mapped_column(
        sa.Enum(WorkItemType, name="workitemtype", create_type=False),
        nullable=False,
    )
    requires_human_review: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")
    reviewer_role: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=sa.func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        onupdate=sa.func.now(),
    )
