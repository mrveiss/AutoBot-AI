# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Add missing updated_at columns (Base timestamp drift) (#10636).

``user_management.models.base.Base`` gives every model both ``created_at`` and
``updated_at``, but the initial migration (20251224_001) and a few later ones
created some tables without ``updated_at``. Because the ORM still emits
``RETURNING ... updated_at`` for those mapped classes, any write fails with
``column "updated_at" does not exist`` — most visibly when seeding the default
platform admin (which writes ``audit_logs``), so full-user-management logins
had no admin account to authenticate against.

This reconciles the drift idempotently: add ``updated_at`` to every affected
table if it is missing. Safe on fresh, partially-migrated, or already-patched
databases (``IF NOT EXISTS`` + ``has_table`` guard).

Revision ID: 20260629_063
Revises: 20260623_062
Create Date: 2026-06-29
"""

from typing import Sequence, Union

from alembic import op

from migrations.guards import has_table

# revision identifiers, used by Alembic.
revision: str = "20260629_063"
down_revision: Union[str, None] = "20260623_062"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Tables observed missing ``updated_at`` despite inheriting Base's timestamp
# columns (or being written through the audited service layer). Listed
# explicitly so the reconciliation is reviewable and deterministic.
_TABLES_MISSING_UPDATED_AT: tuple[str, ...] = (
    "agent_connections",
    "agent_task_history",
    "audit_logs",
    "chat_shared_links",
    "completion_feedback",
    "desktop_mobile_devices",
    "heartbeat_run_events",
    "llc_activity_log",
    "llc_agent_api_keys",
    "llc_heartbeat_runs",
    "llc_routine_runs",
    "llc_run_replay_logs",
    "mesh_edges",
    "mesh_evolution_log",
    "mesh_nodes",
    "mesh_nodes_archive",
    "push_subscriptions",
    "role_permissions",
    "task_approval_links",
    "user_voice_bundle",
    "workflow_audit_log",
)


def upgrade() -> None:
    for table in _TABLES_MISSING_UPDATED_AT:
        if has_table(table):
            op.execute(
                f'ALTER TABLE "{table}" '
                "ADD COLUMN IF NOT EXISTS updated_at "
                "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT now()"
            )


def downgrade() -> None:
    # Forward-only drift reconciliation: dropping ``updated_at`` again would
    # re-break the ORM write paths these columns fix, so downgrade is a no-op.
    pass
