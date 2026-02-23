# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2026 mrveiss
# Author: mrveiss
"""
Migration: Add required, degraded_without, ansible_playbook columns to roles table

Issue #1129 Phase 2 — role metadata fields for fleet health classification
and Ansible playbook migration.

Run: python3 -m migrations.add_role_metadata_fields
"""

import logging
import sys

from migrations.utils import add_column_if_not_exists, get_connection

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add required, degraded_without, ansible_playbook to roles table (#1129)."""
    logger.info("Running migration: add_role_metadata_fields")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    add_column_if_not_exists(cursor, "roles", "required", "BOOLEAN DEFAULT FALSE")
    add_column_if_not_exists(cursor, "roles", "degraded_without", "JSON DEFAULT '[]'")
    add_column_if_not_exists(cursor, "roles", "ansible_playbook", "VARCHAR(255)")

    conn.commit()
    conn.close()

    logger.info(
        "Migration complete: added required, degraded_without, ansible_playbook"
    )


if __name__ == "__main__":
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)
