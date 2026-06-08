# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add kb_summary column to llc_sprints (GH#8238).

Stores the LLM-generated sprint summary produced on sprint close.
Nullable TEXT — pre-existing rows remain NULL; populated on the next close.

Revision ID: 005
Revises: 004
Create Date: 2026-05-24
"""

import sqlalchemy as sa
from alembic import op

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "llc_sprints",
        sa.Column("kb_summary", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llc_sprints", "kb_summary")
