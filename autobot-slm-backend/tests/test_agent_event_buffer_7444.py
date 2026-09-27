# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The agent's event buffer, extracted out of the event loop (#7444, #1106).

The extraction is behaviour-preserving except for one fix, which is why these
tests exist: the prune call used to reach a ``@staticmethod`` whose ``db_path``
defaulted to ``DEFAULT_BUFFER_DB``, and it was invoked with no argument. An
agent configured with a non-default ``buffer_db`` therefore pruned the default
file and let its own buffer grow past the cap forever.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from slm.agent import event_buffer


def _db(tmp_path: Path) -> str:
    path = str(tmp_path / "nested" / "events.db")
    event_buffer.initialize(path)
    return path


class TestRoundTrip:
    def test_initialize_creates_the_parent_directory_and_table(self, tmp_path: Path) -> None:
        path = _db(tmp_path)
        assert Path(path).exists()
        conn = sqlite3.connect(path)
        try:
            names = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        finally:
            conn.close()
        assert "event_buffer" in names

    def test_initialize_is_idempotent(self, tmp_path: Path) -> None:
        path = _db(tmp_path)
        event_buffer.append(path, "boot", {"n": 1})
        event_buffer.initialize(path)  # CREATE TABLE IF NOT EXISTS — must not drop rows
        assert len(event_buffer.read_unsynced(path)) == 1

    def test_appended_events_read_back_unsynced_with_their_payload(self, tmp_path: Path) -> None:
        path = _db(tmp_path)
        event_buffer.append(path, "health", {"cpu": 12})
        rows = event_buffer.read_unsynced(path)
        assert [(r[1], r[2]) for r in rows] == [("health", '{"cpu": 12}')]

    def test_mark_synced_removes_rows_from_the_unsynced_view(self, tmp_path: Path) -> None:
        path = _db(tmp_path)
        for i in range(3):
            event_buffer.append(path, "e", {"i": i})
        rows = event_buffer.read_unsynced(path)
        event_buffer.mark_synced(path, [rows[0][0], rows[1][0]])
        assert [r[2] for r in event_buffer.read_unsynced(path)] == ['{"i": 2}']

    def test_mark_synced_with_no_ids_opens_no_connection(self, tmp_path: Path, monkeypatch) -> None:
        """The empty-list guard is about the connection, not about SQL validity.

        Asserted by watching ``sqlite3.connect``, because the obvious assertion --
        that the rows are untouched -- passes with the guard removed: SQLite accepts
        an empty ``IN ()`` and the UPDATE simply matches nothing. Removing the guard
        would cost a connection per idle sync, and a row-count assertion would not
        notice.
        """
        path = _db(tmp_path)
        event_buffer.append(path, "e", {})

        opened: list = []
        real_connect = sqlite3.connect
        monkeypatch.setattr(event_buffer.sqlite3, "connect", lambda *a, **k: opened.append(a) or real_connect(*a, **k))
        event_buffer.mark_synced(path, [])

        assert opened == []
        assert len(event_buffer.read_unsynced(path)) == 1

    def test_read_unsynced_honours_its_limit(self, tmp_path: Path) -> None:
        path = _db(tmp_path)
        for i in range(5):
            event_buffer.append(path, "e", {"i": i})
        assert len(event_buffer.read_unsynced(path, limit=2)) == 2


class TestPrune:
    def test_prune_drops_the_oldest_rows_beyond_the_cap(self, tmp_path: Path) -> None:
        path = _db(tmp_path)
        for i in range(6):
            event_buffer.append(path, "e", {"i": i})
        event_buffer.prune(path, max_events=2)
        assert [r[2] for r in event_buffer.read_unsynced(path)] == ['{"i": 4}', '{"i": 5}']

    def test_prune_under_the_cap_changes_nothing(self, tmp_path: Path) -> None:
        path = _db(tmp_path)
        event_buffer.append(path, "e", {"i": 0})
        event_buffer.prune(path, max_events=500)
        assert len(event_buffer.read_unsynced(path)) == 1

    def test_prune_acts_on_the_path_it_is_given_and_not_a_default(self, tmp_path: Path) -> None:
        """The #7444 fix. Two buffers; pruning one must not touch the other.

        This is the shape of the bug that was there: the caller passed no path, so
        the cap was enforced against ``DEFAULT_BUFFER_DB`` while the configured
        buffer grew unbounded. A prune function with no default cannot repeat it.
        """
        configured = _db(tmp_path / "configured")
        other = _db(tmp_path / "other")
        for i in range(4):
            event_buffer.append(configured, "e", {"i": i})
            event_buffer.append(other, "e", {"i": i})

        event_buffer.prune(configured, max_events=1)

        assert len(event_buffer.read_unsynced(configured)) == 1
        assert len(event_buffer.read_unsynced(other)) == 4
