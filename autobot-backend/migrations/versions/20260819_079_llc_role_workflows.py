# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Add llc_role_workflows — workflows carried by a role (#14221 step 5).

The attachment hangs off the role, so replacing the holder moves nothing: the
next occupant of a role inherits its workflows because they were never the
previous occupant's.

``workflow_id`` is ``VARCHAR(255)`` to match ``workflows.workflow_id``, which is
a string primary key rather than a UUID.

Plain ``op.create_table`` — the tolerant ``IF NOT EXISTS`` form belongs to the
drift reconciliations that re-add columns to tables already changed
out-of-band, not to a table born in its own migration.

Revision ID: 20260819_079
Revises: 20260818_078
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "20260819_079"
down_revision: Union[str, None] = "20260818_078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXED_COLUMNS = ("company_id", "role_id", "workflow_id")


def upgrade() -> None:
    op.create_table(
        "llc_role_workflows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=False),
        # VARCHAR, not UUID — workflows.workflow_id is a string key.
        sa.Column("workflow_id", sa.String(255), nullable=False),
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
        sa.UniqueConstraint("role_id", "workflow_id", name="uq_llc_role_workflows_role_workflow"),
    )
    for column in _INDEXED_COLUMNS:
        op.create_index(f"ix_llc_role_workflows_{column}", "llc_role_workflows", [column])


def downgrade() -> None:
    for column in _INDEXED_COLUMNS:
        op.drop_index(f"ix_llc_role_workflows_{column}", table_name="llc_role_workflows")
    op.drop_table("llc_role_workflows")
