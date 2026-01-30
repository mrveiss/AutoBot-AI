# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add node_credentials table.

This adds encrypted credential storage for VNC, SSH, and other
service credentials. Related to Issue #725.
"""

import logging
import os
import sqlite3
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


def migrate(db_path: str) -> None:
    """Add node_credentials table for encrypted credential storage."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if table exists
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='node_credentials'"
    )
    table_exists = cursor.fetchone() is not None

    if not table_exists:
        logger.info("Creating node_credentials table...")
        cursor.execute("""
            CREATE TABLE node_credentials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                websockify_enabled BOOLEAN DEFAULT 1,
                is_active BOOLEAN DEFAULT 1,
                last_used TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(node_id, credential_type, name)
            )
        """)

        # Create indexes
        cursor.execute(
            "CREATE INDEX idx_credentials_node_id ON node_credentials(node_id)"
        )
        cursor.execute(
            "CREATE INDEX idx_credentials_type ON node_credentials(credential_type)"
        )
        cursor.execute(
            "CREATE INDEX idx_credentials_active ON node_credentials(is_active)"
        )
        logger.info("Created node_credentials table with indexes")
    else:
        logger.info("node_credentials table already exists")

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


def get_default_db_path() -> str:
    """Get default database path from config or environment."""
    # Check environment variable first
    db_path = os.getenv("SLM_DATABASE_PATH")
    if db_path:
        return db_path

    # Fall back to relative path from slm-server directory
    base_dir = Path(__file__).parent.parent
    return str(base_dir / "data" / "slm.db")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        db_path = get_default_db_path()
    else:
        db_path = sys.argv[1]

    logger.info("Migrating database: %s", db_path)
    migrate(db_path)
