# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add component_sync_jobs table.

Persists per-component drift/resolve job tracking to survive SLM backend
restarts.  When the resolved component is autobot-slm-backend, the final
service restart kills the in-flight request.  The job row is committed before
the restart so the GUI can poll for completion (#11303, same rationale as
#1707 for fleet_sync_jobs).
"""

import logging
import sys

from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)


def _create_component_sync_jobs(cursor) -> None:
    """Create component_sync_jobs table if not exists (#11303)."""
    if table_exists(cursor, "component_sync_jobs"):
        logger.info("component_sync_jobs table already exists")
        return

    logger.info("Creating component_sync_jobs table...")
    cursor.execute("""
        CREATE TABLE component_sync_jobs (
            id SERIAL PRIMARY KEY,
            job_id VARCHAR(64) UNIQUE NOT NULL,
            component VARCHAR(64) NOT NULL,
            status VARCHAR(20) DEFAULT 'pending',
            success BOOLEAN,
            deps_changed BOOLEAN DEFAULT FALSE,
            message TEXT,
            post_steps TEXT,
            created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMPTZ
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_component_sync_jobs_job_id " "ON component_sync_jobs (job_id)")
    logger.info("Created component_sync_jobs table")


def migrate(db_url: str) -> None:
    """Add component sync job tracking table (#11303)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    _create_component_sync_jobs(cursor)

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
