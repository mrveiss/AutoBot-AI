# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Migration 006: Add KB inheritance weight multiplier to organizations (GH#8241).

Adds:
  kb_inheritance_weight — FLOAT DEFAULT 0.6: weight decay multiplier for sub-company KB inheritance
"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("kb_inheritance_weight", sa.Float, nullable=False, server_default="0.6"),
    )


def downgrade() -> None:
    op.drop_column("organizations", "kb_inheritance_weight")
