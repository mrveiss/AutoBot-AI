# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add code_version and code_status columns to nodes table.

Adds fields for tracking deployed code version on each node.
Related to Issue #741 (SLM Code Distribution).
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
    """Add code_version and code_status columns to nodes table (#786)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Check if nodes table exists
    if not table_exists(cursor, "nodes"):
        logger.error("nodes table does not exist. Database may not be initialized.")
        conn.close()
        return

    # Add code version columns if they don't exist
    code_columns = [
        ("code_version", "VARCHAR(64)"),  # Git commit hash
        (
            "code_status",
            "VARCHAR(20) DEFAULT 'unknown'",
        ),  # up_to_date, outdated, unknown
    ]

    for column_name, column_type in code_columns:
        add_column_if_not_exists(cursor, "nodes", column_name, column_type)

    # Create index on code_status for filtering outdated nodes
    create_index_if_not_exists(cursor, "idx_nodes_code_status", "nodes", "code_status")

    conn.commit()
    conn.close()
    logger.info("Code version migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
