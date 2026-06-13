# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add linked_pr_urls to llc_work_items for GitHub PR integration (GH#9625).

Revision ID: 20260612_056
Revises: 20260612_055
Create Date: 2026-06-12 00:00:00.000000

Adds a JSONB ``linked_pr_urls`` column to ``llc_work_items`` storing the
list of GitHub PR URLs linked to the work item (via the link-pr endpoint
or the GitHub webhook auto-linker).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "20260612_056"
down_revision: Union[str, None] = "20260612_055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_work_items",
        sa.Column(
            "linked_pr_urls",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("llc_work_items", "linked_pr_urls")
