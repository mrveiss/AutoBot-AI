# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The table joining one SLM person to one main-app user (#10200).

Revision ID: 20261102_109
Revises: 20261101_108
Create Date: 2026-11-02 00:00:00.000000

``NO DATA LOSS``: a new, empty table. Downgrade drops only that table.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from migrations.guards import has_table

revision: str = "20261102_109"
down_revision: Union[str, None] = "20261106_113"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if has_table("person_links"):
        return
    op.create_table(
        "person_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("slm_user_id", UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("slm_user_id", name="uq_person_links_slm_user"),
        sa.UniqueConstraint("user_id", name="uq_person_links_user"),
    )


def downgrade() -> None:
    if has_table("person_links"):
        op.drop_table("person_links")
