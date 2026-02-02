# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add code_version and code_status columns to nodes table.

Adds fields for tracking deployed code version on each node.
Related to Issue #741 (SLM Code Distribution).
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate(db_path: str) -> None:
    """Add code_version and code_status columns to nodes table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if nodes table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='nodes'")
    if not cursor.fetchone():
        logger.error("nodes table does not exist. Database may not be initialized.")
        conn.close()
        return

    # Get existing columns
    cursor.execute("PRAGMA table_info(nodes)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Add code version columns if they don't exist
    code_columns = [
        ("code_version", "VARCHAR(64)"),  # Git commit hash
        (
            "code_status",
            "VARCHAR(20) DEFAULT 'unknown'",
        ),  # up_to_date, outdated, unknown
    ]

    for column_name, column_type in code_columns:
        if column_name not in existing_columns:
            logger.info("Adding column: %s", column_name)
            cursor.execute(f"ALTER TABLE nodes ADD COLUMN {column_name} {column_type}")
        else:
            logger.info("Column %s already exists", column_name)

    # Create index on code_status for filtering outdated nodes
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_nodes_code_status ON nodes(code_status)"
        )
        logger.info("Created index on code_status")
    except sqlite3.OperationalError as e:
        logger.debug("Index creation skipped: %s", e)

    conn.commit()
    conn.close()
    logger.info("Code version migration completed successfully!")


def get_default_db_path() -> str:
    """Get default database path from config or environment."""
    db_path = os.getenv("SLM_DATABASE_PATH")
    if db_path:
        return db_path

    base_dir = Path(__file__).parent.parent
    return str(base_dir / "data" / "slm.db")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        db_path = get_default_db_path()
    else:
        db_path = sys.argv[1]

    logger.info("Migrating database: %s", db_path)
    migrate(db_path)
