# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""
Migration: Widen code_status column from VARCHAR(20) to VARCHAR(50).

The CODE_CURRENT_SERVICE_FAILED enum value (#1605) is 27 chars,
exceeding the original VARCHAR(20) constraint.
Related to Issue #1622.
"""

import logging

from migrations.utils import get_connection, table_exists

logger = logging.getLogger(__name__)


def migrate(db_url: str) -> None:
    """Widen code_status column to VARCHAR(50) (#1622)."""
    conn = get_connection(db_url)
    cursor = conn.cursor()

    if not table_exists(cursor, "nodes"):
        logger.error("nodes table does not exist.")
        conn.close()
        return

    cursor.execute("ALTER TABLE nodes ALTER COLUMN code_status TYPE VARCHAR(50)")

    conn.commit()
    conn.close()
    logger.info("Widened code_status column to VARCHAR(50)")
