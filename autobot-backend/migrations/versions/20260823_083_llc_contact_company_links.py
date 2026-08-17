# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_contact_company_links — contacts shared across companies (#13998).

Owner decision: a contact is one row per human, shared, with visibility granted
per company through this table instead of a copy per company.

**Non-destructive on purpose.** This migration adds the table and backfills
exactly one link per existing contact, from the ``company_id`` that row already
carries. Nothing is merged and nothing is deleted:

* De-duplicating history means deciding two rows are the same human. Matching on
  email or name is a guess, and a wrong guess fuses two people's PII into one
  record — irreversible, and invisible afterwards. Merging is therefore an
  explicit operation a human performs, not something a migration does silently.
* ``llc_contacts.company_id`` is left in place. Readers move to the link table
  first; dropping the column is a follow-up, so there is no window where a
  reader depends on a column that is already gone.

The backfill is idempotent — re-running inserts no duplicate links, because the
select excludes contacts that already have one.

Revision ID: 20260823_083
Revises: 20260822_082
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260823_083"
down_revision: Union[str, None] = "20260822_082"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXED_COLUMNS = ("contact_id", "company_id")


def upgrade() -> None:
    op.create_table(
        "llc_contact_company_links",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("contact_id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
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
        sa.UniqueConstraint("contact_id", "company_id", name="uq_llc_contact_company_links_contact_company"),
    )
    for column in _INDEXED_COLUMNS:
        op.create_index(f"ix_llc_contact_company_links_{column}", "llc_contact_company_links", [column])

    # Backfill: one link per existing contact, from the company it already
    # belongs to. `NOT EXISTS` rather than `ON CONFLICT` so the intent is
    # visible and the statement is safe to re-run.
    op.execute(sa.text("""
            INSERT INTO llc_contact_company_links (id, contact_id, company_id)
            SELECT gen_random_uuid(), c.id, c.company_id
            FROM llc_contacts AS c
            WHERE c.company_id IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1
                  FROM llc_contact_company_links AS l
                  WHERE l.contact_id = c.id AND l.company_id = c.company_id
              )
            """))


def downgrade() -> None:
    """Drop the links. Contacts keep their ``company_id``, so nothing is lost.

    Safe precisely because the upgrade never removed that column or merged any
    rows — the pre-migration state is still fully described by the contacts
    table alone.
    """
    for column in _INDEXED_COLUMNS:
        op.drop_index(f"ix_llc_contact_company_links_{column}", table_name="llc_contact_company_links")
    op.drop_table("llc_contact_company_links")
