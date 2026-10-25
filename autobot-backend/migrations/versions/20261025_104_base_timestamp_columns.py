# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add the remaining Base timestamp columns no migration created (#17996).

Revision ID: 20261025_104
Revises: 20261024_103
Create Date: 2026-10-25 00:00:01.000000

``Base`` gives every mapped model ``created_at`` and ``updated_at``. Revision 103 added them to
``llc_workspace_leases``; ``test_orm_columns_match_migrations_17996`` then found the same gap
on seven more tables, each missing one of the two. On a migrated database every ``SELECT`` of
those models fails with ``column ... does not exist`` -- ``heartbeat_run_events`` among them,
which every heartbeat run writes.

``NO DATA LOSS``: additive only. Each column is added with the type, timezone, nullability and
``now()`` server default ``Base`` declares, so existing rows are filled with the time of the
migration and nothing is rewritten or deleted. Idempotent (``has_table``/``has_column``) for a
database built by ``create_all``, which already has them. ``downgrade`` is a no-op for the same
reason as revision 103: the columns are ORM-owned and may predate this revision.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from migrations.guards import has_column, has_table

revision: str = "20261025_104"
down_revision: Union[str, None] = "20261024_103"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def upgrade() -> None:
    # Literal add_column calls (not a loop) so the baseline probe ladder can observe this
    # revision; has_table/has_column keep each one idempotent.
    if has_table("completion_feedback") and not has_column("completion_feedback", "created_at"):
        op.add_column("completion_feedback", _timestamp("created_at"))
    if has_table("heartbeat_run_events") and not has_column("heartbeat_run_events", "created_at"):
        op.add_column("heartbeat_run_events", _timestamp("created_at"))
    if has_table("role_permissions") and not has_column("role_permissions", "created_at"):
        op.add_column("role_permissions", _timestamp("created_at"))
    if has_table("workflow_audit_log") and not has_column("workflow_audit_log", "created_at"):
        op.add_column("workflow_audit_log", _timestamp("created_at"))
    if has_table("llc_role_skills") and not has_column("llc_role_skills", "updated_at"):
        op.add_column("llc_role_skills", _timestamp("updated_at"))
    if has_table("llc_workflow_nodes") and not has_column("llc_workflow_nodes", "updated_at"):
        op.add_column("llc_workflow_nodes", _timestamp("updated_at"))
    if has_table("llc_workflow_transitions") and not has_column("llc_workflow_transitions", "updated_at"):
        op.add_column("llc_workflow_transitions", _timestamp("updated_at"))


def downgrade() -> None:
    # Deliberate no-op: the columns are ORM-owned (Base declares them on every model), so a drop
    # re-breaks every read of these models, and upgrade() skips them on a create_all database, so
    # a drop would also destroy real timestamps this revision never created (#17996).
    pass
