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

Why a wider lint call-list would not have found the original defect: the prune
call was a *sync* method invoked from async, and a guard that resets its async
depth inside sync bodies -- correctly, since sync helpers have sync callers --
cannot see the ``sqlite3.connect`` one frame down. Widening the vocabulary of
``tools/lint/check_no_blocking_io_in_async.py`` does not reach that shape;
moving the blocking work here and scheduling it explicitly does.
"""

import json
import logging
import sqlite3
from pathlib import Path

from autobot_shared import env_utils, time_utils

logger = logging.getLogger(__name__)

#: Rows read per sync attempt. One admin POST carries at most this many events.
#:
#: Read through ``env_utils`` rather than ``int(os.getenv(...))``: a bare cast
#: raises ``ValueError`` at **import**, and for an agent module that means a
#: malformed value in a node's environment stops the agent from starting rather
#: than degrading one setting. Caught by ``repo_tests/env_var_bare_cast_test.py``
#: on the first attempt at this change, which is what the guard is for.
#:
#: Floored at 1: a batch size of 0 reads nothing, forever, while the buffer fills.
SYNC_BATCH_SIZE = env_utils.env_int_clamped("SLM_SYNC_BATCH_SIZE", 100, min_v=1)

#: Cap on buffered rows. Oldest-first pruning keeps an offline node from
#: filling its disk while the admin is unreachable.
#:
#: Env-backed, following ``DEFAULT_BUFFER_DB`` in ``agent.py``: both were bare
#: literals, and a fleet-wide cap that can only be changed by shipping code is
#: the shape the project's no-hardcoding rule exists to prevent. #16056 asks for
#: exactly this and for three further things this module cannot provide -- the
#: agent must *report* its depth and its cumulative drops, and the SLM must
#: persist and surface them. Those stay open there; only the literal is settled.
#: Floored at 1: a cap of 0 would delete every row on each prune, and a negative
#: cap makes ``count - max_events`` delete more rows than exist.
MAX_BUFFERED_EVENTS = env_utils.env_int_clamped("SLM_MAX_BUFFERED_EVENTS", 500, min_v=1)

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
    """Append one unsynced event. Blocking.

    ``SLMAgent.buffer_event`` wraps this and has **two** async callers -- the
    heartbeat failure handler and the code-change HTTP handler. The #17647 review
    found the first push had offloaded only one of them, so the rule is recorded
    here rather than at either call site: every async path reaching this function
    goes through ``asyncio.to_thread``, and the hop belongs at the caller, because
    ``buffer_event``'s third caller is synchronous and must stay so.

    For the code-change path the hop wraps the whole of ``_process_code_change``
    rather than this call: that function writes a version file, clears a cache and
    appends a row, so three wrappers would buy nothing over one.
    """
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
    """Delete oldest rows beyond *max_events* (#1106). Blocking.

    This is the buffer's only cap enforcement, and the caller decides when it
    runs -- which is the part that was wrong before. The agent used to prune at
    the top of its event *sync*, and the run loop calls that only when a
    heartbeat succeeded, so during an admin outage every failed heartbeat
    appended a row and nothing ever trimmed: the cap was dead in the one
    situation it exists for (#17647 review). ``SLMAgent.prune_event_buffer``
    now runs it on a path no connectivity check gates.

    Deliberately *not* enforced inside ``append``: that would put a ``COUNT(*)``
    on every insert and give the cap two enforcement points that could disagree.

    The caller runs it **first** in its cycle, ahead of the heartbeat. A total
    request timeout raises ``asyncio.TimeoutError``, which is not an
    ``aiohttp.ClientError``, so it escapes the heartbeat's own handler and lands in
    the run loop's catch-all -- skipping a prune placed after the heartbeat, while
    the code-change endpoint keeps appending rows on its own path. A ``finally``
    would also survive that, but a prune raising inside one would escape the
    catch-all and kill the loop (#9965); ordering costs nothing and cannot
    (#17647 review, round 3).

    ``SLMAgent.prune_event_buffer`` swallows and logs any failure from this
    function rather than letting it propagate. It runs *before* the heartbeat, and
    the run loop's catch-all wraps both -- so an unhandled buffer fault here would
    skip health reporting for that cycle and a node with a full disk or a corrupt
    buffer would go dark while otherwise healthy. Ordering the prune first fixed a
    timeout escaping past it and introduced that; isolating its exceptions is what
    makes both orderings safe (#17647 review, round 5).

    ``db_path`` has no default on purpose. Reaching a defaulted path with no
    argument is exactly how the previous prune came to trim a file the agent was
    not writing to.
    """
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
