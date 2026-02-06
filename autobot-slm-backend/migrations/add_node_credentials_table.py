# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add node_credentials table.

This adds encrypted credential storage for VNC, SSH, and other
service credentials. Related to Issue #725.
Updated for PostgreSQL (Issue #786).
"""

import logging
import sys

from migrations.utils import create_index_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add node_credentials table for encrypted credential storage (#786)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if not table_exists(cursor, "node_credentials"):
        logger.info("Creating node_credentials table...")
        cursor.execute(
            """
            CREATE TABLE node_credentials (
                id SERIAL PRIMARY KEY,
                credential_id VARCHAR(64) UNIQUE NOT NULL,
                node_id VARCHAR(64) NOT NULL,
                credential_type VARCHAR(32) NOT NULL,
                name VARCHAR(128),
                encrypted_password VARCHAR(512),
                encrypted_data TEXT,
                port INTEGER,
                vnc_type VARCHAR(32),
                display_number INTEGER,
                vnc_port INTEGER,
                websockify_enabled BOOLEAN DEFAULT TRUE,
                is_active BOOLEAN DEFAULT TRUE,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(node_id, credential_type, name)
            )
        """
        )

        # Create indexes
        create_index_if_not_exists(
            cursor, "idx_credentials_node_id", "node_credentials", "node_id"
        )
        create_index_if_not_exists(
            cursor, "idx_credentials_type", "node_credentials", "credential_type"
        )
        create_index_if_not_exists(
            cursor, "idx_credentials_active", "node_credentials", "is_active"
        )
        logger.info("Created node_credentials table with indexes")
    else:
        logger.info("node_credentials table already exists")

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
