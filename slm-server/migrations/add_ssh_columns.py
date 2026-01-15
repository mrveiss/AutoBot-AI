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
"""

import logging
import sqlite3
import sys

logger = logging.getLogger(__name__)


def migrate(db_path: str) -> None:
    """Add SSH columns to nodes table if they don't exist."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get existing columns
    cursor.execute("PRAGMA table_info(nodes)")
    existing_columns = {row[1] for row in cursor.fetchall()}
    logger.info("Existing columns: %s", existing_columns)

    # Define new columns with their SQL definitions
    new_columns = [
        ("ssh_user", "VARCHAR(64) DEFAULT 'autobot'"),
        ("ssh_port", "INTEGER DEFAULT 22"),
        ("ssh_password_encrypted", "VARCHAR(512)"),
        ("auth_method", "VARCHAR(20) DEFAULT 'password'"),
    ]

    # Add missing columns
    for col_name, col_def in new_columns:
        if col_name not in existing_columns:
            sql = f"ALTER TABLE nodes ADD COLUMN {col_name} {col_def}"
            logger.info("Adding column: %s", col_name)
            cursor.execute(sql)
        else:
            logger.info("Column already exists: %s", col_name)

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        db_path = "/home/autobot/AutoBot/slm-server/slm.db"
    else:
        db_path = sys.argv[1]

    logger.info("Migrating database: %s", db_path)
    migrate(db_path)
