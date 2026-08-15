# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_role_assignments — who holds a role, and for how long (#14221 step 2).

``ended_at IS NULL`` means the holder holds it now; a set ``ended_at`` means the
tenure is over and the row stays. Ending a tenure is an UPDATE, never a DELETE,
because work left behind still has to belong to the role.

Follows the sibling new-table migration ``20260811_072_llc_contacts``: plain ``op.create_table``, not
``CREATE TABLE IF NOT EXISTS``. The tolerant form belongs to the drift
reconciliations that re-add columns to tables already changed out-of-band; this
table is born here, so tolerating a pre-existing one would only hide a schema
mismatch a migration is supposed to surface.

Revision ID: 20260818_078
Revises: 20260816_076
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260818_078"
down_revision: Union[str, None] = "20260816_076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_HOLDER_KINDS = ("agent", "user", "contact")
_INDEXED_COLUMNS = (
    "company_id",
    "role_id",
    "ended_at",
    "holder_agent_id",
    "holder_user_id",
    "holder_contact_id",
)


def upgrade() -> None:
    op.create_table(
        "llc_role_assignments",
        # No server_default gen_random_uuid() — the ORM always supplies id
        # explicitly, mirroring llc_contacts / llc_secrets.
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        sa.Column("holder_type", sa.String(16), nullable=False),
        sa.Column("holder_agent_id", UUID(as_uuid=True), nullable=True),
        sa.Column("holder_user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("holder_contact_id", UUID(as_uuid=True), nullable=True),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # NULL means "still holds it" — the column the whole design turns on.
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
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
    for column in _INDEXED_COLUMNS:
        op.create_index(f"ix_llc_role_assignments_{column}", "llc_role_assignments", [column])

    # Partial unique index: one *open* tenure per holder per role. Ended tenures
    # are excluded so returning to a role you once held stays legal, which a
    # plain UNIQUE over the same columns would forbid.
    for kind in _HOLDER_KINDS:
        op.create_index(
            f"uq_llc_role_assignments_open_{kind}",
            "llc_role_assignments",
            ["role_id", f"holder_{kind}_id"],
            unique=True,
            postgresql_where=sa.text(f"ended_at IS NULL AND holder_{kind}_id IS NOT NULL"),
        )


def downgrade() -> None:
    for kind in _HOLDER_KINDS:
        op.drop_index(f"uq_llc_role_assignments_open_{kind}", table_name="llc_role_assignments")
    for column in _INDEXED_COLUMNS:
        op.drop_index(f"ix_llc_role_assignments_{column}", table_name="llc_role_assignments")
    op.drop_table("llc_role_assignments")
