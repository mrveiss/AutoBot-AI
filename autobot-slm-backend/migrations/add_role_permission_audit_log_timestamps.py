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

Run: python3 -m migrations.add_role_permission_audit_log_timestamps
"""

import logging
import sys

from migrations.utils import add_column_if_not_exists, get_connection

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

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
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)
