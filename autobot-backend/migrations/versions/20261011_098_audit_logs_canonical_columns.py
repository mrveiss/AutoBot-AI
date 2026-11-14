# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``audit_logs`` becomes the audit trail's system of record (#17225 D1).

The owner chose to extend the existing ``audit_logs`` table rather than add a
second Postgres audit table. Its original columns could not hold what the
canonical ``AuditEvent`` records: an actor that is not a user row (an agent,
``system``), a resource that is not a UUID (a path, a fact id), the session,
and the category that selects the retention period.

``NO DATA LOSS``: four additive columns and two indexes. ``actor``,
``session_id`` and ``resource_ref`` are nullable with no default. ``category``
is NOT NULL with ``server_default 'security'``, which PostgreSQL 11+ applies
as a catalogue default without rewriting a row; every existing row is a
security record (logins, permission denials, org/team/user changes), so the
default is also the true value. Nothing existing is altered or dropped.

Source of truth: ``autobot_shared/user_management/models/audit.py :: AuditLog``.
The SLM's ``slm_users`` database maps the same model and gets the same columns
from ``autobot-slm-backend/migrations/add_audit_logs_canonical_columns.py``.

Idempotent: every step is guarded by ``has_column`` / ``has_index``.

The two indexes are built ``CONCURRENTLY``, outside the migration transaction,
so ``audit_logs`` keeps taking writes while they build. A concurrent build that
fails leaves an INVALID index behind; :func:`_ensure_index` drops that one
(an index, never row data) and builds it again.

**Forward-only.** ``downgrade()`` is a no-op: see its docstring.

Revision ID: 20261011_098
Revises: 20260928_097
Create Date: 2026-10-11
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column, has_index

revision: str = "20261011_098"
down_revision: Union[str, None] = "20260928_097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = (("ix_audit_logs_category", ("category",)), ("idx_audit_actor_created", ("actor", "created_at")))


def upgrade() -> None:
    """Add the four canonical columns and their indexes, skipping any that exist.

    Literal ``op.add_column("audit_logs", sa.Column("<name>", ...))`` calls, so
    the probe ladder can observe this revision (see 20260926_096).
    """
    if not has_column("audit_logs", "category"):
        op.add_column(
            "audit_logs",
            sa.Column("category", sa.String(32), nullable=False, server_default="security"),
        )
    if not has_column("audit_logs", "actor"):
        op.add_column("audit_logs", sa.Column("actor", sa.String(255), nullable=True))
    if not has_column("audit_logs", "session_id"):
        op.add_column("audit_logs", sa.Column("session_id", sa.String(255), nullable=True))
    if not has_column("audit_logs", "resource_ref"):
        op.add_column("audit_logs", sa.Column("resource_ref", sa.String(512), nullable=True))
    # CREATE INDEX CONCURRENTLY cannot run inside a transaction block.
    with op.get_context().autocommit_block():
        for name, columns in _INDEXES:
            _ensure_index(name, columns)


def _index_is_invalid(name: str) -> bool:
    """True when a failed concurrent build left *name* behind, unusable.

    ``pg_index`` exists only on PostgreSQL; on any other dialect there is no
    such thing as an invalid index, so the answer is False.
    """
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    row = bind.execute(
        sa.text("SELECT NOT i.indisvalid FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid WHERE c.relname = :n"),
        {"n": name},
    )
    return bool(row.scalar())


def _ensure_index(name: str, columns: tuple[str, ...]) -> None:
    """Build *name* concurrently unless a valid copy already exists."""
    if has_index("audit_logs", name):
        if not _index_is_invalid(name):
            return
        op.drop_index(name, table_name="audit_logs", postgresql_concurrently=True)
    op.create_index(name, "audit_logs", list(columns), postgresql_concurrently=True)


def downgrade() -> None:
    """No-op, on purpose: rolling back must not delete audit records (#17038).

    Dropping ``category``, ``actor``, ``session_id`` or ``resource_ref`` would
    destroy what every audit row written since the upgrade recorded in them --
    a deletion path in the audit store, which only a human may approve. The
    columns are additive (nullable, or a server default) and the indexes are
    read aids, so code from before this revision runs unchanged beside them.
    """
