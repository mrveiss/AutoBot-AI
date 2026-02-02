# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add agents table for per-agent LLM configuration.

Issue #760 Phase 2
"""

import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def run_migration(db_path: str = "slm.db") -> bool:
    """Run the agents table migration."""
    logger.info("Running agents migration...")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Check if table already exists
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='agents'"
        )
        if cursor.fetchone():
            logger.info("agents table already exists, skipping creation")
            return True

        # Create agents table
        cursor.execute(
            """
            CREATE TABLE agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        logger.info("Created agents table")

        # Create indexes
        cursor.execute("CREATE INDEX idx_agents_agent_id ON agents(agent_id)")
        cursor.execute("CREATE INDEX idx_agents_is_default ON agents(is_default)")
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
        return True

    except Exception as e:
        logger.error("Migration failed: %s", e)
        conn.rollback()
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Find database
    db_path = Path("slm.db")
    if not db_path.exists():
        db_path = Path("data/slm.db")

    if not db_path.exists():
        logger.error("Database not found")
        exit(1)

    success = run_migration(str(db_path))
    exit(0 if success else 1)
