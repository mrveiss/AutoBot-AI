# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add node_events, certificates, and update_info tables.

This adds tables for:
- node_events: Lifecycle event tracking
- certificates: PKI certificate management
- update_info: Update tracking and management
"""

import logging
import sqlite3
import sys

logger = logging.getLogger(__name__)


def migrate(db_path: str) -> None:
    """Add new tables for events, certificates, and updates."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if tables exist
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='node_events'"
    )
    node_events_exists = cursor.fetchone() is not None

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='certificates'"
    )
    certificates_exists = cursor.fetchone() is not None

    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='update_info'"
    )
    update_info_exists = cursor.fetchone() is not None

    # Create node_events table
    if not node_events_exists:
        logger.info("Creating node_events table...")
        cursor.execute("""
            CREATE TABLE node_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id VARCHAR(64) UNIQUE NOT NULL,
                node_id VARCHAR(64) NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                severity VARCHAR(20) DEFAULT 'info',
                message TEXT NOT NULL,
                details JSON DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX idx_node_events_node_id ON node_events(node_id)")
        cursor.execute(
            "CREATE INDEX idx_node_events_event_type ON node_events(event_type)"
        )
        cursor.execute(
            "CREATE INDEX idx_node_events_created_at ON node_events(created_at)"
        )
        logger.info("Created node_events table")
    else:
        logger.info("node_events table already exists")

    # Create certificates table
    if not certificates_exists:
        logger.info("Creating certificates table...")
        cursor.execute("""
            CREATE TABLE certificates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                certificate_id VARCHAR(64) UNIQUE NOT NULL,
                node_id VARCHAR(64) NOT NULL,
                fingerprint VARCHAR(128) NOT NULL,
                issued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                public_key TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX idx_certificates_node_id ON certificates(node_id)"
        )
        logger.info("Created certificates table")
    else:
        logger.info("certificates table already exists")

    # Create update_info table
    if not update_info_exists:
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
