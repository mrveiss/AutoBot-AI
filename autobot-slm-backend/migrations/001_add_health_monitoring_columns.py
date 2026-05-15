# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add health monitoring columns to blue_green_deployments table

Issue #726 Phase 3: Automatic rollback with health monitoring
Updated for PostgreSQL (Issue #786).

Adds the following columns:
- post_deploy_monitor_duration: Duration of post-deployment monitoring (seconds)
- health_failure_threshold: Consecutive failures before rollback
- health_failures: Current failure count
- monitoring_started_at: When monitoring started
"""

import logging
import sys

from migrations.utils import add_column_if_not_exists, get_connection, table_exists

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Run the migration (#786)."""
    logger.info("Running health monitoring columns migration")

    conn = get_connection(db_url)
    cursor = conn.cursor()

    # Check if table exists
    if not table_exists(cursor, "blue_green_deployments"):
        logger.info("Table blue_green_deployments does not exist - skipping migration")
        conn.close()
        return

    # Add post_deploy_monitor_duration column
    add_column_if_not_exists(
        cursor,
        "blue_green_deployments",
        "post_deploy_monitor_duration",
        "INTEGER DEFAULT 1800",
    )

    # Add health_failure_threshold column
    add_column_if_not_exists(
        cursor,
        "blue_green_deployments",
        "health_failure_threshold",
        "INTEGER DEFAULT 3",
    )

    # Add health_failures column
    add_column_if_not_exists(
        cursor,
        "blue_green_deployments",
        "health_failures",
        "INTEGER DEFAULT 0",
    )

    # Add monitoring_started_at column
    add_column_if_not_exists(
        cursor,
        "blue_green_deployments",
        "monitoring_started_at",
        "TIMESTAMP",
    )

    conn.commit()
    conn.close()
    logger.info("Migration completed successfully")


def main():
    """Entry point for running migration directly."""
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    migrate(db_url)


if __name__ == "__main__":
    main()
