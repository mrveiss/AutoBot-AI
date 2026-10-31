# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Attachment content hash and file-deletion outbox (#19756).

Revision ID: 20261031_107
Revises: 20261031_106
Create Date: 2026-10-31 00:00:01.000000

``NO DATA LOSS``: one nullable column and one new table; no row is rewritten and nothing is
backfilled (a backfill would read every stored file). Rows uploaded earlier keep a NULL
``sha256``. Guarded for a database that ``create_all`` already built.

Downgrade drops the ``sha256`` column (the hashes are derived from the stored files, so they
can be recomputed) and the outbox table, and refuses to drop the table while it holds entries.

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

from migrations.guards import has_column, has_table

revision: str = "20261031_107"
down_revision: Union[str, None] = "20261031_106"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLE = "llc_attachment_file_deletions"


def upgrade() -> None:
    if not has_column("llc_work_item_attachments", "sha256"):
        op.add_column("llc_work_item_attachments", sa.Column("sha256", sa.String(64), nullable=True))
    if has_table(_TABLE):
        return
    op.create_table(
        "llc_attachment_file_deletions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("attachment_id", UUID(as_uuid=True), nullable=False),
        sa.Column("company_id", UUID(as_uuid=True), nullable=False),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("root_id", sa.Text, nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stuck_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(f"ix_{_TABLE}_attachment_id", _TABLE, ["attachment_id"])
    op.create_index(f"ix_{_TABLE}_root_id", _TABLE, ["root_id"])


def downgrade() -> None:
    # A pending outbox row is an owed file removal; dropping the table forgets it. Refuse
    # rather than lose it silently: drain the outbox before downgrading.
    if has_table(_TABLE):
        bind = op.get_bind()
        # EXCLUSIVE blocks concurrent inserts until this transaction ends, so no outbox entry can
        # commit between the count and the DROP and be discarded with the table. A blocked
        # delete waits, then fails with the table gone and keeps its attachment row.
        bind.execute(sa.text("LOCK TABLE llc_attachment_file_deletions IN EXCLUSIVE MODE"))
        pending = bind.execute(sa.text("SELECT count(*) FROM llc_attachment_file_deletions")).scalar()
        if pending:
            raise NotImplementedError(
                f"{pending} attachment file removal(s) still pending in {_TABLE}; drain them first"
            )
        op.drop_index(f"ix_{_TABLE}_root_id", table_name=_TABLE)
        op.drop_index(f"ix_{_TABLE}_attachment_id", table_name=_TABLE)
        op.drop_table(_TABLE)
    if has_column("llc_work_item_attachments", "sha256"):
        op.drop_column("llc_work_item_attachments", "sha256")
