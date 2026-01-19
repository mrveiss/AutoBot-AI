# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add replications table.

This adds the replications table for tracking stateful service
replication between nodes (e.g., Redis master-replica setups).
"""

import logging
import sqlite3
import sys

logger = logging.getLogger(__name__)


def migrate(db_path: str) -> None:
    """Add replications table."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='replications'"
    )
    replications_exists = cursor.fetchone() is not None

    # Create replications table
    if not replications_exists:
        logger.info("Creating replications table...")
        cursor.execute("""
            CREATE TABLE replications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                replication_id VARCHAR(64) UNIQUE NOT NULL,
                source_node_id VARCHAR(64) NOT NULL,
                target_node_id VARCHAR(64) NOT NULL,
                service_type VARCHAR(32) DEFAULT 'redis',
                status VARCHAR(20) DEFAULT 'pending',
                sync_position VARCHAR(128),
                lag_bytes INTEGER DEFAULT 0,
                error TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX idx_replications_source_node ON replications(source_node_id)"
        )
        cursor.execute(
            "CREATE INDEX idx_replications_target_node ON replications(target_node_id)"
        )
        cursor.execute(
            "CREATE INDEX idx_replications_status ON replications(status)"
        )
        logger.info("Created replications table")
    else:
        logger.info("replications table already exists")

    # Also check if update_info table exists (correct name from model)
    # If 'updates' exists but 'update_info' doesn't, rename it
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='update_info'"
    )
    update_info_exists = cursor.fetchone() is not None

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='updates'"
    )
    updates_exists = cursor.fetchone() is not None

    if updates_exists and not update_info_exists:
        logger.info("Renaming 'updates' table to 'update_info' to match model...")
        cursor.execute("ALTER TABLE updates RENAME TO update_info")
        logger.info("Renamed table successfully")
    elif not update_info_exists:
        logger.info("Creating update_info table...")
        cursor.execute("""
            CREATE TABLE update_info (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id VARCHAR(64) UNIQUE NOT NULL,
                node_id VARCHAR(64),
                package_name VARCHAR(128) NOT NULL,
                current_version VARCHAR(32),
                available_version VARCHAR(32) NOT NULL,
                severity VARCHAR(16) DEFAULT 'low',
                description TEXT,
                is_applied BOOLEAN DEFAULT 0,
                applied_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX idx_update_info_node_id ON update_info(node_id)")
        logger.info("Created update_info table")
    else:
        logger.info("update_info table already exists")

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
