# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create secret_dependencies — what depends on a secret (#10088 Task 8.2).

The dependency half of the auditable secrets graph: a service / agent / workflow that
consumes a secret at run time, one row per (secret, dependent). Guarded with
``migrations.guards`` so it is safe on databases where the table already exists.

Revision ID: 20260621_061
Revises: 20260616_060
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from migrations.guards import has_table

revision: str = "20260621_061"
down_revision: Union[str, None] = "20260616_060"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("secret_dependencies"):
        return
    op.create_table(
        "secret_dependencies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("secret_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dependent_kind", sa.String(length=32), nullable=False),
        sa.Column("dependent_id", sa.String(length=255), nullable=False),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["secret_id"], ["secrets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "secret_id", "dependent_kind", "dependent_id", name="uq_secret_dependencies_secret_dependent"
        ),
    )
    op.create_index("ix_secret_dependencies_secret_id", "secret_dependencies", ["secret_id"])
    op.create_index("ix_secret_dependencies_company_id", "secret_dependencies", ["company_id"])


def downgrade() -> None:
    if not has_table("secret_dependencies"):
        return
    op.drop_index("ix_secret_dependencies_company_id", table_name="secret_dependencies")
    op.drop_index("ix_secret_dependencies_secret_id", table_name="secret_dependencies")
    op.drop_table("secret_dependencies")
