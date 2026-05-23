# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC heartbeat run model (GH#8228).

Minimal table definition required by LivenessMonitor to detect and mark stuck
runs. The full HeartbeatScheduler (GH#8225) populates this table; this module
defines the schema shared by both issues.
"""

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCHeartbeatRun(Base):
    """One scheduler-dispatched or manually-triggered heartbeat run."""

    __tablename__ = "llc_heartbeat_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)

    invocation_source: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="scheduler"
    )
    status: Mapped[str] = mapped_column(
        sa.String(32), nullable=False, server_default="queued", index=True
    )

    # FK to the work item that was checked out during this run (nullable)
    work_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    external_run_id: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)
    context_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )
