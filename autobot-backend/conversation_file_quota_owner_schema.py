# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""DDL for ``conversation_files.quota_owner`` (#20678). No request-handling imports: a migration may import it."""

from __future__ import annotations

import sqlite3

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_ADD_COLUMN_SQL = "ALTER TABLE conversation_files ADD COLUMN quota_owner TEXT"
# Same expression the quota sums by, so the per-owner sum stays an index lookup (#20217).
_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_conversation_files_quota_owner "
    "ON conversation_files(COALESCE(quota_owner, uploaded_by), is_deleted)"
)


def ensure_quota_owner_schema(connection: sqlite3.Connection) -> None:
    """Add the ``quota_owner`` column and its index to a database made before #20678. Idempotent; no row changes.

    ``CREATE TABLE IF NOT EXISTS`` in the schema file leaves an existing table as it was, so the column
    is added here, once, when ``PRAGMA table_info`` shows it missing.
    """
    columns = {row[1] for row in connection.execute("PRAGMA table_info(conversation_files)")}
    if "quota_owner" not in columns:
        connection.execute(_ADD_COLUMN_SQL)
        logger.info("Added conversation_files.quota_owner (#20678)")
    connection.execute(_INDEX_SQL)
    connection.commit()
