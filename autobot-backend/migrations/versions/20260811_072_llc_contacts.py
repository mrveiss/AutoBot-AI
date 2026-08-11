# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_contacts table (#13969).

A contact is a human who appears in a process (the supplier you email, the
customer you call) with no account and no login path — deliberately never a
``users`` row. Company-scoped like ``llc_company_memberships`` /
``llc_secrets`` (no FK to a companies table, matching that existing pattern);
one contact belongs to exactly one ``company_id`` (see
``llc/models/contact.py`` module docstring for the cross-company-sharing
follow-up decision this defers).

Purely additive: new table only, no existing column/table touched.

Revision ID: 20260811_072
Revises: 20260730_071
Create Date: 2026-08-11 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260811_072"
down_revision: Union[str, None] = "20260730_071"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "llc_contacts",
        # No server_default gen_random_uuid() — the ORM always supplies id
        # explicitly (ContactService.create), mirroring llc_secrets (#8217).
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("phone", sa.String(64), nullable=True),
        sa.Column("role_title", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
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
    )
    op.create_index("ix_llc_contacts_company_id", "llc_contacts", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_llc_contacts_company_id", table_name="llc_contacts")
    op.drop_table("llc_contacts")
