# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""merge divergent heads (036b, 046, 051) into a single head

Three parallel migration branches were never merged, leaving the chain with
multiple heads so ``alembic upgrade head`` could not resolve a single target.
This no-op merge unifies them (#9759).

Revision ID: 20260608_052
Revises: 20260524_036b, 20260527_046, 20260604_051
Create Date: 2026-06-08
"""
from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "20260608_052"
down_revision: Union[str, Sequence[str], None] = (
    "20260524_036b",
    "20260527_046",
    "20260604_051",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No schema change — merge node only."""


def downgrade() -> None:
    """No schema change — merge node only."""
