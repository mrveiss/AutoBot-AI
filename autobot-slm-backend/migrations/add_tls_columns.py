# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add TLS columns to node_credentials table.

Adds TLS-specific fields for mTLS certificate storage.
Related to Issue #725.
Updated for PostgreSQL (Issue #786).
"""

import logging
import sys

from migrations.utils import (
    add_column_if_not_exists,
    create_index_if_not_exists,
    get_connection,
    table_exists,
)

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add TLS columns to node_credentials table (#786)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Check if node_credentials table exists
    if not table_exists(cursor, "node_credentials"):
        logger.error(
            "node_credentials table does not exist. "
            "Run add_node_credentials_table.py first."
        )
        conn.close()
        return

    # Add TLS columns if they don't exist
    tls_columns = [
        ("tls_common_name", "VARCHAR(255)"),
        ("tls_expires_at", "TIMESTAMP"),
        ("tls_fingerprint", "VARCHAR(64)"),
    ]

    for column_name, column_type in tls_columns:
        add_column_if_not_exists(cursor, "node_credentials", column_name, column_type)

    # Create index on tls_expires_at for expiring certificate queries
    create_index_if_not_exists(
        cursor, "idx_credentials_tls_expires", "node_credentials", "tls_expires_at"
    )

    conn.commit()
    conn.close()
    logger.info("TLS migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
