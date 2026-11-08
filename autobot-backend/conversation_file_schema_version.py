# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Read the conversation-files schema version from a database file (split out of the manager, #20678)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from constants.threshold_constants import TimingConstants


def query_schema_version(db_path: Path) -> str:
    """Thread-safe database query for the schema version; ``"unknown"`` when none is recorded."""
    connection = sqlite3.connect(
        str(db_path),
        timeout=TimingConstants.SHORT_TIMEOUT,
        check_same_thread=False,
    )
    cursor = connection.cursor()
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'")
        if not cursor.fetchone():
            return "unknown"
        cursor.execute("SELECT version FROM schema_migrations ORDER BY migration_id DESC LIMIT 1")
        result = cursor.fetchone()
        return result[0] if result else "unknown"
    finally:
        cursor.close()
        connection.close()
