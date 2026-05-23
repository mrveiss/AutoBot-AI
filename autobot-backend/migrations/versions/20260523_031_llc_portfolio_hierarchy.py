# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""LLC Portfolio → Program → Project → Sprint hierarchy tables (GH#8219).

Revision ID: 20260523_031
Revises: 20260523_030
Create Date: 2026-05-23
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "20260523_031"
down_revision = "20260523_030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "llc_portfolios",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("company_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_llc_portfolios_company_id", "llc_portfolios", ["company_id"])
    op.create_index("ix_llc_portfolios_status", "llc_portfolios", ["status"])

    op.create_table(
        "llc_programs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("portfolio_id", UUID(as_uuid=True), sa.ForeignKey("llc_portfolios.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_llc_programs_portfolio_id", "llc_programs", ["portfolio_id"])
    op.create_index("ix_llc_programs_status", "llc_programs", ["status"])

    op.create_table(
        "llc_projects",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("program_id", UUID(as_uuid=True), sa.ForeignKey("llc_programs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("status", sa.String(32), nullable=False, server_default="active"),
        sa.Column("owner_agent_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_llc_projects_program_id", "llc_projects", ["program_id"])
    op.create_index("ix_llc_projects_status", "llc_projects", ["status"])
    op.create_index("ix_llc_projects_owner_agent_id", "llc_projects", ["owner_agent_id"])

    op.create_table(
        "llc_sprints",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("project_id", UUID(as_uuid=True), sa.ForeignKey("llc_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(512), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="planning"),
        sa.Column("start_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("capacity_points", sa.Integer, nullable=True),
        sa.Column("velocity_actual", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_llc_sprints_project_id", "llc_sprints", ["project_id"])
    op.create_index("ix_llc_sprints_status", "llc_sprints", ["status"])


def downgrade() -> None:
    op.drop_table("llc_sprints")
    op.drop_table("llc_projects")
    op.drop_table("llc_programs")
    op.drop_table("llc_portfolios")
