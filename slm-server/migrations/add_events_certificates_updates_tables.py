# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add node_events, certificates, and updates tables.

This adds tables for:
- node_events: Lifecycle event tracking
- certificates: PKI certificate management
- updates: Update tracking and management
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
        "SELECT name FROM sqlite_master WHERE type='table' AND name='updates'"
    )
    updates_exists = cursor.fetchone() is not None

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

    # Create updates table
    if not updates_exists:
        logger.info("Creating updates table...")
        cursor.execute("""
            CREATE TABLE updates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                update_id VARCHAR(64) UNIQUE NOT NULL,
                node_id VARCHAR(64),
                package_name VARCHAR(255) NOT NULL,
                current_version VARCHAR(64),
                available_version VARCHAR(64) NOT NULL,
                update_type VARCHAR(20) DEFAULT 'package',
                severity VARCHAR(20) DEFAULT 'normal',
                description TEXT,
                is_applied BOOLEAN DEFAULT 0,
                applied_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX idx_updates_node_id ON updates(node_id)")
        logger.info("Created updates table")
    else:
        logger.info("updates table already exists")

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
