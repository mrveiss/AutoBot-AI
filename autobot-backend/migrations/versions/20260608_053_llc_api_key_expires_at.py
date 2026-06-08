# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add expires_at to llc_agent_api_keys (GH#9623).

Revision ID: 20260608_053
Revises: 20260608_052
Create Date: 2026-06-08

Ephemeral run-scoped heartbeat keys are revoked when the run finishes, but a
scheduler crash mid-run would leave the key valid forever. ``expires_at`` is a
defense-in-depth TTL backstop so such keys self-expire even if revocation never
runs. Existing keys get NULL (never expire) — behavior unchanged.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260608_053"
down_revision: Union[str, None] = "20260608_052"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "llc_agent_api_keys",
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("llc_agent_api_keys", "expires_at")
