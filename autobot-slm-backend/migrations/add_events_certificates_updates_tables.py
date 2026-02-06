# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add node_events, certificates, and update_info tables.

This adds tables for:
- node_events: Lifecycle event tracking
- certificates: PKI certificate management
- update_info: Update tracking and management

Updated for PostgreSQL (Issue #786).
"""

import logging
import sys

from migrations.utils import create_index_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add new tables for events, certificates, and updates (#786)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Create node_events table
    if not table_exists(cursor, "node_events"):
        logger.info("Creating node_events table...")
        cursor.execute(
            """
            CREATE TABLE node_events (
                id SERIAL PRIMARY KEY,
                event_id VARCHAR(64) UNIQUE NOT NULL,
                node_id VARCHAR(64) NOT NULL,
                event_type VARCHAR(50) NOT NULL,
                severity VARCHAR(20) DEFAULT 'info',
                message TEXT NOT NULL,
                details JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        create_index_if_not_exists(
            cursor, "idx_node_events_node_id", "node_events", "node_id"
        )
        create_index_if_not_exists(
            cursor, "idx_node_events_event_type", "node_events", "event_type"
        )
        create_index_if_not_exists(
            cursor, "idx_node_events_created_at", "node_events", "created_at"
        )
        logger.info("Created node_events table")
    else:
        logger.info("node_events table already exists")

    # Create certificates table
    if not table_exists(cursor, "certificates"):
        logger.info("Creating certificates table...")
        cursor.execute(
            """
            CREATE TABLE certificates (
                id SERIAL PRIMARY KEY,
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
        """
        )
        create_index_if_not_exists(
            cursor, "idx_certificates_node_id", "certificates", "node_id"
        )
        logger.info("Created certificates table")
    else:
        logger.info("certificates table already exists")

    # Create update_info table
    if not table_exists(cursor, "update_info"):
        logger.info("Creating update_info table...")
        cursor.execute(
            """
            CREATE TABLE update_info (
                id SERIAL PRIMARY KEY,
                update_id VARCHAR(64) UNIQUE NOT NULL,
                node_id VARCHAR(64),
                package_name VARCHAR(128) NOT NULL,
                current_version VARCHAR(32),
                available_version VARCHAR(32) NOT NULL,
                severity VARCHAR(16) DEFAULT 'low',
                description TEXT,
                is_applied BOOLEAN DEFAULT FALSE,
                applied_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        create_index_if_not_exists(
            cursor, "idx_update_info_node_id", "update_info", "node_id"
        )
        logger.info("Created update_info table")
    else:
        logger.info("update_info table already exists")

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
