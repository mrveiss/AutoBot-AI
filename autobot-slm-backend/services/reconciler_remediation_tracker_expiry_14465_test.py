# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Escalation must be reachable for a node degraded on a non-staleness cause (#14465, defect 2).

Third attempt at this fix. The first two both cleared the remediation tracker
on a POSITIVE observation of health -- a bare `old_status != ONLINE -> ONLINE`
transition in `update_node_heartbeat`, then a `settings.unhealthy_threshold`
-consecutive-beat dwell window gating that same clear. Review measured both as
fakeable: any observation that a flap can satisfy before it degrades again is,
by construction, a fact about the PAST that a later failure does not retract.
The dwell window's own break-even was exactly `beats_per_flap >=
unhealthy_threshold` -- three beats, 90 seconds of agent life, the ordinary
crash-loop shape -- and it doubled up an unrelated setting
(`SLM_UNHEALTHY_THRESHOLD`, "missed heartbeats before unhealthy") as an
escalation gate, so tightening detection loosened escalation.

This fix reads no heartbeat signal at all. `_forgive_if_expired` resets a
non-exhausted tracker's count only once `REMEDIATION_TRACKER_EXPIRY_S` has
passed with NO new attempt recorded -- and `last_attempt` only advances when
`_remediate_node` actually runs an attempt, which happens every
`REMEDIATION_COOLDOWN` for as long as `_attempt_remediation` keeps
re-selecting the node as DEGRADED, regardless of how its heartbeat flaps in
between. A flap has nothing here to satisfy, at any beat count, because
nothing here reads a beat at all. `exhausted` trackers are excluded from
expiry entirely -- forgiving those on a timer would be a silent, unbounded
auto-retry, a scope change this issue does not ask for.

These tests drive the real `_remediate_node`/`_check_remediation_limits`/
`_forgive_if_expired`, plus `update_node_heartbeat` interleaved purely to
demonstrate it has NO effect on any of this. The module is loaded from disk
for the same reason as its siblings: the package conftest stubs `services.*`,
and a plain import yields a MagicMock that would pass every assertion here
while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    spec = importlib.util.spec_from_file_location(
        "reconciler_under_expiry_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_expiry_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
    assert inspect.iscoroutinefunction(reconciler.ReconcilerService._remediate_node)
    assert inspect.isfunction(reconciler.ReconcilerService._forgive_if_expired)
    for dead_name in ("_clear_tracker_if_recovered", "_clear_tracker_on_recovery", "_track_online_streak"):
        assert not hasattr(reconciler.ReconcilerService, dead_name), (
            f"{dead_name} is still present -- two superseded heartbeat-side clearing "
            "mechanisms should not sit alongside the time-based one"
        )
    assert not hasattr(
        reconciler.ReconcilerService(), "_online_streak"
    ), "the streak dict from the superseded dwell-window mechanism must not still be tracked"


class _Clock:
    """A controllable stand-in for `datetime` inside `services.reconciler`."""

    def __init__(self, start: datetime):
        self.current = start

    def now(self, _tz=None) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class _FakeSession:
    """`add`/`commit` no-ops -- everything `_remediate_node` writes through `db`."""

    def add(self, _obj):
        pass

    async def commit(self):
        pass


class _AsyncReturns:
    """A stand-in for an async instance method that always returns a fixed value.

    Assigned directly onto an instance (`service._x = _AsyncReturns(v)`), so
    calling `service._x(...)` invokes `__call__` with no implicit `self` --
    matching how the real bound methods are called from inside `_remediate_node`.
    """

    def __init__(self, value):
        self._value = value

    async def __call__(self, *_args, **_kwargs):
        return self._value


class _CountingAsyncReturns(_AsyncReturns):
    """Like `_AsyncReturns`, but counts invocations -- for asserting cooldown pacing."""

    def __init__(self, value):
        super().__init__(value)
        self.call_count = 0

    async def __call__(self, *args, **kwargs):
        self.call_count += 1
        return await super().__call__(*args, **kwargs)


def _degraded_node() -> SimpleNamespace:
    return SimpleNamespace(node_id="node-14465", hostname="node-14465", ansible_target="node-14465")


def test_a_flapping_node_that_never_verifies_still_reaches_max_attempts():
    """The behaviour that matters: across cycles, not one call's return value.

    `_heartbeat_returned` never verifies. Nothing in this mechanism ever reads
    a heartbeat to decide whether to clear the tracker, so the count must
    climb monotonically to `MAX_REMEDIATION_ATTEMPTS` and `_create_max_
    attempts_event` must fire exactly once, regardless of how the node's own
    heartbeat behaves in between attempts.
    """
    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _AsyncReturns(True)
    service._heartbeat_returned = _AsyncReturns(False)

    max_attempts_events: list[dict] = []
    original_create_event = reconciler.ReconcilerService._create_max_attempts_event

    async def _spy_create_max_attempts_event(self, db, node, tracker):
        max_attempts_events.append(dict(tracker))
        await original_create_event(self, db, node, tracker)

    service._create_max_attempts_event = _spy_create_max_attempts_event.__get__(service)

    clock = _Clock(datetime.now(timezone.utc))
    reconciler.datetime = clock
    try:
        db = _FakeSession()
        node = _degraded_node()

        for _cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS + 2):
            asyncio.run(service._remediate_node(db, node))
            clock.advance(reconciler.REMEDIATION_COOLDOWN + 5)
    finally:
        reconciler.datetime = datetime

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] >= reconciler.MAX_REMEDIATION_ATTEMPTS, (
        f"count is {tracker['count']} after "
        f"{reconciler.MAX_REMEDIATION_ATTEMPTS + 2} cycles -- escalation is unreachable (#14465)"
    )
    assert tracker.get("exhausted") is True
    assert (
        len(max_attempts_events) == 1
    ), f"_create_max_attempts_event fired {len(max_attempts_events)} times -- expected exactly once"


def test_a_node_that_verifies_every_time_never_accumulates_by_design():
    """The control case: an agent restart that genuinely restores heartbeating
    resets the count via `_heartbeat_returned`'s own success path (#14344) --
    unrelated to, and unaffected by, this fix.
    """
    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _AsyncReturns(True)
    service._heartbeat_returned = _AsyncReturns(True)

    clock = _Clock(datetime.now(timezone.utc))
    reconciler.datetime = clock
    try:
        db = _FakeSession()
        node = _degraded_node()

        for _cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS + 2):
            asyncio.run(service._remediate_node(db, node))
            clock.advance(reconciler.REMEDIATION_COOLDOWN + 5)
    finally:
        reconciler.datetime = datetime

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] == 0, "a verified-successful restart must reset the count, not accumulate it"
    assert not tracker.get("exhausted")


class _HeartbeatSession:
    """Drives `update_node_heartbeat`: one scripted `Node` row, no-op writes.

    Used ONLY to prove heartbeats -- however many, however "healthy" -- have
    zero effect on the remediation tracker under the new mechanism.
    """

    def __init__(self, node):
        self._node = node
        self._reads = 0

    async def execute(self, _query):
        self._reads += 1
        if self._reads == 1:
            return SimpleNamespace(scalar_one_or_none=lambda: self._node)
        return SimpleNamespace(scalar_one_or_none=lambda: None, scalars=lambda: SimpleNamespace(all=lambda: []))

    def add(self, _obj):
        pass

    async def commit(self):
        pass

    async def refresh(self, _obj):
        pass


def test_many_healthy_heartbeats_between_attempts_never_touch_the_tracker():
    """The regression review caught, closed structurally rather than raised.

    Drives 10 real, healthy `update_node_heartbeat` calls -- the exact shape
    that satisfied both the transition-only clear (1 beat) and the
    dwell-window clear (>= unhealthy_threshold beats) -- between two
    `_remediate_node` attempts, and asserts the count is untouched by any of
    them. This mechanism has no code path that even reads `node.status` or
    `node.last_heartbeat` when deciding whether to clear, so no beat count
    can matter.
    """
    node = SimpleNamespace(
        node_id="node-14465",
        hostname="node-14465",
        ansible_target="node-14465",
        status=reconciler.NodeStatus.DEGRADED.value,
        cpu_percent=0.0,
        memory_percent=0.0,
        disk_percent=0.0,
        last_heartbeat=datetime.now(timezone.utc),
        extra_data={},
        agent_version=None,
        os_info=None,
    )
    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _AsyncReturns(True)
    service._heartbeat_returned = _AsyncReturns(False)
    remediation_db = _FakeSession()

    asyncio.run(service._remediate_node(remediation_db, node))
    assert service._remediation_tracker[node.node_id]["count"] == 1

    for _ in range(10):
        asyncio.run(
            service.update_node_heartbeat(_HeartbeatSession(node), node.node_id, 0.0, 10.0, 10.0, extra_data={})
        )

    assert (
        service._remediation_tracker[node.node_id]["count"] == 1
    ), "healthy heartbeats between attempts must never clear or otherwise touch the remediation tracker"


def test_a_non_exhausted_tracker_forgives_only_after_the_expiry_window():
    """`_forgive_if_expired` directly: the actual recovery mechanism now.

    A gap shorter than `REMEDIATION_TRACKER_EXPIRY_S` -- however it arose,
    including a flap -- must not forgive. Only a gap that long does, and it
    can only arise from the reconciler genuinely not re-selecting this node
    as DEGRADED (so `_remediate_node` never ran) for that whole window.
    """
    service = reconciler.ReconcilerService()
    last_attempt = datetime.now(timezone.utc)

    service._remediation_tracker["node-14465"] = {"count": 2, "last_attempt": last_attempt}
    still_short = last_attempt + timedelta(seconds=reconciler.REMEDIATION_TRACKER_EXPIRY_S - 5)
    tracker = service._forgive_if_expired("node-14465", service._remediation_tracker["node-14465"], still_short)
    assert tracker["count"] == 2, "a gap just under the expiry window must not forgive"

    long_gap = last_attempt + timedelta(seconds=reconciler.REMEDIATION_TRACKER_EXPIRY_S + 5)
    tracker = service._forgive_if_expired("node-14465", service._remediation_tracker["node-14465"], long_gap)
    assert tracker["count"] == 0, "a gap past the expiry window must forgive a non-exhausted tracker"
    assert tracker["last_attempt"] == last_attempt, "the forgiven tracker must still preserve cooldown pacing"


def test_an_exhausted_tracker_never_auto_expires():
    """Exhaustion means human intervention was required -- not a timer.

    Auto-forgiving an `exhausted` tracker on elapsed time alone would be a
    silent, unbounded auto-retry outside this issue's scope.
    """
    service = reconciler.ReconcilerService()
    last_attempt = datetime.now(timezone.utc)
    service._remediation_tracker["node-14465"] = {"count": 3, "last_attempt": last_attempt, "exhausted": True}

    far_future = last_attempt + timedelta(seconds=reconciler.REMEDIATION_TRACKER_EXPIRY_S * 100)
    tracker = service._forgive_if_expired("node-14465", service._remediation_tracker["node-14465"], far_future)

    assert (
        tracker["count"] == 3 and tracker.get("exhausted") is True
    ), "an exhausted tracker must stay exhausted no matter how much time passes"


def test_cooldown_still_paces_attempts_even_with_frequent_reconcile_ticks():
    """`_remediate_node` may be invoked far more often than `REMEDIATION_COOLDOWN`
    allows an attempt to actually fire (every reconcile tick, not every
    cooldown period). Restart attempts must stay paced to the cooldown.
    """
    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _CountingAsyncReturns(True)
    service._heartbeat_returned = _AsyncReturns(False)

    clock = _Clock(datetime.now(timezone.utc))
    reconciler.datetime = clock
    tick = 60  # a reconcile_interval-scale tick, far shorter than the 300s cooldown
    ticks = 40

    try:
        db = _FakeSession()
        node = _degraded_node()
        for _ in range(ticks):
            asyncio.run(service._remediate_node(db, node))
            clock.advance(tick)
    finally:
        reconciler.datetime = datetime

    total_seconds = ticks * tick
    max_paced_attempts = total_seconds // reconciler.REMEDIATION_COOLDOWN + 2
    restart_calls = service._restart_service_via_ansible.call_count
    assert restart_calls <= max_paced_attempts, (
        f"{restart_calls} restart attempts over {total_seconds}s of {tick}s-spaced ticks -- "
        f"cooldown is not pacing (expected <= {max_paced_attempts})"
    )
    assert restart_calls < ticks, "a restart on every single tick means the cooldown gate did nothing at all"


class _FailingResultCommitSession:
    """`add` is a no-op; the SECOND `commit()` (the outcome event's) raises.

    The FIRST commit is the REMEDIATION_STARTED event, which must succeed for
    the attempt to even begin.
    """

    def __init__(self):
        self._commits = 0

    def add(self, _obj):
        pass

    async def commit(self):
        self._commits += 1
        if self._commits == 2:
            raise RuntimeError("simulated DB commit failure")


def test_the_tracker_write_survives_a_failed_result_commit():
    """Review's corrected principle: for a PACING record, over-recording is
    safe (it only delays a retry) and under-recording is unsafe (it
    unthrottles one). The ansible restart has already run by the time the
    outcome commit is attempted, so the in-memory tracker write must not be
    conditional on that commit succeeding -- otherwise a failed commit leaves
    `last_attempt` unset and the very next pass restarts with no cooldown at
    all, faster than the bug this issue reports.
    """
    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _AsyncReturns(True)
    service._heartbeat_returned = _AsyncReturns(False)
    db = _FailingResultCommitSession()
    node = _degraded_node()

    raised = False
    try:
        asyncio.run(service._remediate_node(db, node))
    except RuntimeError:
        raised = True

    assert raised, "sanity: the simulated commit failure must actually propagate"
    tracker = service._remediation_tracker.get(node.node_id)
    assert tracker is not None and tracker["count"] == 1, (
        "the tracker write must happen before the result commit -- a failed commit must not leave "
        "the attempt unrecorded, or the next pass has no cooldown to pace against at all"
    )
