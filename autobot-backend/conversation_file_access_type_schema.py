# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Let ``file_access_log.access_type`` hold ``reference`` on a database made before #21404.

No request-handling imports: a migration may import it. SQLite cannot alter a CHECK in place, so the log is
rebuilt from the one definition in the schema file; every row is copied across unchanged.
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from autobot_shared.logging_manager import get_logger

logger = get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "database/schemas/conversation_files_schema.sql"
_TABLE = re.compile(r"CREATE TABLE IF NOT EXISTS file_access_log \(.*?\n\);", re.DOTALL)
_INDEX = re.compile(r"CREATE INDEX IF NOT EXISTS idx_file_access_log_\w+\s+ON file_access_log\([^)]*\);")
_STAGE_SQL = (
    "CREATE TEMP TABLE file_access_log_rebuild AS "
    "SELECT log_id, file_id, access_type, accessed_by, accessed_at, access_metadata FROM file_access_log"
)
_RESTORE_SQL = (
    "INSERT INTO file_access_log (log_id, file_id, access_type, accessed_by, accessed_at, access_metadata) "
    "SELECT log_id, file_id, access_type, accessed_by, accessed_at, access_metadata FROM file_access_log_rebuild"
)
_REMOVE_OLD_SQL = "DROP TABLE file_access_log"
_REMOVE_STAGE_SQL = "DROP TABLE file_access_log_rebuild"


def _accepts_reference(connection: sqlite3.Connection) -> bool:
    row = connection.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='file_access_log'").fetchone()
    return row is None or "'reference'" in row[0]


def ensure_access_type_schema(connection: sqlite3.Connection) -> None:
    """Rebuild ``file_access_log`` with ``reference`` allowed, keeping every row. Idempotent: a no-op once allowed."""
    if _accepts_reference(connection):
        return
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    statements = [_TABLE.search(schema).group(0), *_INDEX.findall(schema)]
    connection.commit()
    try:
        connection.execute("BEGIN")
        connection.execute(_STAGE_SQL)
        connection.execute(_REMOVE_OLD_SQL)
        for statement in statements:
            connection.execute(statement)
        connection.execute(_RESTORE_SQL)
        connection.execute(_REMOVE_STAGE_SQL)
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    logger.info("file_access_log now accepts access_type 'reference' (#21404)")
