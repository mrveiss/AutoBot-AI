# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add services table.

This adds the services table for tracking systemd services
discovered on each managed node. Related to Issue #728.
"""

import logging
import sqlite3
import sys

logger = logging.getLogger(__name__)


def migrate(db_path: str) -> None:
    """Add services table for tracking systemd services per node."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='services'"
    )
    services_exists = cursor.fetchone() is not None

    if not services_exists:
        logger.info("Creating services table...")
        cursor.execute("""
            CREATE TABLE services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                node_id VARCHAR(64) NOT NULL,
                service_name VARCHAR(128) NOT NULL,
                status VARCHAR(20) DEFAULT 'unknown',
                enabled BOOLEAN DEFAULT 0,
                description VARCHAR(512),
                active_state VARCHAR(32),
                sub_state VARCHAR(32),
                main_pid INTEGER,
                memory_bytes INTEGER,
                last_checked TIMESTAMP,
                extra_data JSON DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(node_id, service_name)
            )
        """)
        cursor.execute(
            "CREATE INDEX idx_services_node_id ON services(node_id)"
        )
        cursor.execute(
            "CREATE INDEX idx_services_status ON services(status)"
        )
        cursor.execute(
            "CREATE INDEX idx_services_name ON services(service_name)"
        )
        logger.info("Created services table with indexes")
    else:
        logger.info("services table already exists")

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
