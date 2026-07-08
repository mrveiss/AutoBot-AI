# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add resource_grants table for scoped/shareable skills and agents (#11277)."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260708_068"
down_revision: Union[str, Sequence[str], None] = "20260708_067"  # verify via `alembic heads`
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "resource_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=255), nullable=False),
        sa.Column("grantee_type", sa.String(length=16), nullable=False),
        sa.Column("grantee_id", sa.String(length=255), nullable=False),
        sa.Column("permission", sa.String(length=16), nullable=False, server_default="use"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "resource_type",
            "resource_id",
            "grantee_type",
            "grantee_id",
            name="uq_resource_grants_target",
        ),
    )
    op.create_index("ix_resource_grants_resource_type", "resource_grants", ["resource_type"])
    op.create_index("ix_resource_grants_resource_id", "resource_grants", ["resource_id"])
    op.create_index("ix_resource_grants_grantee_id", "resource_grants", ["grantee_id"])


def downgrade() -> None:
    op.drop_index("ix_resource_grants_grantee_id", table_name="resource_grants")
    op.drop_index("ix_resource_grants_resource_id", table_name="resource_grants")
    op.drop_index("ix_resource_grants_resource_type", table_name="resource_grants")
    op.drop_table("resource_grants")
