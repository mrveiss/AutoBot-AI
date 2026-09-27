# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""SQLite event-buffer persistence for the SLM agent (#1106, #7444).

Every function here opens its own connection, does one unit of work, and closes
it. All of them **block**, so an async caller goes through
``asyncio.to_thread`` -- which is why they are a module and not methods on
``SLMAgent``: the agent used to run this sqlite work on the event loop and hold
one connection open across an ``await`` on a 30-second HTTP POST, so a slow
admin held both the loop and a database handle for the whole timeout. A
connection that cannot outlive a single call cannot be held across an await.

``asyncio`` is deliberately not imported here. This module is the blocking half;
the scheduling decision belongs to its caller.
"""

import json
import logging
import sqlite3
from pathlib import Path

from autobot_shared import time_utils

logger = logging.getLogger(__name__)

#: Rows read per sync attempt. One admin POST carries at most this many events.
SYNC_BATCH_SIZE = 100

#: Cap on buffered rows. Oldest-first pruning keeps an offline node from
#: filling its disk while the admin is unreachable.
MAX_BUFFERED_EVENTS = 500

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS event_buffer (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT NOT NULL,
        event_type TEXT NOT NULL,
        data TEXT NOT NULL,
        synced INTEGER DEFAULT 0
    )
"""


def initialize(db_path: str) -> None:
    """Create the buffer database and its table if absent. Blocking."""
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(_SCHEMA)
        conn.commit()
    finally:
        conn.close()
    logger.info("Event buffer initialized at %s", db_path)


def append(db_path: str, event_type: str, data: dict) -> None:
    """Append one unsynced event. Blocking."""
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO event_buffer (timestamp, event_type, data) VALUES (?, ?, ?)",
            (time_utils.utc_timestamp(), event_type, json.dumps(data)),
        )
        conn.commit()
    finally:
        conn.close()


def read_unsynced(db_path: str, limit: int = SYNC_BATCH_SIZE) -> list:
    """Return ``(id, event_type, data)`` for up to *limit* unsynced rows. Blocking."""
    conn = sqlite3.connect(db_path)
    try:
        return conn.execute(
            "SELECT id, event_type, data FROM event_buffer WHERE synced = 0 ORDER BY id LIMIT ?",
            (limit,),
        ).fetchall()
    finally:
        conn.close()


def mark_synced(db_path: str, ids: list) -> None:
    """Mark *ids* as synced. Blocking. A empty *ids* is a no-op, not a bare ``IN ()``."""
    if not ids:
        return
    conn = sqlite3.connect(db_path)
    try:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE event_buffer SET synced = 1 WHERE id IN ({placeholders})",  # nosec B608
            ids,
        )
        conn.commit()
    finally:
        conn.close()


def prune(db_path: str, max_events: int = MAX_BUFFERED_EVENTS) -> None:
    """Delete oldest rows beyond *max_events* (#1106). Blocking."""
    conn = sqlite3.connect(db_path)
    try:
        count = conn.execute("SELECT COUNT(*) FROM event_buffer").fetchone()[0]
        if count <= max_events:
            return
        conn.execute(
            "DELETE FROM event_buffer WHERE id IN (  SELECT id FROM event_buffer  ORDER BY id ASC LIMIT ?)",
            (count - max_events,),
        )
        conn.commit()
        logger.info("Pruned %d old events (cap=%d)", count - max_events, max_events)
    finally:
        conn.close()
