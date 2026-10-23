# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add post_sync_action_runs table (#17455).

One row per post-sync command or restart a code sync executed, grouped by
`run_id`, so the sync's own history answers "what post-sync work ran, and did it
succeed". Idempotent: skipped when the table exists. Reversible: DROP TABLE
removes it, nothing references it.
"""

import logging
import sys

from autobot_shared.secret_redaction import redact_url_credentials
from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)


_CREATE_TABLE = """
        CREATE TABLE post_sync_action_runs (
            id SERIAL PRIMARY KEY,
            run_id VARCHAR(64) NOT NULL,
            node_id VARCHAR(64) NOT NULL,
            role_name VARCHAR(50) NOT NULL,
            category VARCHAR(20) NOT NULL,
            label VARCHAR(255) NOT NULL,
            command TEXT,
            units TEXT,
            started_at TIMESTAMPTZ NOT NULL,
            finished_at TIMESTAMPTZ NOT NULL,
            exit_code INTEGER,
            success BOOLEAN,
            output_tail TEXT NOT NULL DEFAULT '',
            error TEXT
        )
    """

_CREATE_INDEX = "CREATE INDEX ix_post_sync_action_runs_run_id ON post_sync_action_runs (run_id)"


def migrate(db_url: str) -> None:
    """Add post_sync_action_runs table (#17455)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if table_exists(cursor, "post_sync_action_runs"):
        logger.info("post_sync_action_runs table already exists")
        conn.close()
        return

    logger.info("Creating post_sync_action_runs table...")
    cursor.execute(_CREATE_TABLE)
    cursor.execute(_CREATE_INDEX)

    conn.commit()
    conn.close()
    logger.info("Created post_sync_action_runs table")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", redact_url_credentials(db_url))  # #18664
    migrate(db_url)
