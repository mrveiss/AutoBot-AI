# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add health monitoring columns to blue_green_deployments table

Issue #726 Phase 3: Automatic rollback with health monitoring

Adds the following columns:
- post_deploy_monitor_duration: Duration of post-deployment monitoring (seconds)
- health_failure_threshold: Consecutive failures before rollback
- health_failures: Current failure count
- monitoring_started_at: When monitoring started
"""

import asyncio
import logging
from pathlib import Path
import aiosqlite

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path (relative to slm-server directory)
DB_PATH = Path(__file__).parent.parent / "data" / "slm.db"


async def check_column_exists(db: aiosqlite.Connection, table: str, column: str) -> bool:
    """Check if a column exists in a table."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = await cursor.fetchall()
    return any(col[1] == column for col in columns)


async def migrate():
    """Run the migration."""
    if not DB_PATH.exists():
        logger.info("Database does not exist yet - migration will be applied on creation")
        return

    logger.info("Connecting to database: %s", DB_PATH)

    async with aiosqlite.connect(DB_PATH) as db:
        # Check if table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blue_green_deployments'"
        )
        if not await cursor.fetchone():
            logger.info("Table blue_green_deployments does not exist - skipping migration")
            return

        # Add post_deploy_monitor_duration column
        if not await check_column_exists(db, "blue_green_deployments", "post_deploy_monitor_duration"):
            logger.info("Adding column: post_deploy_monitor_duration")
            await db.execute(
                "ALTER TABLE blue_green_deployments ADD COLUMN post_deploy_monitor_duration INTEGER DEFAULT 1800"
            )
        else:
            logger.info("Column post_deploy_monitor_duration already exists")

        # Add health_failure_threshold column
        if not await check_column_exists(db, "blue_green_deployments", "health_failure_threshold"):
            logger.info("Adding column: health_failure_threshold")
            await db.execute(
                "ALTER TABLE blue_green_deployments ADD COLUMN health_failure_threshold INTEGER DEFAULT 3"
            )
        else:
            logger.info("Column health_failure_threshold already exists")

        # Add health_failures column
        if not await check_column_exists(db, "blue_green_deployments", "health_failures"):
            logger.info("Adding column: health_failures")
            await db.execute(
                "ALTER TABLE blue_green_deployments ADD COLUMN health_failures INTEGER DEFAULT 0"
            )
        else:
            logger.info("Column health_failures already exists")

        # Add monitoring_started_at column
        if not await check_column_exists(db, "blue_green_deployments", "monitoring_started_at"):
            logger.info("Adding column: monitoring_started_at")
            await db.execute(
                "ALTER TABLE blue_green_deployments ADD COLUMN monitoring_started_at DATETIME"
            )
        else:
            logger.info("Column monitoring_started_at already exists")

        await db.commit()
        logger.info("Migration completed successfully")


def main():
    """Entry point for running migration directly."""
    asyncio.run(migrate())


if __name__ == "__main__":
    main()
