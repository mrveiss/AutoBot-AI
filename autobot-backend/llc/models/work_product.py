# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC work product model — artifacts produced by agents on work item completion (GH#8242)."""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from user_management.models.base import Base

from .enums import WorkProductType


class LLCWorkProduct(Base):
    """Artifact produced by an agent during or after completing a work item.

    ``kb_indexed`` is set to True by ArtifactIngestor after the content has
    been chunked and indexed into the project ChromaDB collection.
    """

    __tablename__ = "llc_work_products"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    work_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    heartbeat_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    type: Mapped[str] = mapped_column(
        sa.Enum(WorkProductType, name="workproducttype", create_type=False),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    content_text: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    storage_path: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    url: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    kb_indexed: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )

    work_item: Mapped["LLCWorkItem"] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "LLCWorkItem",
        back_populates="work_products",
        lazy="selectin",
    )
