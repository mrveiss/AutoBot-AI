# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add error resolution fields to node_events table

Issue #563: Error Monitoring Dashboard
Updated for PostgreSQL (Issue #786).

Adds the following columns to node_events:
- resolved: Boolean flag indicating if error has been resolved
- resolved_at: Timestamp when error was resolved
- resolved_by: Username who resolved the error
"""

import logging
import sys

from migrations.utils import add_column_if_not_exists, get_connection, table_exists

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Run the migration (#786)."""
    logger.info("Running error resolution fields migration")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Check if table exists
    if not table_exists(cursor, "node_events"):
        logger.info("Table node_events does not exist - skipping migration")
        conn.close()
        return

    # Add resolved column
    add_column_if_not_exists(cursor, "node_events", "resolved", "BOOLEAN DEFAULT FALSE")

    # Add resolved_at column
    add_column_if_not_exists(cursor, "node_events", "resolved_at", "TIMESTAMP")

    # Add resolved_by column
    add_column_if_not_exists(cursor, "node_events", "resolved_by", "VARCHAR(255)")

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully - error resolution fields added")


def main():
    """Entry point for running migration directly."""
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)


if __name__ == "__main__":
    main()
