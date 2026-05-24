# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC heartbeat run model (GH#8225/GH#8228).

Defines the schema shared by HeartbeatScheduler (GH#8225) and LivenessMonitor
(GH#8228). Both issues read and write this table.
"""

import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base

from .enums import HeartbeatInvocationSource, HeartbeatRunStatus


class LLCHeartbeatRun(Base):
    """Persisted record of a single heartbeat invocation.

    company_id matches the UUID PK of the organizations table (GH#8225 note:
    PR #8481 creates this column as UUID NOT NULL — callers must resolve a
    valid org UUID before inserting).
    """

    __tablename__ = "llc_heartbeat_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)

    invocation_source: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=HeartbeatInvocationSource.SCHEDULER.value,
    )
    status: Mapped[str] = mapped_column(
        sa.String(32),
        nullable=False,
        server_default=HeartbeatRunStatus.QUEUED.value,
        index=True,
    )

    work_item_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    started_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True)
    error: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)
    external_run_id: Mapped[Optional[str]] = mapped_column(sa.Text(), nullable=True)
    context_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Rate-limit retry fields (GH#8204).
    # retry_after: when the scheduler should next re-dispatch this agent.
    # retry_count: number of rate-limit retries so far (drives exponential backoff).
    retry_after: Mapped[Optional[datetime]] = mapped_column(sa.DateTime(timezone=True), nullable=True, index=True)
    retry_count: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="0")

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
    )
