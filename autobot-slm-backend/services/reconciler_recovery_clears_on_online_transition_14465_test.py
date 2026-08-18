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
window.

Two node shapes reach that check with a heartbeat satisfying both conditions:

  1. A node genuinely recovering. It never actually arrives here: any heartbeat
     flips it out of DEGRADED in `update_node_heartbeat`, so it stops matching
     `_attempt_remediation`'s query before this function runs at all -- the
     check existed to protect a case it structurally could never see.
  2. A node degraded for a reason a `slm-agent` restart cannot fix (resource
     pressure, or -- before defect 1's fix -- the permanently-mis-scored crash
     loop from `reconciler_status_ignores_lifetime_restarts_14465_test.py`)
     while its OWN heartbeat cadence never lapses. Its `last_heartbeat` is
     current on every single reconcile tick regardless of whether that tick's
     remediation attempt succeeded, so its count was wiped every ~`reconcile_
     interval` seconds -- independently of whatever `_heartbeat_returned`
     decided about that specific attempt. Any attempt that DID fail
     verification had its increment erased before the next attempt could ever
     compound failures toward `MAX_REMEDIATION_ATTEMPTS`.

The fix (owner's own diagnosis on the issue): clear on the ONLINE transition in
`update_node_heartbeat`, which is reachable for shape 1 for the first time and
simply never fires for shape 2, since that node never stops being DEGRADED.

These tests drive the real `_remediate_node` across multiple cycles with a
controllable clock and a `_heartbeat_returned` that never verifies (shape 2's
worst case: no attempt is ever counted a success), and assert the count reaches
`MAX_REMEDIATION_ATTEMPTS` and `_create_max_attempts_event` fires -- the
behaviour across cycles, not a single call's return value. The module is loaded
from disk for the same reason as its siblings: the package conftest stubs
`services.*`, and a plain import yields a MagicMock that would pass every
assertion here while exercising nothing.
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
    assert not hasattr(reconciler.ReconcilerService, "_clear_tracker_if_recovered"), (
        "the superseded per-tick clearing method is still present -- the new "
        "ONLINE-transition mechanism is meant to replace it, not sit beside it"
    )


class _Clock:
    """A controllable stand-in for `datetime` inside `services.reconciler`.

    `_remediate_node`/`_check_remediation_limits`/`_create_max_attempts_event`
    call only `datetime.now(tz)`; nothing here constructs a `datetime` directly,
    so a bare `.now()` shim is enough to drive multiple remediation cycles
    without sleeping in real time for `REMEDIATION_COOLDOWN` seconds each pass.
    """

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


def _degraded_node() -> SimpleNamespace:
    return SimpleNamespace(node_id="node-14465", hostname="node-14465", ansible_target="node-14465")


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


def test_recovery_clear_is_a_full_reset_not_a_cooldown_preserving_one():
    """Deliberate behaviour change from the superseded `_clear_tracker_if_recovered`.

    The old function kept `last_attempt` on reset so `REMEDIATION_COOLDOWN` kept
    pacing the SAME degraded episode. This fix clears the whole entry: recovery
    to ONLINE ends that episode, so a future degradation -- for any reason -- is
    a new one and gets a fresh cooldown, not one inherited from an episode that
    is now resolved.
    """
    service = reconciler.ReconcilerService()
    service._remediation_tracker["node-14465"] = {"count": 2, "last_attempt": datetime.now(timezone.utc)}

    service._clear_tracker_on_recovery("node-14465")

    assert "node-14465" not in service._remediation_tracker, "recovery must delete the entry, not merely zero it"


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


def test_online_transition_clears_a_pending_remediation_tracker():
    """The two defects meeting: a node with exhausted remediation history that
    genuinely recovers must leave BOTH the degraded state AND the remediation
    population able to track it again later (#14454's own acceptance
    criterion, unreachable before this fix -- see the module docstring).
    """
    node = SimpleNamespace(
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
    service = reconciler.ReconcilerService()
    service._remediation_tracker[node.node_id] = {
        "count": 3,
        "last_attempt": datetime.now(timezone.utc),
        "exhausted": True,
    }

    asyncio.run(service.update_node_heartbeat(_HeartbeatSession(node), node.node_id, 0.0, 23.4, 18.1, extra_data={}))

    assert (
        node.node_id not in service._remediation_tracker
    ), "a node observed transitioning to online must have its remediation history cleared"


def test_a_heartbeat_that_stays_degraded_does_not_clear_the_tracker():
    """The other half: a node whose heartbeat is healthy-LOOKING but whose
    status computation still resolves DEGRADED (a currently active crash-loop,
    in this fixture) must NOT have its progress toward escalation erased.
    """
    node = SimpleNamespace(
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
    service = reconciler.ReconcilerService()
    service._remediation_tracker[node.node_id] = {"count": 2, "last_attempt": datetime.now(timezone.utc)}

    still_crash_looping = {"discovered_services": [{"name": "autobot-vnc", "status": "crash-loop", "n_restarts": 1}]}
    asyncio.run(
        service.update_node_heartbeat(
            _HeartbeatSession(node), node.node_id, 0.0, 23.4, 18.1, extra_data=still_crash_looping
        )
    )

    assert node.status == reconciler.NodeStatus.DEGRADED.value
    assert (
        service._remediation_tracker[node.node_id]["count"] == 2
    ), "a heartbeat that recomputes DEGRADED cleared the remediation tracker anyway"
