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
import asyncio
import importlib
import logging
import os
import sqlite3
import types
from pathlib import Path

import pytest

from slm.agent import event_buffer
from slm.agent.agent import SLMAgent


def _raise_disk_full(*_a, **_k):
    raise sqlite3.OperationalError("disk I/O error")


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


class TestEnvBackedLimits:
    """The cap and the batch size are configuration, not constants (#16056 AC5).

    They were bare literals -- `500` inside a staticmethod default and `100`
    inline in a SELECT -- so a fleet-wide cap could only be changed by shipping
    code. Env-backed following `DEFAULT_BUFFER_DB` in `agent.py`.

    Reloading the module is how an import-time `os.getenv` is observed at all.
    Teardown restores the *original* value rather than deleting the variable: on a
    machine that already sets a limit, `delenv` + reload left the module holding the
    default while pytest restored the environment, so the module and its environment
    disagreed for every later test (#17647 review).
    """

    @staticmethod
    def _limit_with(monkeypatch, name: str, value: str, attr: str):
        """`event_buffer.<attr>` as read with *name* set to *value*.

        Returns the **value**, not the module: `importlib.reload` returns the same
        module object it mutates, so a reference captured before the teardown reload
        is not a snapshot -- it reads the restored default. The first version of this
        helper returned the module and every assertion against it saw 500/100.
        """
        original = os.environ.get(name)
        monkeypatch.setenv(name, value)
        try:
            return getattr(importlib.reload(event_buffer), attr)
        finally:
            if original is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, original)
            importlib.reload(event_buffer)

    @pytest.mark.parametrize(
        ("env", "attr"),
        [
            ("SLM_MAX_BUFFERED_EVENTS", "MAX_BUFFERED_EVENTS"),
            ("SLM_SYNC_BATCH_SIZE", "SYNC_BATCH_SIZE"),
        ],
    )
    def test_each_limit_reads_its_env_var(self, monkeypatch, env: str, attr: str) -> None:
        assert self._limit_with(monkeypatch, env, "7", attr) == 7

    @pytest.mark.parametrize("env", ["SLM_MAX_BUFFERED_EVENTS", "SLM_SYNC_BATCH_SIZE"])
    def test_a_malformed_value_falls_back_instead_of_killing_the_import(self, monkeypatch, env: str) -> None:
        """The first attempt at env-backing used `int(os.getenv(...))`.

        A bare cast raises `ValueError` at **import**, and for an agent module that
        means a typo in one node's environment stops the agent from starting rather
        than degrading one setting. `repo_tests/env_var_bare_cast_test.py` caught it
        in CI; this pins the behaviour at the site so the shape cannot come back
        quietly with the guard's population ceiling unchanged.
        """
        attr = {"SLM_MAX_BUFFERED_EVENTS": "MAX_BUFFERED_EVENTS"}.get(env, "SYNC_BATCH_SIZE")
        # Must not raise: a bare cast would have died at import here.
        assert self._limit_with(monkeypatch, env, "not-a-number", attr) in (500, 100)

    @pytest.mark.parametrize(
        ("env", "attr"),
        [("SLM_MAX_BUFFERED_EVENTS", "MAX_BUFFERED_EVENTS"), ("SLM_SYNC_BATCH_SIZE", "SYNC_BATCH_SIZE")],
    )
    def test_a_zero_or_negative_limit_is_clamped(self, monkeypatch, env: str, attr: str) -> None:
        """A cap of 0 deletes every row on each prune; a batch of 0 reads nothing, forever."""
        assert self._limit_with(monkeypatch, env, "0", attr) == 1

    def test_the_default_is_unchanged_without_the_env_var(self) -> None:
        # Env-backing must not quietly alter behaviour for every existing node.
        # Skipped rather than failed where a limit is configured: the assertion is
        # about the *default*, and an environment that sets one cannot answer it.
        configured = [v for v in ("SLM_MAX_BUFFERED_EVENTS", "SLM_SYNC_BATCH_SIZE") if os.environ.get(v)]
        if configured:
            pytest.skip(f"configured in this environment: {configured}")
        assert (event_buffer.MAX_BUFFERED_EVENTS, event_buffer.SYNC_BATCH_SIZE) == (500, 100)


class TestPruneFailureDoesNotSilenceTheNode:
    """A buffer fault must not cost the heartbeat (#17647 review, round 5).

    Behavioural rather than an AST pin, unlike the ordering assertions: the property
    is "does not propagate", which is directly observable. The ordering ones are not
    -- prune trims correctly whether or not the loop reaches it.
    """

    @staticmethod
    async def _prune(monkeypatch, buffer_db: str):
        agent = types.SimpleNamespace(buffer_db=buffer_db)
        monkeypatch.setattr(event_buffer, "prune", _raise_disk_full)
        await SLMAgent.prune_event_buffer(agent)

    def test_a_failing_prune_is_logged_and_swallowed(self, tmp_path: Path, monkeypatch, caplog) -> None:
        # Ordering the prune first closed a timeout escaping past it, and opened
        # this: the run loop's catch-all wraps both, so an unhandled fault here
        # skipped the heartbeat and the node went dark while otherwise healthy.
        with caplog.at_level(logging.WARNING, logger="slm.agent.agent"):
            asyncio.run(self._prune(monkeypatch, str(tmp_path / "events.db")))  # must not raise
        assert [
            r for r in caplog.records if "prune failed" in r.getMessage().lower()
        ], "the failure was swallowed without a log line -- silent is worse than raising"


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


def _awaited_to_thread(node: ast.AST) -> list:
    """`to_thread(...)` calls that are the operand of an `await`.

    Required because `asyncio.to_thread(f)` without `await` returns a coroutine
    that is never run -- `f` does not execute at all. An assertion that only checks
    the callable was *passed* to `to_thread` therefore passes on a fix that does
    nothing, which was proved on this PR by mutating the `await` away and watching
    both original assertions still pass. Raised as Trivial in review; a pin that
    certifies an inert fix is not trivial.
    """
    return [
        sub.value
        for sub in ast.walk(node)
        if isinstance(sub, ast.Await)
        and isinstance(sub.value, ast.Call)
        and isinstance(sub.value.func, ast.Attribute)
        and sub.value.func.attr == "to_thread"
    ]


def _offloaded(node: ast.AST, name: str) -> list:
    """*name* handed to an **awaited** `to_thread` as its **first** argument.

    First argument specifically, because `to_thread(func, *args)` only calls its
    first argument. Accepting any position let
    `await asyncio.to_thread(lambda unused: None, self.buffer_event)` satisfy the
    pin while never calling `buffer_event` at all -- the third distinct way this
    pin has been looser than its name (#17647 review).
    """
    return [
        call.args[0]
        for call in _awaited_to_thread(node)
        if call.args and isinstance(call.args[0], ast.Attribute) and call.args[0].attr == name
    ]


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

        # Unconditional is not the same as per-cycle: a call placed before
        # `while self.running` satisfies every assertion above while pruning once at
        # startup. Raised in review, and the reason this checks containment.
        in_loop = {
            id(c)
            for node in ast.walk(run)
            if isinstance(node, ast.While)
            for c in _calls_named(node, "prune_event_buffer")
        }
        assert all(id(c) in in_loop for c in calls), (
            "a prune_event_buffer() call sits outside the heartbeat loop -- once at "
            "startup is not the per-cycle cap this claims"
        )

        # And it must precede the heartbeat. A total request timeout raises
        # `asyncio.TimeoutError`, which is not an `aiohttp.ClientError`, so it escapes
        # the heartbeat's handler into the loop's catch-all -- skipping any prune
        # placed after it, while the code-change endpoint keeps appending.
        heartbeats = _calls_named(run, "send_heartbeat")
        assert heartbeats, "run() no longer sends heartbeats -- re-point this pin"
        assert min(c.lineno for c in calls) < min(c.lineno for c in heartbeats), (
            "prune_event_buffer() runs after send_heartbeat() -- an exception from the "
            "heartbeat skips the cap for that cycle"
        )

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

        assert _offloaded(fn, "buffer_event"), (
            "the failure path either stopped buffering the heartbeat, or hands it to an "
            "unawaited to_thread -- a coroutine that never runs"
        )

    def test_both_of_buffer_events_async_callers_are_offloaded(self, rel: str) -> None:
        """`buffer_event` has two async paths; a fix that covers one is not a fix.

        The first push offloaded the heartbeat handler and left
        `handle_code_change` -- an aiohttp request handler -- calling
        `_process_code_change` bare, which reaches `buffer_event` and so sqlite.
        Found by review at the pushed head, not by the guard, because the chain
        runs through two sync frames.

        The hop belongs around the whole of `_process_code_change`: it writes a
        version file, clears a cache and appends a row, so wrapping each would buy
        nothing over wrapping once.
        """
        fn = _function(_tree(rel), "handle_code_change")
        assert (
            _calls_named(fn, "_process_code_change") == []
        ), "_process_code_change(...) is called inline in an async request handler"
        assert _offloaded(fn, "_process_code_change"), (
            "the code-change handler either stopped processing the change, or hands it to "
            "an unawaited to_thread -- a coroutine that never runs"
        )


class TestTheOffloadMatcherItself:
    """The matcher is the instrument; an untested instrument is not evidence.

    `_offloaded` was widened three times on #17647 -- awaited-only, then
    first-argument-only -- and each widening was applied to the production code
    without a test of the matcher, so reverting it passed the whole suite. These
    assert the matcher directly against the shapes it must separate.
    """

    @staticmethod
    def _fn(body: str):
        return ast.parse(f"async def h(self):\n    {body}\n").body[0]

    def test_the_target_must_be_the_first_argument(self) -> None:
        # `to_thread(func, *args)` calls only its first argument, so this awaits a
        # lambda and never touches buffer_event -- CodeRabbit's counter-example.
        fn = self._fn("await asyncio.to_thread(lambda unused: None, self.buffer_event)")
        assert _offloaded(fn, "buffer_event") == []

    def test_the_target_as_first_argument_is_accepted(self) -> None:
        fn = self._fn("await asyncio.to_thread(self.buffer_event, 'heartbeat', {})")
        assert len(_offloaded(fn, "buffer_event")) == 1

    def test_an_unawaited_to_thread_is_rejected(self) -> None:
        fn = self._fn("asyncio.to_thread(self.buffer_event, 'heartbeat', {})")
        assert _offloaded(fn, "buffer_event") == []
