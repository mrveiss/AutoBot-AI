# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add fleet_sync_jobs and fleet_sync_node_states tables.

Persists fleet sync job tracking to survive SLM backend restarts.
Previously, jobs were tracked in-memory and lost when the SLM
self-node sync triggered a service restart (#1707).
"""

import logging
import sys

from migrations.utils import create_index_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def _create_fleet_sync_jobs(cursor) -> None:
    """Create fleet_sync_jobs table if not exists (#1707)."""
    if table_exists(cursor, "fleet_sync_jobs"):
        logger.info("fleet_sync_jobs table already exists")
        return

    logger.info("Creating fleet_sync_jobs table...")
    cursor.execute("""
        CREATE TABLE fleet_sync_jobs (
            id SERIAL PRIMARY KEY,
            job_id VARCHAR(64) UNIQUE NOT NULL,
            strategy VARCHAR(20) NOT NULL,
            batch_size INTEGER DEFAULT 1,
            restart BOOLEAN DEFAULT TRUE,
            status VARCHAR(20) DEFAULT 'pending',
            total_nodes INTEGER DEFAULT 0,
            completed_nodes INTEGER DEFAULT 0,
            failed_nodes INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    create_index_if_not_exists(cursor, "idx_fleet_sync_jobs_status", "fleet_sync_jobs", "status")
    create_index_if_not_exists(cursor, "idx_fleet_sync_jobs_created", "fleet_sync_jobs", "created_at")
    logger.info("Created fleet_sync_jobs table")


def _create_fleet_sync_node_states(cursor) -> None:
    """Create fleet_sync_node_states table if not exists (#1707)."""
    if table_exists(cursor, "fleet_sync_node_states"):
        logger.info("fleet_sync_node_states table already exists")
        return

    logger.info("Creating fleet_sync_node_states table...")
    cursor.execute("""
        CREATE TABLE fleet_sync_node_states (
            id SERIAL PRIMARY KEY,
            job_id VARCHAR(64) NOT NULL
                REFERENCES fleet_sync_jobs(job_id) ON DELETE CASCADE,
            node_id VARCHAR(64) NOT NULL,
            hostname VARCHAR(128),
            ip_address VARCHAR(45),
            status VARCHAR(20) DEFAULT 'pending',
            message TEXT,
            started_at TIMESTAMP,
            completed_at TIMESTAMP
        )
    """)
    create_index_if_not_exists(
        cursor,
        "idx_fleet_sync_node_states_job",
        "fleet_sync_node_states",
        "job_id",
    )
    logger.info("Created fleet_sync_node_states table")


def migrate(db_url: str) -> None:
    """Add fleet sync job tracking tables (#1707)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    _create_fleet_sync_jobs(cursor)
    _create_fleet_sync_node_states(cursor)

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
