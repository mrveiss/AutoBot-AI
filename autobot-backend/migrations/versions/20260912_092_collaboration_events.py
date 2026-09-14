# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create collaboration_events table (#16460).

Persisted history for the collaboration activity feed and secret-share
notifications. #16443 delivered both live-only, over
websocket/presence.py's generic broadcast relay -- a client not connected at
the moment of a broadcast, or one that reconnects, saw nothing before that
point. This table is the durable copy; ``GET /sessions/{id}/events`` reads
it back.

Source of truth: models/collaboration_event.py :: CollaborationEvent.

NO DATA LOSS: this migration only creates a new table and its indexes.
Nothing existing is altered or dropped.

Idempotent: guarded by ``has_table``.

Revision ID: 20260912_092
Revises: 20260912_091
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from migrations.guards import has_table

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------

revision: str = "20260912_092"
down_revision: Union[str, None] = "20260912_091"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("collaboration_events"):
        return
    op.create_table(
        "collaboration_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "session_id",
            sa.String(128),
            sa.ForeignKey("session_collaborations.session_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "timestamp",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_collaboration_events_session_id", "collaboration_events", ["session_id"])
    op.create_index("ix_collaboration_events_kind", "collaboration_events", ["kind"])
    op.create_index("ix_collaboration_events_user_id", "collaboration_events", ["user_id"])
    op.create_index("ix_collaboration_events_timestamp", "collaboration_events", ["timestamp"])
    # The list-recent query pattern is always "one session, newest first".
    op.create_index(
        "ix_collaboration_events_session_timestamp",
        "collaboration_events",
        ["session_id", "timestamp"],
    )


def downgrade() -> None:
    # Forward-only, consistent with every other migration in this chain.
    pass
