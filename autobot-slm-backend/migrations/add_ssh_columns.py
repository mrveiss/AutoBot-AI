# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add SSH credential columns to nodes table.

This adds:
- ssh_user (VARCHAR(64), default 'autobot')
- ssh_port (INTEGER, default 22)
- ssh_password_encrypted (VARCHAR(512), nullable)
- auth_method (VARCHAR(20), default 'password')

Updated for PostgreSQL (Issue #786).
"""

import logging
import sys

from migrations.utils import add_column_if_not_exists, get_connection

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add SSH columns to nodes table if they don't exist (#786)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Define new columns with their SQL definitions
    new_columns = [
        ("ssh_user", "VARCHAR(64) DEFAULT 'autobot'"),
        ("ssh_port", "INTEGER DEFAULT 22"),
        ("ssh_password_encrypted", "VARCHAR(512)"),
        ("auth_method", "VARCHAR(20) DEFAULT 'password'"),
    ]

    # Add missing columns
    for col_name, col_def in new_columns:
        add_column_if_not_exists(cursor, "nodes", col_name, col_def)

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
