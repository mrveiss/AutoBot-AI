# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Create chat_session_shares, the durable participant set of a shared chat (#18890).

Shares lived only in a Redis set with a 30-day TTL, so a participant lost access silently. This table is
the system of record; the Redis sets are projections rebuilt from it.

Also creates chat_session_share_adoption, the durable one-shot record that the Redis adoption finished, so a
lost Redis marker plus restored legacy keys can never re-insert a share that was unshared afterwards.

Source of truth: models/session_share.py :: SessionShare, SessionShareAdoption.

NO DATA LOSS: only creates a new table. Shares that exist only in Redis on an installed system are
copied into it by ``security.session_shares.adopt_redis_shares`` on first use after the update; a migration
does not read Redis.

Idempotent: each table is guarded by ``has_table``.

Revision ID: 20261120_116
Revises: 20261118_115
Create Date: 2026-11-20
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column, has_table

revision: str = "20261120_116"
down_revision: Union[str, None] = "20261118_115"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not has_table("chat_session_shares"):
        op.create_table(
            "chat_session_shares",
            sa.Column("session_id", sa.String(128), nullable=False),
            sa.Column("user_id", sa.String(255), nullable=False),
            sa.Column("shared_by", sa.String(255), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("session_id", "user_id"),
        )
        op.create_index("ix_chat_session_shares_user_id", "chat_session_shares", ["user_id"])
    if not has_table("chat_session_share_adoption"):
        op.create_table(
            "chat_session_share_adoption",
            sa.Column("name", sa.String(64), nullable=False),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.PrimaryKeyConstraint("name"),
        )
    # The columns ``Base`` gives every model (``autobot_shared/user_management/models/base.py``), for a table
    # an earlier run of this revision created without them.
    for table, column in (
        ("chat_session_shares", "updated_at"),
        ("chat_session_share_adoption", "created_at"),
        ("chat_session_share_adoption", "updated_at"),
    ):
        if not has_column(table, column):
            op.add_column(
                table, sa.Column(column, sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now())
            )


def downgrade() -> None:
    for table in ("chat_session_share_adoption", "chat_session_shares"):
        if has_table(table):
            op.drop_table(table)
