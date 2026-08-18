# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Escalation must be reachable for a node degraded on a non-staleness cause (#14465, defect 2).

Third attempt at the tracker-clearing mechanism. The first two both cleared
the remediation tracker on a POSITIVE observation of health -- a bare
`old_status != ONLINE -> ONLINE` transition in `update_node_heartbeat`, then a
`settings.unhealthy_threshold`-consecutive-beat dwell window gating that same
clear. Review measured both as fakeable: any observation that a flap can
satisfy before it degrades again is, by construction, a fact about the PAST
that a later failure does not retract. The dwell window's own break-even was
exactly `beats_per_flap >= unhealthy_threshold` -- three beats, 90 seconds of
agent life, the ordinary crash-loop shape -- and it doubled up an unrelated
setting (`SLM_UNHEALTHY_THRESHOLD`, "missed heartbeats before unhealthy") as
an escalation gate, so tightening detection loosened escalation.

`_forgive_if_expired` reads no heartbeat/streak signal, which closes that
specific failure mode: nothing here is fakeable by however a node's own
heartbeat behaves, at any beat count, because nothing here reads a beat.
**This is not, on its own, a general fix for escalation reachability.**
Review's next round found the actual dominant gate for a node whose agent
keeps heartbeating is five lines below in `_remediate_node`:

    success = restarted and await self._heartbeat_returned(node, now)
    … "count": … if not success else 0

Any single heartbeat landing within `REMEDIATION_HEARTBEAT_WAIT_S` of a
restart resets `count` to 0 through THAT path, on every attempt, regardless
of `_forgive_if_expired` -- because count never accumulates past 0/1 in the
first place. Measured: with `_heartbeat_returned` returning `True` (a node
that genuinely re-heartbeats after every restart -- the ordinary #14350/#14454
flapping shape), removing `_forgive_if_expired` entirely produces a
byte-identical result. What this PR delivers is escalation reachability for
the three shapes where `_heartbeat_returned` genuinely and repeatedly fails:
an ansible restart that cannot run, a restart that runs but never gets a
heartbeat accepted (#14350 at its narrowest -- verification fails on every
single attempt, not just once), and an outcome-commit failure. All three go
from 40 restarts/0 escalations on `origin/Dev_new_gui` to 3/1 here. Whether
and how to widen "recovered" to also cover a node that heartbeats but never
truly fixes itself is a posted, unresolved decision on #14465 (labelled
`needs-decision`) -- out of scope for this PR.

These tests drive the real `_remediate_node`/`_check_remediation_limits`/
`_forgive_if_expired`/`_heartbeat_returned`. The module is loaded from disk
for the same reason as its siblings: the package conftest stubs `services.*`,
and a plain import yields a MagicMock that would pass every assertion here
while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace
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


def test_the_expiry_floor_clears_the_cooldown_by_more_than_a_reconcile_tick():
    """Review: `min_v=REMEDIATION_COOLDOWN` alone let the floor itself BE the
    degenerate value -- every operator setting in {-1, 0, 1, 60, 299, 300}
    clamped to exactly 300, at which point forgive and cooldown fired at the
    identical elapsed time and forgive always won: count could never exceed 1
    no matter how many attempts failed. The floor must be strictly above
    `REMEDIATION_COOLDOWN` plus a reconcile-tick margin, structurally, not by
    the module's chosen default happening to clear it.
    """
    assert reconciler.REMEDIATION_TRACKER_EXPIRY_S > reconciler.REMEDIATION_COOLDOWN + 1, (
        "the expiry floor must clear the cooldown by more than a reconcile-tick margin, "
        "or forgive and cooldown fire at the same elapsed time and forgive always wins"
    )


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


def test_a_node_whose_restart_never_gets_a_heartbeat_accepted_reaches_max_attempts():
    """One of the three shapes this PR actually fixes -- an ansible restart
    that runs but never gets ONE heartbeat accepted on ANY attempt (the
    narrowest #14350 shape: verification fails every single time, not just
    once). `_heartbeat_returned` is stubbed to `False` to represent that
    outcome directly; the polling loop itself is covered separately by
    `reconciler_heartbeat_verification_test.py`. Across cycles, not one
    call's return value: count must climb monotonically to
    `MAX_REMEDIATION_ATTEMPTS` and `_create_max_attempts_event` must fire
    exactly once.
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


def test_escalation_survives_the_expiry_floor_at_its_worst_case_setting():
    """Structural claim above, exercised behaviourally: even forced down to
    its own computed floor -- the worst case any `AUTOBOT_REMEDIATION_
    TRACKER_EXPIRY_S` operator setting can clamp to -- the never-verifies
    scenario above must still escalate.
    """
    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _AsyncReturns(True)
    service._heartbeat_returned = _AsyncReturns(False)

    clock = _Clock(datetime.now(timezone.utc))
    reconciler.datetime = clock
    original_expiry = reconciler.REMEDIATION_TRACKER_EXPIRY_S
    reconciler.REMEDIATION_TRACKER_EXPIRY_S = reconciler.REMEDIATION_COOLDOWN + 61
    try:
        db = _FakeSession()
        node = _degraded_node()
        for _cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS + 2):
            asyncio.run(service._remediate_node(db, node))
            clock.advance(reconciler.REMEDIATION_COOLDOWN + 5)
    finally:
        reconciler.datetime = datetime
        reconciler.REMEDIATION_TRACKER_EXPIRY_S = original_expiry

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] >= reconciler.MAX_REMEDIATION_ATTEMPTS and tracker.get("exhausted"), (
        f"escalation failed even at the expiry floor -- got {tracker}"
    )


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


class _AlwaysFreshBeatSessions:
    """`db_service.session()` stand-in that `_heartbeat_returned` polls.

    Always answers with a beat one second after `_clock`'s CURRENT time --
    simulating a genuinely flapping node whose agent DOES land a heartbeat
    shortly after every restart (the actual #14350/#14454 shape), which is
    exactly what `_heartbeat_returned`'s own success semantics is designed to
    detect, and correctly counts as verified (#14344) on that mechanism's own
    terms. `_clock` is read live on every poll, not captured once, so it
    tracks whatever `restarted_at` each `_remediate_node` cycle computed.
    """

    def __init__(self, clock: _Clock):
        self._clock = clock
        self.reads = 0

    @asynccontextmanager
    async def session(self):
        yield SimpleNamespace(execute=self._execute)

    async def _execute(self, _query):
        self.reads += 1
        beat = self._clock.current + timedelta(seconds=1)
        return SimpleNamespace(scalar_one_or_none=lambda: SimpleNamespace(last_heartbeat=beat))


class _FakeQuery:
    """Stands in for the SQLAlchemy `select()` `_heartbeat_returned` builds.

    Ignored entirely by `_AlwaysFreshBeatSessions` -- see
    `reconciler_heartbeat_verification_test.py` for the same pattern and its
    rationale.
    """

    def where(self, *_args, **_kwargs) -> "_FakeQuery":
        return self


@contextmanager
def _real_heartbeat_verification_installed(clock: _Clock):
    """Install a fake `services.database.db_service` and shrink the poll
    timings so the REAL `_heartbeat_returned` runs fast and deterministically.
    """
    name = "services.database"
    created = name not in sys.modules
    if created:
        sys.modules[name] = ModuleType(name)
    db_module = sys.modules[name]
    original_db_service = getattr(db_module, "db_service", None)
    db_module.db_service = _AlwaysFreshBeatSessions(clock)

    prev_wait = reconciler.REMEDIATION_HEARTBEAT_WAIT_S
    prev_poll = reconciler.REMEDIATION_HEARTBEAT_POLL_S
    reconciler.REMEDIATION_HEARTBEAT_WAIT_S = 1
    reconciler.REMEDIATION_HEARTBEAT_POLL_S = 0

    prev_select = reconciler.select
    reconciler.select = lambda *_a, **_k: _FakeQuery()
    try:
        yield
    finally:
        reconciler.select = prev_select
        reconciler.REMEDIATION_HEARTBEAT_WAIT_S = prev_wait
        reconciler.REMEDIATION_HEARTBEAT_POLL_S = prev_poll
        if created:
            del sys.modules[name]
        else:
            db_module.db_service = original_db_service


def test_a_genuinely_flapping_node_with_verified_heartbeats_does_not_escalate():
    """The honest result, replacing an earlier test that only LOOKED like it
    modelled a flapping node: its fixture had no `last_heartbeat` and it
    stubbed `_heartbeat_returned` to a value no real flapping node produces
    (`False`, unconditionally) -- the round-1 flaw repeated, per review.

    Drives the REAL `_heartbeat_returned` against a node whose agent DOES
    land a heartbeat shortly after every restart. That resets `count` to 0
    via `_heartbeat_returned`'s own success path on every attempt, correctly
    on that mechanism's own terms -- `_forgive_if_expired` never gets a
    chance to matter, because count never accumulates past 1 in the first
    place. This is the gap the posted #14465 decision is about, not a defect
    in this PR: recorded here as a known, currently-unescalating shape rather
    than silently assumed fixed.
    """
    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _AsyncReturns(True)
    # _heartbeat_returned is the REAL function here -- not stubbed.

    clock = _Clock(datetime.now(timezone.utc))
    reconciler.datetime = clock
    try:
        with _real_heartbeat_verification_installed(clock):
            db = _FakeSession()
            node = _degraded_node()
            for _cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS + 5):
                asyncio.run(service._remediate_node(db, node))
                clock.advance(reconciler.REMEDIATION_COOLDOWN + 5)
    finally:
        reconciler.datetime = datetime

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] == 0, (
        f"expected the honest, currently-unescalating result (count stays 0 -- _heartbeat_returned "
        f"resets it every attempt), got count={tracker['count']}. If this changed, the #14465 "
        f"decision may have landed and this test needs updating, not silencing."
    )
    assert not tracker.get("exhausted"), "escalation is not reachable for this shape via any tracker-side mechanism"


class _HeartbeatSession:
    """Drives `update_node_heartbeat`: one scripted `Node` row, no-op writes.

    Used ONLY to prove ordinary heartbeat processing (the `/heartbeat` API
    path, unrelated to `_heartbeat_returned`'s remediation-side polling) has
    zero effect on the remediation tracker.
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


def test_ordinary_heartbeat_processing_never_touches_the_remediation_tracker():
    """`update_node_heartbeat` (the `/heartbeat` API path) is structurally
    decoupled from `self._remediation_tracker` -- no code path there reads or
    writes it. Drives 10 real, healthy `update_node_heartbeat` calls between
    two `_remediate_node` attempts and asserts the count is untouched. This is
    NOT the same claim as "a flapping node cannot defeat escalation" -- that
    depends on `_heartbeat_returned`'s own polling (see the tests above);
    this is the narrower, still-true claim that the heartbeat endpoint itself
    cannot reach into remediation state.
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

    assert service._remediation_tracker[node.node_id]["count"] == 1, (
        "ordinary heartbeat processing must never touch the remediation tracker"
    )


def test_a_non_exhausted_tracker_forgives_only_after_the_expiry_window():
    """`_forgive_if_expired` directly.

    A gap shorter than `REMEDIATION_TRACKER_EXPIRY_S` must not forgive. Only
    a gap that long does, and it can only arise from the reconciler
    genuinely not re-selecting this node as DEGRADED (so `_remediate_node`
    never ran) for that whole window.
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


def test_an_exhausted_node_broadcasts_on_every_subsequent_refusal():
    """Review: base's clear dropped `exhausted` whenever it fired, so a
    recovered node became remediable again -- rarely reachable per this
    issue's own root-cause finding, but a real path base had.
    `_forgive_if_expired` excludes `exhausted` trackers entirely (by design,
    see its docstring), so with no automatic path back the lockout must at
    least be visible: `_handle_max_attempts_refusal` broadcasts on every
    refusal after the first, not only the one DB-persisted event.
    """
    service = reconciler.ReconcilerService()
    node = _degraded_node()
    service._remediation_tracker[node.node_id] = {
        "count": reconciler.MAX_REMEDIATION_ATTEMPTS,
        "last_attempt": datetime.now(timezone.utc),
        "exhausted": True,
    }

    broadcasts: list[tuple] = []
    original_broadcast = reconciler.ReconcilerService._broadcast_remediation_event

    async def _spy_broadcast(self, node_id, event_type, success=None, message=None):
        broadcasts.append((node_id, event_type, success, message))
        await original_broadcast(self, node_id, event_type, success=success, message=message)

    service._broadcast_remediation_event = _spy_broadcast.__get__(service)

    events_created: list[dict] = []
    original_create_event = reconciler.ReconcilerService._create_max_attempts_event

    async def _spy_create_event(self, db, node_, tracker):
        events_created.append(dict(tracker))
        await original_create_event(self, db, node_, tracker)

    service._create_max_attempts_event = _spy_create_event.__get__(service)

    db = _FakeSession()
    for _ in range(3):
        asyncio.run(service._remediate_node(db, node))

    assert len(events_created) == 0, "an already-exhausted tracker must not create a second DB-persisted event"
    assert len(broadcasts) == 3, f"expected a broadcast on every one of 3 refusals, got {len(broadcasts)}"


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
    """One of the three shapes this PR actually fixes. Review's corrected
    principle: for a PACING record, over-recording is safe (it only delays a
    retry) and under-recording is unsafe (it unthrottles one). The ansible
    restart has already run by the time the outcome commit is attempted, so
    the in-memory tracker write must not be conditional on that commit
    succeeding -- otherwise a failed commit leaves `last_attempt` unset and
    the very next pass restarts with no cooldown at all, faster than the bug
    this issue reports.
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
