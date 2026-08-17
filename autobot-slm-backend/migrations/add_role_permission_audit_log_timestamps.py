# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add created_at/updated_at to role_permissions and audit_logs

Issue #12647 — the new canonical ``user_management`` declarative base bakes
``created_at``/``updated_at`` into ``Base`` unconditionally (matching the
backend's existing, already-migrated design), rather than making them
opt-in via ``TimestampMixin``. SLM's ``RolePermission`` and ``AuditLog``
models never opted into ``TimestampMixin`` and have no matching columns in
the live SLM database, so they gain ORM-mapped ``updated_at`` (and, for
``role_permissions``, ``created_at`` too) under the new base.

This mirrors the backend's own #10636 fix for the identical drift
("Base gives every model both created_at and updated_at, but ... some
tables [were] created without updated_at") — same idempotent,
guard-checked, forward-only, no-data-loss pattern, applied here because SLM
has its own separate database and never received that migration.

#14300: role_permissions and audit_logs are user_management tables, which
live in a *different* database than the rest of SLM's schema (the primary
SLM database the runner otherwise connects to via DATABASE_URL cannot see
them, by construction). TARGET_DB below tells the runner to resolve this
migration's db_url against the user_management database instead, via
``migrations.runner.get_user_management_db_url`` — the same config source
(``user_management.config.get_slm_db_config``) the SLM backend itself uses
to open that database at startup.

Run: python3 -m migrations.add_role_permission_audit_log_timestamps
"""

import logging
import sys

from migrations.runner import TARGET_DB_USER_MANAGEMENT
from migrations.utils import add_column_if_not_exists, get_connection

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

# Read by migrations.runner.run_migration to pick this migration's db_url
# (#14300) -- see the module docstring above.
TARGET_DB = TARGET_DB_USER_MANAGEMENT

_TIMESTAMP_COLUMN = "TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()"


def migrate(db_url: str) -> None:
    """Add missing created_at/updated_at columns (#12647, mirrors #10636)."""
    logger.info("Running migration: add_role_permission_audit_log_timestamps")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    add_column_if_not_exists(cursor, "role_permissions", "created_at", _TIMESTAMP_COLUMN)
    add_column_if_not_exists(cursor, "role_permissions", "updated_at", _TIMESTAMP_COLUMN)
    add_column_if_not_exists(cursor, "audit_logs", "updated_at", _TIMESTAMP_COLUMN)

    conn.commit()
    conn.close()

    logger.info("Migration complete: added created_at/updated_at to role_permissions, audit_logs")


if __name__ == "__main__":
    from migrations.runner import get_user_management_db_url

    # Standalone invocation bypasses migrations.runner.run_migration's
    # TARGET_DB resolution, so default to the same user_management database
    # that resolution would have picked (#14300) rather than DATABASE_URL,
    # which cannot reach role_permissions/audit_logs.
    db_url = sys.argv[1] if len(sys.argv) > 1 else get_user_management_db_url()
    migrate(db_url)
