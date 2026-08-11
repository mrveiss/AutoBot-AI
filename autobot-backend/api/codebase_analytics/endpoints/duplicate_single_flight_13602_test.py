# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The single-flight guard has to cover every caller, and outlast the orphan (#13602).

#12779 added a lock and a cancel token so an abandoned duplicate scan could not
accumulate. Two holes remained, and both let the accumulation back in:

1. `/report` submitted its own scan straight to the shared analytics executor
   with neither the lock nor the token. Same executor, same 8 workers — so a
   report queued a full walk regardless of one already running, and its orphan
   could not be told to stop.

2. The lock was released in a `finally` that ran on timeout, while the orphan
   thread was still going. The next poll therefore acquired it immediately and
   queued a second full scan on top of the first.

Both are invisible from outside: the endpoint returns, the log says the scan
timed out, and nothing reports that the work is still running or that scans are
stacking.
"""

from __future__ import annotations

import asyncio
import threading

import pytest

import api.codebase_analytics.endpoints.duplicates as dup_mod
import api.codebase_analytics.endpoints.report as report_mod


@pytest.fixture(autouse=True)
async def _single_flight_lock_is_free():
    dup_mod._duplicate_scan_lock.acquire()  # MUTATION: simulate a leaked lock
    """Wait for the module-global lock before and after every test.

    The lock is released by a done-callback on the executor future, so a test
    that abandons a scan releases it ASYNCHRONOUSLY — after its own body has
    returned. The next test then called `_run_standard_analysis` while the lock
    was still held, got the "already in flight" decline, and never reached the
    code it was written to exercise.

    On this machine the callback always won the race; on a loaded CI runner it
    did not, and `test_an_outer_cancel_still_signals_the_orphan` failed with
    "DID NOT RAISE CancelledError" — the task had already returned None.
    Ordering luck, not a code defect, but a test that depends on it is worthless.
    """
    await _wait_for_lock()
    yield
    await _wait_for_lock()


async def _wait_for_lock(timeout: float = 10.0) -> None:
    deadline = timeout / 0.05
    for _ in range(int(deadline)):
        if dup_mod._duplicate_scan_lock.acquire(blocking=False):
            dup_mod._duplicate_scan_lock.release()
            return
        await asyncio.sleep(0.05)
    raise AssertionError("the single-flight lock was never released — a previous test leaked it")


class TestReportUsesTheGuardedScan:
    @pytest.mark.asyncio
    async def test_report_does_not_queue_a_scan_while_one_is_in_flight(self, monkeypatch, tmp_path):
        """With the lock held, /report's duplicate analysis must decline rather
        than start a second walk on the shared executor."""
        submitted: list[str] = []

        def _record(*_args, **_kwargs):
            submitted.append("scan")
            raise AssertionError("a second scan was queued while one was in flight")

        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _record)

        assert dup_mod._duplicate_scan_lock.acquire(blocking=False)
        try:
            result = await report_mod._get_duplicate_analysis(project_root=tmp_path)
        finally:
            dup_mod._duplicate_scan_lock.release()

        assert result is None, "an in-flight scan yields no result rather than a duplicate scan"
        assert submitted == [], "the report path must go through the single-flight guard"

    @pytest.mark.asyncio
    async def test_report_returns_the_guarded_scans_result(self, monkeypatch, tmp_path):
        """Delegation must not silently drop a successful analysis.

        The stub carries the counters the success log reads: a bare object made
        this fail through the handler's `except Exception`, which is worth
        noting — a delegation that returned something unexpected would be
        reported as "duplicate analysis failed", not as a wiring bug.
        """

        class _Analysis:
            total_duplicates = 3
            high_similarity_count = 1
            medium_similarity_count = 1
            low_similarity_count = 1

        sentinel = _Analysis()

        async def _fake(project_root, min_similarity):
            return sentinel

        monkeypatch.setattr(report_mod, "_run_standard_analysis", _fake)

        assert await report_mod._get_duplicate_analysis(project_root=tmp_path) is sentinel


class TestTheLockOutlastsTheOrphan:
    @pytest.mark.asyncio
    async def test_lock_stays_held_until_the_abandoned_scan_exits(self, monkeypatch, tmp_path):
        """On timeout the thread survives. Releasing the lock then is what let
        abandoned scans stack — the very accumulation #12779 set out to stop."""
        release_thread = threading.Event()
        started = threading.Event()

        class _SlowDetector:
            def __init__(self, **kwargs):
                self._cancel_token = kwargs.get("cancel_token")

            def run_analysis(self):
                started.set()
                release_thread.wait(timeout=30)
                return "done"

        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _SlowDetector)
        monkeypatch.setattr(dup_mod.AnalyticsConfig, "DUPLICATE_DETECTION_TIMEOUT", 0.1)

        result = await dup_mod._run_standard_analysis(str(tmp_path), 0.5)
        assert result is None, "the scan should have timed out"
        assert started.is_set()

        # The orphan is still running: the guard must still be closed.
        acquired = dup_mod._duplicate_scan_lock.acquire(blocking=False)
        if acquired:
            dup_mod._duplicate_scan_lock.release()
        assert not acquired, "the lock was released while the abandoned scan was still running"

        # Once it exits, the guard reopens — otherwise this is a permanent block,
        # which would be a worse bug than the one being fixed.
        release_thread.set()
        for _ in range(100):
            if dup_mod._duplicate_scan_lock.acquire(blocking=False):
                dup_mod._duplicate_scan_lock.release()
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("the lock was never released after the abandoned scan finished")

    @pytest.mark.asyncio
    async def test_the_abandoned_scan_is_told_to_stop(self, monkeypatch, tmp_path):
        """Holding the lock is only bounded because the thread can be cancelled."""
        seen_token: dict[str, threading.Event | None] = {}
        proceed = threading.Event()

        class _SlowDetector:
            def __init__(self, **kwargs):
                seen_token["token"] = kwargs.get("cancel_token")

            def run_analysis(self):
                proceed.wait(timeout=30)
                return "done"

        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _SlowDetector)
        monkeypatch.setattr(dup_mod.AnalyticsConfig, "DUPLICATE_DETECTION_TIMEOUT", 0.1)

        await dup_mod._run_standard_analysis(str(tmp_path), 0.5)
        token = seen_token["token"]
        assert token is not None, "the scan must be given a cancel token"
        assert token.is_set(), "an abandoned scan must be signalled to stop"
        proceed.set()


class TestCancellationIsNotATimeout:
    """#14014 review: `CancelledError` is not `TimeoutError`, so it skipped the
    timeout handler entirely and fell through to `finally`.

    The lock was released with the token never set — and because the future is
    shielded, the orphan kept burning an executor thread with no way to stop it.
    That is the accumulation both #12779 and this work exist to close, reachable
    via uvicorn graceful shutdown and via any outer deadline tighter than the
    inner one. `/report` now wraps this call in its own deadline, so the two are
    nested and the margin between them is the only thing that was preventing it.
    """

    @pytest.mark.asyncio
    async def test_an_outer_cancel_still_signals_the_orphan(self, monkeypatch, tmp_path):
        seen: dict[str, threading.Event | None] = {}
        proceed = threading.Event()
        started = threading.Event()

        class _SlowDetector:
            def __init__(self, **kwargs):
                seen["token"] = kwargs.get("cancel_token")

            def run_analysis(self):
                started.set()
                proceed.wait(timeout=30)
                return "done"

        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _SlowDetector)

        task = asyncio.ensure_future(dup_mod._run_standard_analysis(str(tmp_path), 0.5))
        await asyncio.get_running_loop().run_in_executor(None, started.wait, 10)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert seen["token"] is not None
        assert seen["token"].is_set(), "a cancelled scan must be signalled to stop, exactly like a timed-out one"

        # And the guard must stay shut until the orphan actually exits.
        acquired = dup_mod._duplicate_scan_lock.acquire(blocking=False)
        if acquired:
            dup_mod._duplicate_scan_lock.release()
        assert not acquired, "the lock was released while the cancelled scan was still running"

        proceed.set()
        for _ in range(100):
            if dup_mod._duplicate_scan_lock.acquire(blocking=False):
                dup_mod._duplicate_scan_lock.release()
                break
            await asyncio.sleep(0.05)
        else:
            pytest.fail("the lock was never released after the cancelled scan finished")
