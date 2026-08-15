# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_roles — the durable anchor an occupant holds (#14221 step 1).

A role outlives its occupant: people are promoted or leave, and the role keeps
its responsibilities, tools and workflows. Until now a role was a ``String(50)``
on ``AgentOrgNode`` plus a display ``title``, so nothing could attach to it and
everything attached to the occupant instead.

Follows the sibling new-table migrations ``20260811_072_llc_contacts`` and
``20260523_028_llc_secrets``: plain ``op.create_table``. Deliberately **not**
``CREATE TABLE IF NOT EXISTS`` — that pattern belongs to the drift
reconciliations (``20260629_063``, ``20260812_073``), which re-add columns to
tables that had already been changed out-of-band. ``llc_roles`` is born here, so
there is no prior state to be tolerant of, and ``IF NOT EXISTS`` would instead
succeed silently against a pre-existing table whose schema does not match this
one — hiding exactly what a migration should surface.

Revision ID: 20260817_077
Revises: 20260816_076
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260817_077"
down_revision: Union[str, None] = "20260816_076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llc_roles",
        # No server_default gen_random_uuid() — the ORM always supplies id
        # explicitly (RoleService.create), mirroring llc_contacts / llc_secrets.
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Per company, not global: two companies may each have a "Head of Sales"
        # and they are different roles.
        sa.UniqueConstraint("company_id", "name", name="uq_llc_roles_company_name"),
    )
    op.create_index("ix_llc_roles_company_id", "llc_roles", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_roles_company_id", table_name="llc_roles")
    op.drop_table("llc_roles")
