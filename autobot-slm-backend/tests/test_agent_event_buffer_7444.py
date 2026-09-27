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

import ast
import sqlite3
from pathlib import Path

import pytest

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


# ---------------------------------------------------------------------------
# Where the agent calls the buffer from (#17647 review)
# ---------------------------------------------------------------------------
#
# Both findings below are about a CALL SITE, not about a function's behaviour, so
# they are asserted against the AST of the call site. A behavioural test would
# pass with either version: `prune` trims correctly whether or not the run loop
# reaches it, and `buffer_event` inserts correctly whether or not the event loop
# was free while it did. The defect was reachability in one case and scheduling
# in the other, and only the call site records those.

_AGENT_SOURCES = [
    "autobot-slm-backend/slm/agent/agent.py",
    "autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/agent.py",
]


def _tree(rel: str) -> ast.Module:
    root = Path(__file__).resolve().parents[2]
    return ast.parse((root / rel).read_text(encoding="utf-8"))


def _function(tree: ast.Module, name: str) -> ast.AST:
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} not found")


def _calls_named(node: ast.AST, name: str) -> list:
    found = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            func = sub.func
            if (isinstance(func, ast.Attribute) and func.attr == name) or (
                isinstance(func, ast.Name) and func.id == name
            ):
                found.append(sub)
    return found


@pytest.mark.parametrize("rel", _AGENT_SOURCES)
class TestBufferCallSites:
    def test_the_cap_is_not_reached_only_through_a_connectivity_check(self, rel: str) -> None:
        """`prune_event_buffer()` must not sit under an `if` in the run loop.

        The bug: the prune lived at the top of `sync_buffered_events`, which the
        run loop calls only `if success`. Heartbeats fail during an admin outage,
        every failure appends a row, so nothing ever trimmed -- the cap was dead
        in the one situation it exists for. Asserting the call is unconditional is
        the assertion that survives a revert.
        """
        run = _function(_tree(rel), "run")
        calls = _calls_named(run, "prune_event_buffer")
        assert calls, "run() must reach prune_event_buffer()"

        guarded = set()
        for node in ast.walk(run):
            if isinstance(node, ast.If):
                for branch in (node.body, node.orelse):
                    for stmt in branch:
                        guarded.update(id(c) for c in _calls_named(stmt, "prune_event_buffer"))
        assert not [
            c for c in calls if id(c) in guarded
        ], "prune_event_buffer() is inside an `if` in run() -- the cap is gated again"

    def test_the_offline_insert_is_offloaded_not_called_inline(self, rel: str) -> None:
        """The heartbeat failure path writes to sqlite; it must not do so on the loop.

        `buffer_event` is sync and stays sync -- `_process_code_change` is a sync
        caller. The async caller hands it to a thread instead, so the assertion is
        that `_send_heartbeat_request` contains no *direct* `buffer_event(...)`
        call, only one passed to `to_thread`.
        """
        fn = _function(_tree(rel), "_send_heartbeat_request")
        direct = [c for c in _calls_named(fn, "buffer_event")]
        assert direct == [], "buffer_event(...) is called inline in an async function"

        handed_off = [
            arg
            for call in _calls_named(fn, "to_thread")
            for arg in call.args
            if isinstance(arg, ast.Attribute) and arg.attr == "buffer_event"
        ]
        assert handed_off, "the failure path no longer buffers the heartbeat at all"
