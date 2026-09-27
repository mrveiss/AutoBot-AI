#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Source-liveness sweep isolation: the probe must cost no shared resource (#17545).

Split from `source_liveness_17545_test.py`, which reached MAX_LINES once these
landed. That file asserts what a probe *means*; this one asserts what a probe is
allowed to *hold* while it runs -- a separate question, and the one the #17615
review raised:

* the event loop -- `os.stat` on a dead NFS/SMB mount blocks uninterruptibly in
  the kernel, so an inline call from a coroutine stalls every other request on
  the worker. The probe runs in a bounded thread pool under a wall-clock timeout,
  and a timeout reads `unreadable`: *could not tell*, never absence.
* a database transaction -- the first version held one session across the row
  query, every probe and the commit, so one dead mount kept a transaction open
  for the kernel's timeout. Read, probe, write are three phases, and the tests
  here assert the *order*, which is the only thing that makes that real.
* a row's turn in the queue -- a locator SQL accepted and `locator_of` rejected
  used to be skipped without writing `source_checked_at`, so `nullsfirst` put it
  first again in every later sweep. Candidacy (`has_key`) and usability
  (`locator_of`) are separate questions with one rule each.

The session here is a fake, deliberately: what is under test is when work happens
relative to a transaction's lifetime, which a real database would obscure rather
than reveal.
"""

from __future__ import annotations

import ast
import asyncio
import threading
from pathlib import Path

import pytest

from knowledge import source_liveness
from knowledge.source_liveness import (
    LOCATOR_KEY,
    PROBE_ABSENT,
    PROBE_RESOLVED,
    PROBE_UNREADABLE,
    _sweep_query,
    probe_path_async,
    sweep_source_liveness,
)
from models.knowledge_fact import KnowledgeFact


class TestTheProbeNeverBlocksTheEventLoop:
    """#17615 review, Major: a stalled mount must not stall the process.

    `os.stat` on a dead NFS/SMB mount blocks in the kernel for as long as the
    mount's timeout allows -- uninterruptibly. Called inline from a coroutine that
    is what the whole event loop does, so every other request on the worker waits
    behind one unreachable share. The probe therefore runs in a bounded thread
    pool under a wall-clock timeout, and a timeout is reported `unreadable`:
    *could not tell*, never evidence of absence.
    """

    @pytest.fixture
    def present(self, tmp_path: Path) -> Path:
        """Written from a sync fixture, not from the coroutine: the repo's
        no-blocking-I/O-in-async guard (#7444) is right about the test too."""
        path = tmp_path / "a.pdf"
        path.write_text("x", encoding="utf-8")
        return path

    @pytest.mark.asyncio
    async def test_the_async_probe_agrees_with_the_sync_one(self, present: Path) -> None:
        assert await probe_path_async(str(present)) == PROBE_RESOLVED
        assert await probe_path_async(str(present.parent / "gone.pdf")) == PROBE_ABSENT
        assert await probe_path_async(None) == PROBE_UNREADABLE

    @pytest.mark.asyncio
    async def test_a_stalled_probe_times_out_as_unreadable(self, monkeypatch) -> None:
        """The dead-mount case, which no real filesystem can be asked for here."""
        release = threading.Event()

        def _hangs(path):
            release.wait(timeout=30)
            return PROBE_RESOLVED

        monkeypatch.setattr(source_liveness, "probe_path", _hangs)
        monkeypatch.setattr(source_liveness, "PROBE_TIMEOUT_SECONDS", 0.05)
        try:
            assert await probe_path_async("/mnt/dead/share/a.pdf") == PROBE_UNREADABLE
        finally:
            release.set()

    @pytest.mark.asyncio
    async def test_the_loop_keeps_running_while_a_probe_stalls(self, monkeypatch) -> None:
        """The property the timeout exists for: other coroutines still progress."""
        release = threading.Event()
        ticks = 0

        def _hangs(path):
            release.wait(timeout=30)
            return PROBE_RESOLVED

        async def _tick():
            nonlocal ticks
            for _ in range(5):
                await asyncio.sleep(0)
                ticks += 1

        monkeypatch.setattr(source_liveness, "probe_path", _hangs)
        monkeypatch.setattr(source_liveness, "PROBE_TIMEOUT_SECONDS", 0.05)
        try:
            outcome, _ = await asyncio.gather(probe_path_async("/mnt/dead/a.pdf"), _tick())
        finally:
            release.set()
        assert outcome == PROBE_UNREADABLE
        assert ticks == 5


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """Just enough session to observe WHEN work happens, not what SQL says."""

    def __init__(self, tracker, rows):
        self._tracker = tracker
        self._rows = rows
        self.committed = False

    async def __aenter__(self):
        self._tracker["open"] += 1
        self._tracker["sessions"] += 1
        return self

    async def __aexit__(self, *exc):
        self._tracker["open"] -= 1
        return False

    async def execute(self, query):
        return _FakeResult([(fact.id, fact.metadata_json) for fact in self._rows])

    async def get(self, model, fact_id):
        return next((fact for fact in self._rows if fact.id == fact_id), None)

    async def commit(self):
        self.committed = True


class TestTheSweepHoldsNoTransactionWhileProbing:
    """#17615 review: one session spanned the query, every probe and the commit.

    A page containing one dead mount held a database transaction open for the
    kernel's timeout. The sweep is three phases -- read, probe, write -- and these
    tests assert the *order*, which is the only thing that makes the fix real.
    """

    @staticmethod
    def _facts():
        return [
            KnowledgeFact(id="f1", content="c", metadata_json={LOCATOR_KEY: "/srv/a.pdf"}),
            KnowledgeFact(id="f2", content="c", metadata_json={LOCATOR_KEY: ""}),
            KnowledgeFact(id="f3", content="c", metadata_json={LOCATOR_KEY: 7}),
        ]

    def _install(self, monkeypatch, facts):
        tracker = {"open": 0, "sessions": 0, "probes_with_a_session_open": 0}
        sessions = []

        def _factory():
            session = _FakeSession(tracker, facts)
            sessions.append(session)
            return session

        monkeypatch.setattr(source_liveness, "get_async_session_factory", lambda: _factory)

        real_probe = source_liveness.probe_path

        def _probe(path):
            if tracker["open"]:
                tracker["probes_with_a_session_open"] += 1
            return real_probe(path)

        monkeypatch.setattr(source_liveness, "probe_path", _probe)
        return tracker, sessions

    @pytest.mark.asyncio
    async def test_no_probe_runs_while_a_session_is_open(self, monkeypatch) -> None:
        facts = self._facts()
        tracker, sessions = self._install(monkeypatch, facts)
        await sweep_source_liveness(limit=10)
        assert tracker["probes_with_a_session_open"] == 0
        assert tracker["sessions"] == 2  # read, then write -- never one spanning both
        assert sessions[-1].committed is True

    @pytest.mark.asyncio
    async def test_an_unusable_locator_is_recorded_rather_than_skipped(self, monkeypatch) -> None:
        """The starvation fix (#17615 review).

        The old loop `continue`d on a locator `locator_of` rejected, so the row
        kept `source_checked_at IS NULL`; with `nullsfirst` it sorted first in
        every later sweep, and a page of such rows made the sweep permanently
        re-read the same facts and probe nothing.
        """
        facts = self._facts()
        self._install(monkeypatch, facts)
        result = await sweep_source_liveness(limit=10)
        assert result["probed"] == len(facts)
        assert result["outcomes"][PROBE_UNREADABLE] == 2  # "" and 7
        assert all(fact.source_checked_at is not None for fact in facts)

    @pytest.mark.asyncio
    async def test_an_empty_page_opens_no_write_transaction(self, monkeypatch) -> None:
        tracker, _ = self._install(monkeypatch, [])
        result = await sweep_source_liveness(limit=10)
        assert result["probed"] == 0
        assert tracker["sessions"] == 1


class TestTheSweepQueryAsksOneQuestion:
    """Candidacy is `has_key`; usability is `locator_of`. Never both in SQL."""

    @staticmethod
    def _sql() -> str:
        from sqlalchemy.dialects import postgresql

        return str(_sweep_query(25).compile(dialect=postgresql.dialect()))

    def test_candidacy_is_key_presence_not_a_text_projection(self) -> None:
        sql = self._sql()
        assert "?" in sql  # JSONB key-presence
        assert "->>" not in sql  # no `.astext` opinion on what a locator is

    def test_a_witnessed_deletion_is_not_re_probed(self) -> None:
        assert "source_gone_at IS NULL" in self._sql()

    def test_the_least_recently_checked_come_first(self) -> None:
        sql = self._sql()
        assert "ORDER BY" in sql and "source_checked_at ASC NULLS FIRST" in sql

    def test_the_sweep_never_skips_a_candidate(self) -> None:
        """A `continue` in the probe loop is what starved the sweep. Source-level,
        because the starvation only shows up on the sweep *after* the one tested."""
        source = Path(__file__).with_name("source_liveness.py").read_text(encoding="utf-8")
        sweep = next(
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "sweep_source_liveness"
        )
        assert not [node for node in ast.walk(sweep) if isinstance(node, ast.Continue)]
