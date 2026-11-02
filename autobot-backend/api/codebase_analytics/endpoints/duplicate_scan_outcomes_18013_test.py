# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A duplicate scan that produced no analysis says WHICH reason (#18013, #18067).

`_run_duplicate_analysis` signalled "lock held" and "deadline expired" with the
same `None`, and the caller reported the timeout reason for both: a 0.2 s
response claiming "timed out after 120s", with advice that cannot help a caller
who is merely queued behind a running scan.

The assertions are on the observable a caller sees -- the payload text and the
raised type -- not on the presence of a branch.
"""

from __future__ import annotations

import threading
from pathlib import Path

import pytest

from api.codebase_analytics.endpoints import duplicates as dup_mod
from api.codebase_analytics.endpoints.scan_responses import (
    ScanBusy,
    ScanTimedOut,
    build_busy_response,
    build_timeout_response,
    response_for,
)
from autobot_shared.eventually import eventually


class _BlockingDetector:
    """A scan that runs until told to stop: the orphan that never exits on its own."""

    release = threading.Event()

    def __init__(self, **kwargs):
        self._cancel_token = kwargs.get("cancel_token")

    def run_analysis(self):
        self.release.wait(timeout=30)
        return "done"


@pytest.fixture(autouse=True)
def _fresh_guard(monkeypatch):
    """Own lock and holder per test; a leaked one must not decline the next test."""
    monkeypatch.setattr(dup_mod, "_duplicate_scan_lock", threading.Lock())
    monkeypatch.setattr(dup_mod, "_scan_holder", None)
    _BlockingDetector.release = threading.Event()
    yield
    _BlockingDetector.release.set()


class _Clock:
    """A hand-wound monotonic clock, so a lease expires by decision, not by waiting."""

    def __init__(self) -> None:
        self.now = 1000.0

    def monotonic(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(dup_mod, "time", fake)
    return fake


class TestBusyIsNotATimeout:
    @pytest.mark.asyncio
    async def test_a_held_lock_raises_busy_with_the_holders_age(self):
        dup_mod._take_scan_lock()
        with pytest.raises(ScanBusy) as caught:
            await dup_mod._run_standard_analysis("/nonexistent", 0.5)
        assert caught.value.elapsed_seconds is not None and caught.value.elapsed_seconds >= 0

    def test_the_busy_payload_never_claims_a_deadline_that_did_not_elapse(self):
        payload = build_busy_response(7.0)
        assert payload["status"] == "busy" and payload["storage_type"] == "in_flight"
        assert "timed out" not in payload["message"], payload
        assert "Retry" in payload["message"] and "for 7s" in payload["message"]

    def test_the_busy_payload_does_not_advise_a_threshold_that_cannot_help(self):
        assert "higher min_similarity" not in build_busy_response(None)["message"]

    @pytest.mark.asyncio
    async def test_an_instant_response_never_carries_a_timed_out_message(self, monkeypatch):
        """The reported symptom: 0.2 s, "timed out after 120.0s"."""

        async def _root(*_a, **_k):
            return Path("/nonexistent")

        monkeypatch.setattr(dup_mod, "resolve_scan_root", _root)
        dup_mod._take_scan_lock()
        response = await dup_mod.get_duplicate_code(
            refresh=True, min_similarity=0.5, use_semantic=False, source_id=None
        )
        body = response.body.decode("utf-8")
        assert '"status":"busy"' in body.replace(" ", "")
        assert "timed out" not in body


class TestTimeoutNamesTheDeadlineThatElapsed:
    @pytest.mark.asyncio
    async def test_the_payload_reports_the_deadline_actually_used(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _BlockingDetector)
        monkeypatch.setattr(dup_mod.AnalyticsConfig, "DUPLICATE_DETECTION_TIMEOUT", 0.1)
        with pytest.raises(ScanTimedOut) as caught:
            await dup_mod._run_standard_analysis(str(tmp_path), 0.5)
        assert caught.value.deadline_seconds == 0.1
        assert "timed out after 0.1s" in response_for(caught.value)["message"]
        assert response_for(caught.value)["storage_type"] == "timeout"

    def test_busy_and_timeout_are_different_payloads(self):
        assert build_busy_response(1.0)["status"] != build_timeout_response(120.0)["status"]


class TestAnOrphanThatNeverExitsCannotHoldTheLockForever:
    """#18013 AC4: hold the lock, let the owner die WITHOUT the callback firing,
    and the next call still acquires."""

    @pytest.mark.asyncio
    async def test_the_lease_expires_and_the_next_call_acquires(self, monkeypatch, tmp_path, clock):
        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _BlockingDetector)
        monkeypatch.setattr(dup_mod.AnalyticsConfig, "DUPLICATE_DETECTION_TIMEOUT", 0.05)
        monkeypatch.setattr(dup_mod, "ORPHAN_LEASE_SECONDS", 20.0)
        with pytest.raises(ScanTimedOut):
            await dup_mod._run_standard_analysis(str(tmp_path), 0.5)

        # Inside the lease the orphan still owns the lock: that is the #13602 guarantee.
        with pytest.raises(ScanBusy):
            await dup_mod._run_standard_analysis(str(tmp_path), 0.5)

        clock.advance(30.0)  # past the lease; the thread is still blocked, its done-callback has NOT fired
        assert not _BlockingDetector.release.is_set()
        lock = dup_mod._take_scan_lock()  # reclaimed rather than ScanBusy forever
        assert lock is dup_mod._duplicate_scan_lock and lock.locked()

    @pytest.mark.asyncio
    async def test_a_late_orphan_cannot_release_the_lock_a_newer_scan_owns(self, monkeypatch, tmp_path, clock):
        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _BlockingDetector)
        monkeypatch.setattr(dup_mod.AnalyticsConfig, "DUPLICATE_DETECTION_TIMEOUT", 0.05)
        monkeypatch.setattr(dup_mod, "ORPHAN_LEASE_SECONDS", 10.0)
        orphan_lock = dup_mod._duplicate_scan_lock
        with pytest.raises(ScanTimedOut):
            await dup_mod._run_standard_analysis(str(tmp_path), 0.5)
        clock.advance(20.0)
        newer = dup_mod._take_scan_lock()
        _BlockingDetector.release.set()  # the old orphan finally exits and fires its callback
        await eventually(lambda: not orphan_lock.locked())  # the callback ran: it released ITS lock
        assert newer.locked(), "the late callback released a lock it never owned"


class TestTheBackgroundPathIsNotCappedByTheRequestDeadline:
    @pytest.mark.asyncio
    async def test_a_scan_slower_than_the_request_deadline_completes_in_the_background(self, monkeypatch, tmp_path):
        class _Slow:
            def __init__(self, **_kwargs):
                pass

            def run_analysis(self):
                threading.Event().wait(0.3)
                return "analysis"

        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _Slow)
        monkeypatch.setattr(dup_mod.AnalyticsConfig, "DUPLICATE_DETECTION_TIMEOUT", 0.05)
        request_lock = dup_mod._duplicate_scan_lock
        with pytest.raises(ScanTimedOut):
            await dup_mod._run_standard_analysis(str(tmp_path), 0.5)
        await eventually(lambda: not request_lock.locked())  # the request-path orphan released its lock
        assert await dup_mod._run_standard_analysis(str(tmp_path), 0.5, background=True) == "analysis"

    @pytest.mark.asyncio
    async def test_the_background_bound_still_exists_and_raises(self, monkeypatch, tmp_path):
        monkeypatch.setattr(dup_mod, "DuplicateCodeDetector", _BlockingDetector)
        monkeypatch.setattr(dup_mod, "BACKGROUND_SCAN_TIMEOUT_SECONDS", 0.05)
        with pytest.raises(ScanTimedOut) as caught:
            await dup_mod._run_standard_analysis(str(tmp_path), 0.5, background=True)
        assert caught.value.deadline_seconds == 0.05
