# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Add error resolution fields to node_events table

Issue #563: Error Monitoring Dashboard

Adds the following columns to node_events:
- resolved: Boolean flag indicating if error has been resolved
- resolved_at: Timestamp when error was resolved
- resolved_by: Username who resolved the error
"""

import asyncio
import logging
from pathlib import Path

import aiosqlite

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Database path (relative to slm-server directory)
DB_PATH = Path(__file__).parent.parent / "data" / "slm.db"


async def check_column_exists(
    db: aiosqlite.Connection, table: str, column: str
) -> bool:
    """Check if a column exists in a table."""
    cursor = await db.execute(f"PRAGMA table_info({table})")
    columns = await cursor.fetchall()
    return any(col[1] == column for col in columns)


def migrate(db_path: str = None) -> None:
    """Synchronous entry point for migration runner."""
    global DB_PATH
    if db_path:
        DB_PATH = Path(db_path)
    asyncio.run(_migrate_async())


async def _migrate_async():
    """Run the migration (async implementation)."""
    if not DB_PATH.exists():
        logger.info(
            "Database does not exist yet - migration will be applied on creation"
        )
        return

    logger.info("Connecting to database: %s", DB_PATH)

    async with aiosqlite.connect(DB_PATH) as db:
        # Check if table exists
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='node_events'"
        )
        if not await cursor.fetchone():
            logger.info("Table node_events does not exist - skipping migration")
            return

        # Add resolved column
        if not await check_column_exists(db, "node_events", "resolved"):
            logger.info("Adding column: resolved")
            await db.execute(
                "ALTER TABLE node_events ADD COLUMN resolved BOOLEAN DEFAULT 0"
            )
        else:
            logger.info("Column resolved already exists")

        # Add resolved_at column
        if not await check_column_exists(db, "node_events", "resolved_at"):
            logger.info("Adding column: resolved_at")
            await db.execute("ALTER TABLE node_events ADD COLUMN resolved_at DATETIME")
        else:
            logger.info("Column resolved_at already exists")

        # Add resolved_by column
        if not await check_column_exists(db, "node_events", "resolved_by"):
            logger.info("Adding column: resolved_by")
            await db.execute(
                "ALTER TABLE node_events ADD COLUMN resolved_by VARCHAR(255)"
            )
        else:
            logger.info("Column resolved_by already exists")

        await db.commit()
        logger.info("Migration completed successfully - error resolution fields added")


def main():
    """Entry point for running migration directly."""
    asyncio.run(_migrate_async())


if __name__ == "__main__":
    main()
