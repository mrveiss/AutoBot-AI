# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Create llc_work_items and llc_work_item_comments tables.

Revision ID: 20260523_022
Revises: 20260522_021
Create Date: 2026-05-23 00:00:00.000000

GH#8213: Core work item hierarchy — Epic/Feature/PBI/Task/Bug/Subtask/Spike/Risk.
Single ``llc_work_items`` table with a ``type`` discriminator. Atomic checkout
via ``checkout_run_id`` + ``checkout_locked_at`` (Redis SET NX EX fence in the
service layer; DB lock column here for persistence).

ENUM types are created with ``checkfirst=True``. For ``workitemstatus``, an
``ALTER TYPE ... ADD VALUE IF NOT EXISTS`` call follows to ensure the ``ready``
value is present even when the enum pre-existed without it (e.g. from a manual
scaffold). The ``workitemtype``, ``workitemstatus``, and ``workitempriority``
enums are created once here and re-used wherever the LLC module references them.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from migrations.guards import drop_pg_enum, ensure_pg_enum, pg_enum

revision: str = "20260523_022"
down_revision: Union[str, None] = "20260522_021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_workitemtype = pg_enum(
    "workitemtype",
    "epic",
    "feature",
    "pbi",
    "task",
    "bug",
    "subtask",
    "spike",
    "risk",
)
_workitemstatus = pg_enum(
    "workitemstatus",
    "backlog",
    "ready",
    "in_progress",
    "in_review",
    "done",
    "cancelled",
    "blocked",
)
_workitempriority = pg_enum(
    "workitempriority",
    "critical",
    "high",
    "medium",
    "low",
)


def upgrade() -> None:
    bind = op.get_bind()
    ensure_pg_enum(_workitemtype)
    ensure_pg_enum(_workitemstatus)
    # Ensure 'ready' exists even when workitemstatus was pre-created without it.
    bind.execute(sa.text("ALTER TYPE workitemstatus ADD VALUE IF NOT EXISTS 'ready'"))
    ensure_pg_enum(_workitempriority)

    op.create_table(
        "llc_work_items",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", UUID(as_uuid=True), nullable=True),
        sa.Column("sprint_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "goal_id",
            UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "parent_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("type", _workitemtype, nullable=False),
        sa.Column("identifier", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("acceptance_criteria", JSONB, nullable=True),
        sa.Column(
            "labels",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "status",
            _workitemstatus,
            nullable=False,
            server_default="backlog",
        ),
        sa.Column(
            "priority",
            _workitempriority,
            nullable=False,
            server_default="medium",
        ),
        sa.Column("story_points", sa.Integer, nullable=True),
        sa.Column("assignee_type", sa.String(16), nullable=True),
        sa.Column("assignee_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("assignee_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("checkout_run_id", sa.Text, nullable=True),
        sa.Column("checkout_locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_by_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )

    op.create_index("ix_llc_work_items_company_id", "llc_work_items", ["company_id"])
    op.create_index("ix_llc_work_items_project_id", "llc_work_items", ["project_id"])
    op.create_index("ix_llc_work_items_sprint_id", "llc_work_items", ["sprint_id"])
    op.create_index("ix_llc_work_items_parent_id", "llc_work_items", ["parent_id"])
    op.create_index("ix_llc_work_items_status", "llc_work_items", ["status"])
    op.create_index("ix_llc_work_items_assignee_agent_id", "llc_work_items", ["assignee_agent_id"])
    op.create_index(
        "ix_llc_work_items_company_status",
        "llc_work_items",
        ["company_id", "status"],
    )

    op.create_table(
        "llc_work_item_comments",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "work_item_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_work_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("author_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_llc_work_item_comments_work_item_id",
        "llc_work_item_comments",
        ["work_item_id"],
    )
    op.create_index(
        "ix_llc_work_item_comments_company_id",
        "llc_work_item_comments",
        ["company_id"],
    )


def downgrade() -> None:
    op.drop_table("llc_work_item_comments")
    op.drop_table("llc_work_items")
    drop_pg_enum(_workitempriority)
    drop_pg_enum(_workitemstatus)
    drop_pg_enum(_workitemtype)
