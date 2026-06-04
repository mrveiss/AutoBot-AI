# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add token-based budget mode to llc_agent_budgets (GH#8997).

Revision ID: 20260604_036
Revises: 20260523_035
Create Date: 2026-06-04

Adds support for token-based budgets alongside dollar-based budgets:
- budget_mode: 'dollars' (default) or 'tokens'
- token_limit: monthly token allowance (nullable, for TOKENS mode)
- tokens_spent: token consumption counter (tracked in both modes)

All existing rows default to 'dollars' mode with tokens_spent=0.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260604_036"
down_revision: Union[str, None] = "20260531_050"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add budget_mode column (defaults to 'dollars' for existing rows)
    op.add_column(
        "llc_agent_budgets",
        sa.Column("budget_mode", sa.String(32), nullable=False, server_default="dollars"),
    )

    # Add token_limit column (nullable, used when budget_mode='tokens')
    op.add_column(
        "llc_agent_budgets",
        sa.Column("token_limit", sa.BigInteger, nullable=True),
    )

    # Add tokens_spent column (tracked in both modes for analytics)
    op.add_column(
        "llc_agent_budgets",
        sa.Column("tokens_spent", sa.BigInteger, nullable=False, server_default="0"),
    )

    # Create index on budget_mode for filtering queries
    op.create_index("ix_llc_agent_budgets_budget_mode", "llc_agent_budgets", ["budget_mode"])


def downgrade() -> None:
    op.drop_index("ix_llc_agent_budgets_budget_mode", table_name="llc_agent_budgets")
    op.drop_column("llc_agent_budgets", "tokens_spent")
    op.drop_column("llc_agent_budgets", "token_limit")
    op.drop_column("llc_agent_budgets", "budget_mode")
