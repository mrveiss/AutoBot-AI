# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add external_agents table (Issue #963).

Stores A2A-compliant external agent registrations with card cache,
trust flags, and optional encrypted API key.
"""

import logging
import sys

from migrations.utils import create_index_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Create external_agents table for the External Agent Registry (#963)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if not table_exists(cursor, "external_agents"):
        logger.info("Creating external_agents table...")
        cursor.execute(
            """
            CREATE TABLE external_agents (
                id          SERIAL PRIMARY KEY,
                name        VARCHAR(100) NOT NULL,
                base_url    VARCHAR(512) NOT NULL UNIQUE,
                description TEXT,
                tags        JSONB DEFAULT '[]',
                enabled     BOOLEAN DEFAULT TRUE,

                card_data       JSONB,
                card_fetched_at TIMESTAMP,
                card_error      TEXT,

                verified    BOOLEAN DEFAULT FALSE,
                ssl_verify  BOOLEAN DEFAULT TRUE,
                api_key     TEXT,

                created_by  VARCHAR(64),
                created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        create_index_if_not_exists(
            cursor,
            "idx_external_agents_base_url",
            "external_agents",
            "base_url",
        )
        create_index_if_not_exists(
            cursor,
            "idx_external_agents_enabled_verified",
            "external_agents",
            "enabled, verified",
        )
        logger.info("Created external_agents table with indexes")
    else:
        logger.info("external_agents table already exists")

    conn.commit()
    conn.close()
    logger.info("Migration add_external_agents completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
