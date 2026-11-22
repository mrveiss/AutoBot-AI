# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``audit_logs`` gets a tamper-evident hash chain (#17219).

Six nullable columns (``chain_seq``, ``prev_hash``, ``row_hash``, ``row_mac``, ``key_id``,
``org_ref``), the ``audit_chain_anchors`` table, and a partial UNIQUE index on ``chain_seq``
(the backstop: two writers can never hold one sequence number).

``NO DATA REWRITE``: no existing row is read or changed. The columns have no default, so a row
from before the chain keeps NULLs and is *pre-chain*. The genesis anchor, which records how many
such rows there are, is written by the first chained insert -- not by this migration -- so rows
that old code writes between the migration and the restart are counted too.

The index is built ``CONCURRENTLY``, outside the migration transaction, so ``audit_logs`` keeps
taking writes while it builds; an INVALID leftover of a failed build is dropped (an index, never
row data) and built again. The SLM's ``slm_users`` database maps the same model and gets the same
change from ``autobot-slm-backend/migrations/add_audit_logs_chain_columns.py``.

**Forward-only.** ``downgrade()`` is a no-op: see its docstring.

Revision ID: 20261122_122
Revises: 20261122_121
Create Date: 2026-11-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column, has_index, has_table

revision: str = "20261122_122"
down_revision: Union[str, None] = "20261122_121"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_audit_logs_chain_seq"


def upgrade() -> None:
    """Add the chain columns, the anchors table and the index, skipping any that exist.

    Literal ``op.add_column("audit_logs", ...)`` calls, so the probe ladder can observe this revision.
    """
    if not has_column("audit_logs", "chain_seq"):
        op.add_column("audit_logs", sa.Column("chain_seq", sa.BigInteger(), nullable=True))
    if not has_column("audit_logs", "prev_hash"):
        op.add_column("audit_logs", sa.Column("prev_hash", sa.String(64), nullable=True))
    if not has_column("audit_logs", "row_hash"):
        op.add_column("audit_logs", sa.Column("row_hash", sa.String(64), nullable=True))
    if not has_column("audit_logs", "row_mac"):
        op.add_column("audit_logs", sa.Column("row_mac", sa.String(64), nullable=True))
    if not has_column("audit_logs", "key_id"):
        op.add_column("audit_logs", sa.Column("key_id", sa.String(32), nullable=True))
    if not has_column("audit_logs", "org_ref"):
        op.add_column("audit_logs", sa.Column("org_ref", sa.String(64), nullable=True))
    _create_anchors()
    with op.get_context().autocommit_block():  # CREATE INDEX CONCURRENTLY cannot run in a transaction
        _ensure_index()


def _create_anchors() -> None:
    if has_table("audit_chain_anchors"):
        return
    op.create_table(
        "audit_chain_anchors",
        sa.Column("kind", sa.String(16), primary_key=True),
        sa.Column("seq", sa.BigInteger(), primary_key=True, autoincrement=False),
        sa.Column("hash", sa.String(64), nullable=False),
        sa.Column("mac", sa.String(64), nullable=False),
        sa.Column("key_id", sa.String(32), nullable=False),
        sa.Column("pre_chain_count", sa.BigInteger(), nullable=False),
        sa.Column("pre_chain_max_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def _index_is_invalid(name: str) -> bool:
    """True when a failed concurrent build left *name* behind, unusable."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    row = bind.execute(
        sa.text("SELECT NOT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = :n"),
        {"n": _INDEX},
    )
    return bool(row.scalar())


def _ensure_index() -> None:
    """Build the partial unique index concurrently unless a valid copy already exists."""
    if has_index("audit_logs", _INDEX):
        if not _index_is_invalid(_INDEX):
            return
        op.drop_index(_INDEX, table_name="audit_logs", postgresql_concurrently=True)
    op.create_index(
        _INDEX,
        "audit_logs",
        ["chain_seq"],
        unique=True,
        postgresql_where=sa.text("chain_seq IS NOT NULL"),
        postgresql_concurrently=True,
    )


def downgrade() -> None:
    """No-op, on purpose: rolling back must not delete audit records (#17038).

    Dropping the chain columns or ``audit_chain_anchors`` would destroy the evidence that makes the
    rows written since the upgrade verifiable. The columns are nullable and the index is a read aid,
    so code from before this revision runs unchanged beside them.
    """
