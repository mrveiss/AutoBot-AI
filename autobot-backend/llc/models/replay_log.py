# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""RunReplayLog model — records inputs and events for replay/debugging (GH#9034).

Each row captures everything needed to re-execute a heartbeat run:
- inputs_snapshot: the full context dict passed to _dispatch_adapter
- agent_snapshot: the agent config dict (adapter_type, adapter_config, etc.)
- recorded_events: parsed JSONL events from subprocess output OR in-process
  log output; stored as a list of dicts; capped at LLC_REPLAY_EVENT_CAP entries.
- output_text: final output / last known output string (last lines of JSONL or
  in-process response repr), capped at LLC_REPLAY_OUTPUT_CAP bytes.
- replay_of_run_id: NULL for original recordings; set when this is a replay run.
- final_status: terminal status string from the run (completed/failed/etc.)
"""

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from user_management.models.base import Base


class LLCRunReplayLog(Base):
    """Persisted replay log for a single heartbeat run (GH#9034)."""

    __tablename__ = "llc_run_replay_logs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=sa.text("gen_random_uuid()"),
    )

    # FK to llc_heartbeat_runs; SET NULL on delete so logs survive run pruning.
    run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # When set, this log belongs to a replay-of-original run.
    replay_of_run_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        sa.ForeignKey("llc_heartbeat_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(sa.String(255), nullable=False, index=True)

    # Full context dict passed to _dispatch_adapter (prompt, work-item, etc.).
    inputs_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Agent config dict (adapter_type, adapter_config, heartbeat_cron, etc.).
    agent_snapshot: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSONB, nullable=True)

    # Parsed JSONL events (tool calls, results, messages) from subprocess output
    # OR structured log entries for in-process agents.  Stored as a JSON array.
    recorded_events: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSONB, nullable=True)

    # Final output text (last lines of subprocess JSONL or response repr).
    output_text: Mapped[Optional[str]] = mapped_column(sa.Text, nullable=True)

    # Terminal status of the run at recording time.
    final_status: Mapped[Optional[str]] = mapped_column(sa.String(32), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
        index=True,
    )
