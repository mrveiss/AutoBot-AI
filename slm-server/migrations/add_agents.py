# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add agents table for per-agent LLM configuration.

Issue #760 Phase 2
Updated for PostgreSQL (Issue #786).
"""

import logging
import sys

from migrations.utils import create_index_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Run the agents table migration (#786)."""
    logger.info("Running agents migration...")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        if table_exists(cursor, "agents"):
            logger.info("agents table already exists, skipping creation")
            conn.close()
            return

        # Create agents table
        cursor.execute(
            """
            CREATE TABLE agents (
                id SERIAL PRIMARY KEY,
                agent_id VARCHAR(64) UNIQUE NOT NULL,
                name VARCHAR(128) NOT NULL,
                description TEXT,
                llm_provider VARCHAR(32) NOT NULL,
                llm_endpoint VARCHAR(256),
                llm_model VARCHAR(64) NOT NULL,
                llm_api_key_encrypted TEXT,
                llm_timeout INTEGER DEFAULT 30,
                llm_temperature REAL DEFAULT 0.7,
                llm_max_tokens INTEGER,
                is_default BOOLEAN DEFAULT FALSE,
                is_active BOOLEAN DEFAULT TRUE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created agents table")

        # Create indexes
        create_index_if_not_exists(cursor, "idx_agents_agent_id", "agents", "agent_id")
        create_index_if_not_exists(
            cursor, "idx_agents_is_default", "agents", "is_default"
        )
        logger.info("Created indexes")

        # Seed default agent
        cursor.execute(
            """
            INSERT INTO agents (agent_id, name, description, llm_provider, llm_model, is_default)
            VALUES ('default', 'Default Agent', 'Fallback agent for unconfigured requests',
                    'ollama', 'mistral:7b-instruct', TRUE)
        """
        )
        logger.info("Seeded default agent")

        conn.commit()
        logger.info("Migration complete")

    except Exception as e:
        logger.error("Migration failed: %s", e)
        conn.rollback()
        raise
    finally:
        conn.close()


# Alias for compatibility with migration runner
run_migration = migrate

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)
