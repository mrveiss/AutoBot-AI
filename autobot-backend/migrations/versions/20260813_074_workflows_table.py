# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add workflows table (#14210).

Gives a workflow a durable, company-scoped identity. Sibling of
``workflow_permissions`` (20251224_001 era) / ``workflow_audit_log`` — those
existed with no ``workflows`` table behind them; workflows themselves lived
only in Redis or a plain in-memory dict (see ``models/workflow.py`` module
docstring). Foundation only: no process node, no canvas, no reconciliation of
the Redis/in-memory stores onto this table (#14210's explicitly deferred
"step 2").

Guarded with ``has_table`` before create, following the established
drift-safe idiom (20260629_063, 20260630_064, 20260812_073): a database that
already carries a same-named table from an out-of-band path must not hard-fail
this migration. ``op.create_table`` (not raw SQL) is used so the table name
stays a literal the probe ladder's AST extraction can see (required by
``tests/migrations/test_probe_ladder_selfcheck.py``) — no TIMESTAMPTZ_MARKERS
registration is needed because this revision is fully observable through its
``Artifacts.tables`` entry.

Purely additive.

Revision ID: 20260813_074
Revises: 20260812_073
Create Date: 2026-08-13 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

from migrations.guards import has_table

revision: str = "20260813_074"
down_revision: Union[str, None] = "20260812_073"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("workflows"):
        return

    op.create_table(
        "workflows",
        sa.Column("workflow_id", sa.String(255), primary_key=True),
        # Nullable: legacy rows backfilled from Redis carry no company
        # attribution in their source data (models/workflow.py docstring).
        sa.Column("company_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="planned"),
        sa.Column("source", sa.String(50), nullable=False, server_default="created"),
        sa.Column(
            "definition",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
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
    op.create_index("ix_workflows_company_id", "workflows", ["company_id"])


def downgrade() -> None:
    if not has_table("workflows"):
        return
    op.drop_index("ix_workflows_company_id", table_name="workflows")
    op.drop_table("workflows")
