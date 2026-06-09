# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Migration: Add failure_reason column to fleet_sync_jobs table.

Allows callers to distinguish reconciled startup failures
(server restarted while job was running) from genuine sync errors
(#1980).
"""

import logging
import sys

from migrations.utils import add_column_if_not_exists, get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Add failure_reason VARCHAR(500) to fleet_sync_jobs (#1980)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if not table_exists(cursor, "fleet_sync_jobs"):
        logger.error("fleet_sync_jobs table does not exist — skipping")
        conn.close()
        return

    added = add_column_if_not_exists(
        cursor,
        "fleet_sync_jobs",
        "failure_reason",
        "VARCHAR(500)",
    )

    conn.commit()
    conn.close()

    if added:
        logger.info("Added failure_reason column to fleet_sync_jobs")
    else:
        logger.info("failure_reason column already present in fleet_sync_jobs")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
