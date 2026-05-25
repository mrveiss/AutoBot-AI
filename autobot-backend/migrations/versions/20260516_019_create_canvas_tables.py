"""Create canvas, canvas_cell, canvas_undo_event tables.

Revision ID: 20260516_019
Revises: 20260422_018
Create Date: 2026-05-16 07:00:00.000000

MVA-359: Live Canvas backend — Phase 1.
Schema includes version + locked_by from day 1 for Phase 3 multi-user
forward-compatibility (no concurrency enforcement in Phase 1).
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "20260516_019"
down_revision: str | None = "20260422_018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "canvas",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("title", sa.String(512), nullable=False, server_default="Untitled Canvas"),
        sa.Column("save_token", UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
        sa.Column("undo_cursor", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_canvas_user_id", "canvas", ["user_id"])

    op.create_table(
        "canvas_cell",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("canvas_id", UUID(as_uuid=True), sa.ForeignKey("canvas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("type", sa.String(50), nullable=False, server_default="text"),
        sa.Column("content", sa.Text, nullable=False, server_default=""),
        sa.Column("state", sa.String(50), nullable=False, server_default="committed"),
        sa.Column("owner", sa.String(50), nullable=False, server_default="user"),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("locked_by", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_canvas_cell_canvas_id", "canvas_cell", ["canvas_id"])
    op.create_index("ix_canvas_cell_user_id", "canvas_cell", ["user_id"])
    op.create_index("ix_canvas_cell_position", "canvas_cell", ["canvas_id", "position"])

    op.create_table(
        "canvas_undo_event",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("canvas_id", UUID(as_uuid=True), sa.ForeignKey("canvas.id", ondelete="CASCADE"), nullable=False),
        sa.Column("seq", sa.Integer, nullable=False),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("ix_canvas_undo_event_canvas_id", "canvas_undo_event", ["canvas_id"])
    op.create_index("ix_canvas_undo_event_seq", "canvas_undo_event", ["canvas_id", "seq"])


def downgrade() -> None:
    op.drop_table("canvas_undo_event")
    op.drop_table("canvas_cell")
    op.drop_table("canvas")
