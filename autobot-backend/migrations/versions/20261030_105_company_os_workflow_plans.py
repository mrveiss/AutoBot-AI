# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Workflow Planner plans: one JSONB document per revision (#19934).

Revision ID: 20261030_105
Revises: 20261025_104
Create Date: 2026-10-30 00:00:01.000000

``NO DATA LOSS``: one new table; nothing that exists is touched. ``status`` is a real column
so plan lists filter in SQL; the plan itself is the ``document``. Unique on
``(company_id, plan_key, revision)``, and a partial unique index allows one open
(not ``converted``) revision per plan (D14). Guarded with ``has_table`` for a database that
``create_all`` already built.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

from migrations.guards import has_table

revision: str = "20261030_105"
down_revision: Union[str, None] = "20261025_104"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("company_os_workflow_plans"):
        return
    op.create_table(
        "company_os_workflow_plans",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("plan_key", sa.String(64), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False, server_default="1"),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="draft"),
        sa.Column("document", JSONB, nullable=False),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("company_id", "plan_key", "revision", name="uq_company_os_workflow_plans_revision"),
    )
    op.create_index("ix_company_os_workflow_plans_company_id", "company_os_workflow_plans", ["company_id"])
    op.create_index("ix_company_os_workflow_plans_status", "company_os_workflow_plans", ["company_id", "status"])
    op.create_index(
        "uq_company_os_workflow_plans_one_open",
        "company_os_workflow_plans",
        ["company_id", "plan_key"],
        unique=True,
        postgresql_where=sa.text("status <> 'converted'"),
    )


def downgrade() -> None:
    if not has_table("company_os_workflow_plans"):
        return
    populated = op.get_bind().execute(sa.text("SELECT count(*) FROM company_os_workflow_plans")).scalar()
    if populated:
        raise NotImplementedError(
            f"20261030_105 downgrade is refused: {populated} workflow plan(s) exist. Dropping the table would "
            "discard them. Export and remove them first."
        )
    op.drop_table("company_os_workflow_plans")
