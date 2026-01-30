# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add TLS columns to node_credentials table.

Adds TLS-specific fields for mTLS certificate storage.
Related to Issue #725.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate(db_path: str) -> None:
    """Add TLS columns to node_credentials table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if node_credentials table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='node_credentials'"
    )
    if not cursor.fetchone():
        logger.error("node_credentials table does not exist. Run add_node_credentials_table.py first.")
        conn.close()
        return

    # Get existing columns
    cursor.execute("PRAGMA table_info(node_credentials)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    # Add TLS columns if they don't exist
    tls_columns = [
        ("tls_common_name", "VARCHAR(255)"),
        ("tls_expires_at", "TIMESTAMP"),
        ("tls_fingerprint", "VARCHAR(64)"),
    ]

    for column_name, column_type in tls_columns:
        if column_name not in existing_columns:
            logger.info("Adding column: %s", column_name)
            cursor.execute(f"ALTER TABLE node_credentials ADD COLUMN {column_name} {column_type}")
        else:
            logger.info("Column %s already exists", column_name)

    # Create index on tls_expires_at for expiring certificate queries
    try:
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_credentials_tls_expires ON node_credentials(tls_expires_at)"
        )
        logger.info("Created index on tls_expires_at")
    except sqlite3.OperationalError as e:
        logger.debug("Index creation skipped: %s", e)

    conn.commit()
    conn.close()
    logger.info("TLS migration completed successfully!")


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
