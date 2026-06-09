# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Migration 005: Add external PM config columns to organizations (GH#8257).

Adds:
  external_pm_type   — nullable VARCHAR(32): jira | azure_devops | trello | asana | none
  external_pm_config — nullable TEXT: AES-256-encrypted JSON blob
"""

import sqlalchemy as sa
from alembic import op


def upgrade() -> None:
    op.add_column(
        "organizations",
        sa.Column("external_pm_type", sa.String(32), nullable=True),
    )
    op.add_column(
        "organizations",
        sa.Column("external_pm_config", sa.Text, nullable=True),
    )


def downgrade() -> None:
    op.drop_column("organizations", "external_pm_config")
    op.drop_column("organizations", "external_pm_type")
