# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""LLC sprint hierarchy — portfolios, programs, projects, sprints (GH#8219).

Revision ID: 20260523_030
Revises: 20260523_029
Create Date: 2026-05-23

Creates:
  llc_portfolios  — top-level portfolio (name, status)
  llc_programs    — program within a portfolio
  llc_projects    — project within a program (owns sprints)
  llc_sprints     — time-boxed sprint within a project

Wires deferred FKs from 20260523_022:
  llc_work_items.project_id → llc_projects.id
  llc_work_items.sprint_id  → llc_sprints.id

Adds auto_rollover column to llc_projects for per-project rollover
behaviour override (null = use company default).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from migrations.guards import drop_pg_enum, ensure_pg_enum, pg_enum

revision: str = "20260523_030"
down_revision: Union[str, None] = "20260523_029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_portfolio_status = pg_enum("portfoliostatus", "active", "paused", "archived")
_program_status = pg_enum("programstatus", "active", "paused", "archived")
_project_status = pg_enum(
    "projectstatus",
    "backlog",
    "planned",
    "in_progress",
    "completed",
    "cancelled",
)
_sprint_status = pg_enum(
    "sprintstatus",
    "planning",
    "active",
    "review",
    "retrospective",
    "closed",
    "cancelled",
)


def upgrade() -> None:
    # -- Create ENUMs --
    ensure_pg_enum(_portfolio_status)
    ensure_pg_enum(_program_status)
    ensure_pg_enum(_project_status)
    ensure_pg_enum(_sprint_status)

    # -- llc_portfolios --
    op.create_table(
        "llc_portfolios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", _portfolio_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llc_portfolios_company_id", "llc_portfolios", ["company_id"])
    op.create_index("ix_llc_portfolios_status", "llc_portfolios", ["status"])

    # -- llc_programs --
    op.create_table(
        "llc_programs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "portfolio_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_portfolios.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", _program_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llc_programs_company_id", "llc_programs", ["company_id"])
    op.create_index("ix_llc_programs_portfolio_id", "llc_programs", ["portfolio_id"])
    op.create_index("ix_llc_programs_status", "llc_programs", ["status"])

    # -- llc_projects --
    op.create_table(
        "llc_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "program_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_programs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "goal_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_goals.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", _project_status, nullable=False, server_default="backlog"),
        sa.Column("lead_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("lead_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("target_date", sa.Date, nullable=True),
        sa.Column("env", JSONB, nullable=True),
        sa.Column("auto_rollover", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llc_projects_company_id", "llc_projects", ["company_id"])
    op.create_index("ix_llc_projects_program_id", "llc_projects", ["program_id"])
    op.create_index("ix_llc_projects_status", "llc_projects", ["status"])

    # -- llc_sprints --
    op.create_table(
        "llc_sprints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "project_id",
            UUID(as_uuid=True),
            sa.ForeignKey("llc_projects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("goal_description", sa.Text, nullable=True),
        sa.Column("start_date", sa.Date, nullable=True),
        sa.Column("end_date", sa.Date, nullable=True),
        sa.Column("status", _sprint_status, nullable=False, server_default="planning"),
        sa.Column("committed_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("actual_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("pending_close_approval_id", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_llc_sprints_company_id", "llc_sprints", ["company_id"])
    op.create_index("ix_llc_sprints_project_id", "llc_sprints", ["project_id"])
    op.create_index("ix_llc_sprints_status", "llc_sprints", ["status"])
    op.create_index("ix_llc_sprints_end_date", "llc_sprints", ["end_date"])

    # -- Wire deferred FKs from 20260523_022 --
    op.create_foreign_key(
        "fk_llc_work_items_project_id",
        "llc_work_items",
        "llc_projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_llc_work_items_sprint_id",
        "llc_work_items",
        "llc_sprints",
        ["sprint_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # -- Work item rollover support columns --
    op.add_column(
        "llc_work_items",
        sa.Column("backlog_position", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "llc_work_items",
        sa.Column("needs_triage", sa.Boolean, nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_constraint("fk_llc_work_items_sprint_id", "llc_work_items", type_="foreignkey")
    op.drop_constraint("fk_llc_work_items_project_id", "llc_work_items", type_="foreignkey")

    op.drop_index("ix_llc_sprints_end_date", "llc_sprints")
    op.drop_index("ix_llc_sprints_status", "llc_sprints")
    op.drop_index("ix_llc_sprints_project_id", "llc_sprints")
    op.drop_index("ix_llc_sprints_company_id", "llc_sprints")
    op.drop_table("llc_sprints")

    op.drop_index("ix_llc_projects_status", "llc_projects")
    op.drop_index("ix_llc_projects_program_id", "llc_projects")
    op.drop_index("ix_llc_projects_company_id", "llc_projects")
    op.drop_table("llc_projects")

    op.drop_index("ix_llc_programs_status", "llc_programs")
    op.drop_index("ix_llc_programs_portfolio_id", "llc_programs")
    op.drop_index("ix_llc_programs_company_id", "llc_programs")
    op.drop_table("llc_programs")

    op.drop_index("ix_llc_portfolios_status", "llc_portfolios")
    op.drop_index("ix_llc_portfolios_company_id", "llc_portfolios")
    op.drop_table("llc_portfolios")

    op.drop_column("llc_work_items", "needs_triage")
    op.drop_column("llc_work_items", "backlog_position")

    drop_pg_enum(_sprint_status)
    drop_pg_enum(_project_status)
    drop_pg_enum(_program_status)
    drop_pg_enum(_portfolio_status)
