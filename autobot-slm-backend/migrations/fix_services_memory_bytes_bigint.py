# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Fix services.memory_bytes column type from INTEGER to BIGINT.

The services table was created with memory_bytes as INTEGER before issue #922
changed the ORM model to BigInteger. Values > 2,147,483,647 bytes (~2GB) cause
sqlalchemy.exc.DBAPIError: NumericValueOutOfRangeError on heartbeat updates.

Alters the existing column in-place using ALTER TABLE ... ALTER COLUMN,
which is safe on PostgreSQL without data loss (widening integer type).
"""

import logging
import sys

from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)


def _get_column_type(cursor, table_name: str, column_name: str) -> str:
    """Return the current PostgreSQL data type for a column."""
    cursor.execute(
        """
        SELECT data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        """,
        (table_name, column_name),
    )
    row = cursor.fetchone()
    return row[0] if row else ""


def migrate(db_url: str) -> None:
    """Widen services.memory_bytes from INTEGER to BIGINT."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if not table_exists(cursor, "services"):
        logger.info("services table does not exist - skipping migration")
        conn.close()
        return

    current_type = _get_column_type(cursor, "services", "memory_bytes")
    if current_type.lower() in ("bigint", "int8"):
        logger.info("services.memory_bytes is already BIGINT - skipping")
        conn.close()
        return

    logger.info("Altering services.memory_bytes from %s to BIGINT...", current_type)
    cursor.execute("ALTER TABLE services ALTER COLUMN memory_bytes TYPE BIGINT")

    conn.commit()
    conn.close()
    logger.info("Migration completed: services.memory_bytes is now BIGINT")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    from migrations.runner import get_db_url

    db_url = sys.argv[1] if len(sys.argv) > 1 else get_db_url()
    logger.info("Migrating database: %s", db_url)
    migrate(db_url)
