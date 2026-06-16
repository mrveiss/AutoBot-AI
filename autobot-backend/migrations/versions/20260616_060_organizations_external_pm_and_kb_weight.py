# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Add organizations.external_pm_type / external_pm_config / kb_inheritance_weight.

Revision ID: 20260616_060
Revises: 20260615_059
Create Date: 2026-06-16

GH#10189: these three columns exist on the ``Organization`` ORM model but no
migration ever added them (migration 023 added the other LLC-extension columns).
A migration-built ``organizations`` table was therefore missing them, so any ORM
read/write touching them (org create, LLC company onboarding) failed with
``UndefinedColumnError``. Add them to match the model.

``kb_inheritance_weight`` is added with a temporary ``server_default`` so it
backfills existing rows, then the default is dropped so the column matches the
``create_all`` shape (NOT NULL, no server default — the ORM supplies 0.6).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column

revision: str = "20260616_060"
down_revision: Union[str, None] = "20260615_059"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if not has_column("organizations", "external_pm_type"):
        op.add_column("organizations", sa.Column("external_pm_type", sa.String(32), nullable=True))
    if not has_column("organizations", "external_pm_config"):
        op.add_column("organizations", sa.Column("external_pm_config", sa.Text(), nullable=True))
    if not has_column("organizations", "kb_inheritance_weight"):
        op.add_column(
            "organizations",
            sa.Column("kb_inheritance_weight", sa.Float(), nullable=False, server_default="0.6"),
        )
        op.alter_column("organizations", "kb_inheritance_weight", server_default=None)


def downgrade() -> None:
    for column in ("kb_inheritance_weight", "external_pm_config", "external_pm_type"):
        if has_column("organizations", column):
            op.drop_column("organizations", column)
