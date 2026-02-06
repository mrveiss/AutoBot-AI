# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add replications table.

This adds the replications table for tracking stateful service
replication between nodes (e.g., Redis master-replica setups).
Updated for PostgreSQL (Issue #786).
"""

import logging
import sys

from migrations.utils import create_index_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add replications table (#786)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Create replications table
    if not table_exists(cursor, "replications"):
        logger.info("Creating replications table...")
        cursor.execute(
            """
            CREATE TABLE replications (
                id SERIAL PRIMARY KEY,
                replication_id VARCHAR(64) UNIQUE NOT NULL,
                source_node_id VARCHAR(64) NOT NULL,
                target_node_id VARCHAR(64) NOT NULL,
                service_type VARCHAR(32) DEFAULT 'redis',
                status VARCHAR(20) DEFAULT 'pending',
                sync_position VARCHAR(128),
                lag_bytes BIGINT DEFAULT 0,
                error TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        create_index_if_not_exists(
            cursor, "idx_replications_source_node", "replications", "source_node_id"
        )
        create_index_if_not_exists(
            cursor, "idx_replications_target_node", "replications", "target_node_id"
        )
        create_index_if_not_exists(
            cursor, "idx_replications_status", "replications", "status"
        )
        logger.info("Created replications table")
    else:
        logger.info("replications table already exists")

    # Create update_info table if it doesn't exist
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
