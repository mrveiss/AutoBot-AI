# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add checkout_intent column to llc_work_items (GH#9532).

Revision ID: 20260611_054
Revises: 20260608_053
Create Date: 2026-06-11 00:00:00.000000

Adds an optional free-text ``checkout_intent`` column to ``llc_work_items``
that stores the agent's declared intent at checkout time for the audit trail.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260611_054"
down_revision: Union[str, None] = "20260608_053"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_work_items",
        sa.Column("checkout_intent", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llc_work_items", "checkout_intent")
