# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Escalation must be reachable for a node degraded on a non-staleness cause (#14465, defect 2).

`_attempt_remediation` selects DEGRADED nodes only. Before this fix,
`_clear_tracker_if_recovered` ran at the top of every `_remediate_node` call --
on EVERY reconcile pass for a selected node, not only on passes that perform an
actual restart -- and reset the attempt count to 0 whenever `node.last_heartbeat`
was newer than the tracker's `last_attempt` and still inside the staleness
window. A node degraded for a reason a `slm-agent` restart cannot fix, while
its own heartbeat cadence never lapses, reached that check with a current beat
on every pass and had its count wiped every pass -- it could never reach
`MAX_REMEDIATION_ATTEMPTS`.

Review of an earlier version of this fix caught a regression in its
replacement: clearing on a bare `old_status != ONLINE -> new_status == ONLINE`
transition inside `update_node_heartbeat` is satisfied by a SINGLE flapping
heartbeat (one healthy beat, then stale again, repeated) -- reproducing
#14454's exact defect through a different call site. A 12-cycle simulation
against the real functions showed the flapping node escalating under #14455
but NOT under that transition-only version.

The fix actually shipped here gates the clear on a **sustained** streak:
`update_node_heartbeat` only clears once a node has computed ONLINE for
`settings.unhealthy_threshold` consecutive heartbeats in a row (see
`_track_online_streak`), and the streak resets to zero on ANY non-ONLINE
observation -- including one `_check_node_health`'s own staleness sweep
assigns directly, via `_handle_degraded_node`/`_handle_offline_node`, entirely
outside `update_node_heartbeat`. A single flap can satisfy the transition; it
cannot satisfy a sustained streak. The clear itself was also changed from a
full delete to a partial reset that preserves `last_attempt`, so a node that
recovers and later degrades again for an unrelated reason still restarts no
faster than `REMEDIATION_COOLDOWN` -- a full delete left `_check_remediation_
limits` with no cooldown to pace against at all.

These tests drive the real `_remediate_node`/`update_node_heartbeat`/
`_handle_degraded_node` across multiple cycles with a controllable clock, and
assert the count reaches `MAX_REMEDIATION_ATTEMPTS` and `_create_max_attempts_
event` fires -- the behaviour across cycles, not a single call's return value.
The module is loaded from disk for the same reason as its siblings: the
package conftest stubs `services.*`, and a plain import yields a MagicMock
that would pass every assertion here while exercising nothing.
"""

from __future__ import annotations

import asyncio
import importlib.util
import inspect
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))


def _load_real_reconciler():
    spec = importlib.util.spec_from_file_location(
        "reconciler_under_recovery_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_recovery_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
    assert inspect.iscoroutinefunction(reconciler.ReconcilerService._remediate_node)
    assert inspect.isfunction(reconciler.ReconcilerService._track_online_streak)
    assert not hasattr(reconciler.ReconcilerService, "_clear_tracker_if_recovered"), (
        "the superseded per-tick clearing method is still present -- the new "
        "ONLINE-transition mechanism is meant to replace it, not sit beside it"
    )


@contextmanager
def _patched_settings(unhealthy_threshold: int = 3, heartbeat_interval: int = 30):
    """Give `reconciler.settings` real, comparable numbers for this module only.

    `config.settings` is a `MagicMock` under the root conftest's stubs, and
    `int >= MagicMock()` raises `TypeError` -- `_track_online_streak`'s dwell
    comparison needs a genuine int. Patches this loaded module's own `settings`
    name, not the shared `sys.modules["config"]` singleton other independently
    -loaded reconciler instances also read, and restores it afterward.
    """
    original = reconciler.settings
    reconciler.settings = SimpleNamespace(
        unhealthy_threshold=unhealthy_threshold, heartbeat_interval=heartbeat_interval
    )
    try:
        yield
    finally:
        reconciler.settings = original


class _Clock:
    """A controllable stand-in for `datetime` inside `services.reconciler`.

    `_remediate_node`/`_check_remediation_limits`/`_create_max_attempts_event`/
    `_update_node_metrics` call only `datetime.now(tz)`; nothing here
    constructs a `datetime` directly, so a bare `.now()` shim is enough to
    drive many cycles without sleeping in real time.
    """

    def __init__(self, start: datetime):
        self.current = start

    def now(self, _tz=None) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current = self.current + timedelta(seconds=seconds)


class _FakeSession:
    """`add`/`commit` no-ops -- everything `_remediate_node`/`_handle_degraded_node` writes through `db`."""

    def add(self, _obj):
        pass

    async def commit(self):
        pass


def _degraded_node() -> SimpleNamespace:
    return SimpleNamespace(
        node_id="node-14465",
        hostname="node-14465",
        ansible_target="node-14465",
        ip_address="10.0.0.5",
    )


def test_a_node_that_never_verifies_still_reaches_max_attempts_and_escalates():
    """The behaviour that matters: across cycles, not one call's return value.

    `_heartbeat_returned` never verifies -- the worst case for a node whose
    degrade cause an agent restart cannot fix. Nothing in the fixed code ever
    resets the tracker for a node that stays DEGRADED, so the count must climb
    monotonically to `MAX_REMEDIATION_ATTEMPTS` and `_create_max_attempts_event`
    must fire exactly once.
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
    assert len(max_attempts_events) == 1, (
        f"_create_max_attempts_event fired {len(max_attempts_events)} times -- "
        "expected exactly once, on the pass count first hits the limit"
    )


def test_a_node_that_verifies_every_time_never_accumulates_by_design():
    """The control case: an agent restart that genuinely restores heartbeating
    resets the count via `_heartbeat_returned`'s own success path (#14344) --
    unrelated to, and unaffected by, this fix. Included so the escalation test
    above is read as "the clearing bug is gone", not "remediation always fails
    now".
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


def test_recovery_clear_preserves_last_attempt_for_cooldown_pacing():
    """Deliberate behaviour, pinned against the opposite of an earlier version of this fix.

    An earlier version did a full delete (`reset_remediation_tracker`), which
    review flagged as WORSE than the bug this issue reports: with no
    `last_attempt` left at all, `_check_remediation_limits` sees no cooldown,
    so the very next degradation -- for any reason -- gets remediated on the
    next `reconcile_interval` instead of waiting `REMEDIATION_COOLDOWN`. This
    pins the fix: the count is forgiven, the pacing is not.
    """
    service = reconciler.ReconcilerService()
    last_attempt = datetime.now(timezone.utc)
    service._remediation_tracker["node-14465"] = {"count": 2, "last_attempt": last_attempt}

    service._clear_tracker_on_recovery("node-14465")

    tracker = service._remediation_tracker["node-14465"]
    assert tracker["count"] == 0, "recovery must forgive the attempt count"
    assert tracker["last_attempt"] == last_attempt, (
        "recovery deleted last_attempt -- the next degradation would be remediated with no cooldown at all"
    )


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


class _HeartbeatSession:
    """Drives `update_node_heartbeat`: one scripted `Node` row, no-op writes.

    The FIRST `execute()` is `_find_node_by_id_or_hostname`'s node lookup.
    Every later `execute()` -- `_sync_discovered_services`'s per-service upsert
    and stale-service lookups, only reached when `extra_data` carries a
    `discovered_services`/`services` payload -- must resolve to "nothing found"
    so those helpers take their create/no-op branches instead of mistaking the
    `Node` fixture for a `Service` row and overwriting its fields.
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


def _degraded_node_fixture() -> SimpleNamespace:
    return SimpleNamespace(
        node_id="node-14465",
        hostname="node-14465",
        status=reconciler.NodeStatus.DEGRADED.value,
        cpu_percent=0.0,
        memory_percent=0.0,
        disk_percent=0.0,
        last_heartbeat=datetime.now(timezone.utc),
        extra_data={},
        agent_version=None,
        os_info=None,
    )


def test_a_single_flapping_heartbeat_does_not_clear_the_tracker():
    """The regression review caught: one healthy beat is not a sustained recovery.

    `old_status != ONLINE -> new_status == ONLINE` is satisfied by this single
    heartbeat, exactly the way it was in the regressed version of this fix. The
    dwell gate (`unhealthy_threshold` consecutive ONLINE heartbeats) is not.
    """
    node = _degraded_node_fixture()
    service = reconciler.ReconcilerService()
    service._remediation_tracker[node.node_id] = {"count": 2, "last_attempt": datetime.now(timezone.utc)}

    with _patched_settings(unhealthy_threshold=3):
        asyncio.run(
            service.update_node_heartbeat(_HeartbeatSession(node), node.node_id, 0.0, 23.4, 18.1, extra_data={})
        )

    assert node.status == reconciler.NodeStatus.ONLINE.value, "sanity: this heartbeat must compute ONLINE"
    assert service._remediation_tracker[node.node_id]["count"] == 2, (
        "a single flapping heartbeat cleared the remediation tracker -- the #14454 defect, reinstated"
    )


def test_a_sustained_online_streak_clears_the_pending_remediation_tracker():
    """The two defects meeting: a node with exhausted remediation history that
    genuinely -- sustainedly -- recovers must leave BOTH the degraded state
    AND the remediation population able to track it again later (#14454's own
    acceptance criterion, unreachable before this issue's fix).
    """
    node = _degraded_node_fixture()
    service = reconciler.ReconcilerService()
    original_last_attempt = datetime.now(timezone.utc)
    service._remediation_tracker[node.node_id] = {
        "count": 3,
        "last_attempt": original_last_attempt,
        "exhausted": True,
    }

    with _patched_settings(unhealthy_threshold=3):
        for _ in range(3):
            asyncio.run(
                service.update_node_heartbeat(_HeartbeatSession(node), node.node_id, 0.0, 23.4, 18.1, extra_data={})
            )

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] == 0, "3 consecutive online heartbeats must clear the attempt count"
    assert "exhausted" not in tracker, "the exhausted flag must not survive a sustained recovery"
    assert tracker["last_attempt"] == original_last_attempt, "cooldown pacing must survive the clear"


def test_a_heartbeat_that_stays_degraded_does_not_clear_the_tracker():
    """The other half: a node whose heartbeat is healthy-LOOKING but whose
    status computation still resolves DEGRADED (a currently active crash-loop,
    in this fixture) must NOT have its progress toward escalation erased.
    """
    node = _degraded_node_fixture()
    service = reconciler.ReconcilerService()
    service._remediation_tracker[node.node_id] = {"count": 2, "last_attempt": datetime.now(timezone.utc)}

    still_crash_looping = {"discovered_services": [{"name": "autobot-vnc", "status": "crash-loop", "n_restarts": 1}]}
    asyncio.run(
        service.update_node_heartbeat(
            _HeartbeatSession(node), node.node_id, 0.0, 23.4, 18.1, extra_data=still_crash_looping
        )
    )

    assert node.status == reconciler.NodeStatus.DEGRADED.value
    assert service._remediation_tracker[node.node_id]["count"] == 2, (
        "a heartbeat that recomputes DEGRADED cleared the remediation tracker anyway"
    )


def test_a_flapping_node_reaches_max_attempts_and_escalates_with_cooldown_pacing():
    """Item 2, re-expressed against the mechanism that actually exists now.

    Not the deleted `_clear_tracker_if_recovered`'s test (it pinned a function
    this fix removes) -- this drives the real, currently-shipping call chain
    every flap cycle: `update_node_heartbeat` (one heartbeat lands, computes
    ONLINE), `_handle_degraded_node` (goes stale again before the reconciler's
    next look -- exactly `_check_node_health`'s own re-degrade path, and the
    thing that resets the streak `update_node_heartbeat` alone cannot), then
    `_remediate_node` (the reconciler's periodic, cooldown-gated attempt).

    Flaps land every `FLAP_INTERVAL` seconds -- far more often than
    `REMEDIATION_COOLDOWN` -- so this also asserts restart attempts stay paced
    to the cooldown rather than firing on every flap.
    """
    node = _degraded_node_fixture()
    node.ansible_target = node.node_id
    node.ip_address = "10.0.0.5"

    service = reconciler.ReconcilerService()
    service._restart_service_via_ansible = _CountingAsyncReturns(True)
    service._heartbeat_returned = _AsyncReturns(False)

    max_attempts_events: list[dict] = []
    original_create_event = reconciler.ReconcilerService._create_max_attempts_event

    async def _spy_create_max_attempts_event(self, db, node_, tracker):
        max_attempts_events.append(dict(tracker))
        await original_create_event(self, db, node_, tracker)

    service._create_max_attempts_event = _spy_create_max_attempts_event.__get__(service)

    db = _FakeSession()
    clock = _Clock(datetime.now(timezone.utc))
    reconciler.datetime = clock
    flap_interval = 100  # << REMEDIATION_COOLDOWN (300s) -- several flaps per cooldown window
    iterations = 40

    try:
        with _patched_settings(unhealthy_threshold=3):
            for _ in range(iterations):
                asyncio.run(
                    service.update_node_heartbeat(
                        _HeartbeatSession(node), node.node_id, 0.0, 10.0, 10.0, extra_data={}
                    )
                )
                assert node.status == reconciler.NodeStatus.ONLINE.value, "sanity: the flap beat must land healthy"

                asyncio.run(service._handle_degraded_node(db, node, old_status=reconciler.NodeStatus.ONLINE.value))
                assert node.status == reconciler.NodeStatus.DEGRADED.value, "sanity: the flap must go stale again"

                asyncio.run(service._remediate_node(db, node))
                clock.advance(flap_interval)
    finally:
        reconciler.datetime = datetime

    tracker = service._remediation_tracker[node.node_id]
    assert tracker["count"] >= reconciler.MAX_REMEDIATION_ATTEMPTS, (
        f"count is {tracker['count']} after {iterations} flap cycles -- escalation is unreachable"
    )
    assert tracker.get("exhausted") is True
    assert len(max_attempts_events) == 1, (
        f"_create_max_attempts_event fired {len(max_attempts_events)} times -- expected exactly once"
    )

    total_seconds = iterations * flap_interval
    max_paced_attempts = total_seconds // reconciler.REMEDIATION_COOLDOWN + 2
    restart_calls = service._restart_service_via_ansible.call_count
    assert restart_calls <= max_paced_attempts, (
        f"{restart_calls} restart attempts over {total_seconds}s of flapping "
        f"(1 every {flap_interval}s) -- cooldown is not pacing (expected <= {max_paced_attempts})"
    )
    assert restart_calls < iterations, "a restart on every single flap means the cooldown gate did nothing at all"
