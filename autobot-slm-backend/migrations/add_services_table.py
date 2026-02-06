# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add services table.

This adds the services table for tracking systemd services
discovered on each managed node. Related to Issue #728.
Updated for PostgreSQL (Issue #786).
"""

import logging
import sys

from migrations.utils import create_index_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add services table for tracking systemd services per node (#786)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if not table_exists(cursor, "services"):
        logger.info("Creating services table...")
        cursor.execute(
            """
            CREATE TABLE services (
                id SERIAL PRIMARY KEY,
                node_id VARCHAR(64) NOT NULL,
                service_name VARCHAR(128) NOT NULL,
                status VARCHAR(20) DEFAULT 'unknown',
                enabled BOOLEAN DEFAULT FALSE,
                description VARCHAR(512),
                active_state VARCHAR(32),
                sub_state VARCHAR(32),
                main_pid INTEGER,
                memory_bytes BIGINT,
                last_checked TIMESTAMP,
                extra_data JSONB DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(node_id, service_name)
            )
        """
        )
        create_index_if_not_exists(
            cursor, "idx_services_node_id", "services", "node_id"
        )
        create_index_if_not_exists(cursor, "idx_services_status", "services", "status")
        create_index_if_not_exists(
            cursor, "idx_services_name", "services", "service_name"
        )
        logger.info("Created services table with indexes")
    else:
        logger.info("services table already exists")

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
