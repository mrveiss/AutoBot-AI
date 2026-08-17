# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A flapping node must still reach escalation (#14454).

`_clear_tracker_if_recovered` was added late in #14344 to stop a node being
locked out of remediation forever after recovering by a route the reconciler
never observes. It shipped without a test, and it was too permissive: any
heartbeat newer than the last attempt cleared the tracker outright.

The structural point is that "newer than the last attempt" cannot mean recovery
here. `_attempt_remediation` only reaches DEGRADED nodes, and any heartbeat
flips a node out of DEGRADED -- so a genuinely recovered node never arrives at
this function, it stops matching the query. The node that *does* arrive with a
newer beat is one that flapped: one heartbeat landed, then it went stale again
and was re-degraded.

That is the #14350 agent exactly -- restart, one heartbeat, 401, silence,
repeat. Each cycle reset `count` to 0, so MAX_REMEDIATION_ATTEMPTS was never
reached and `_create_max_attempts_event` never fired. The #14344 defect
("not a loop that gives up -- one that cannot") rebuilt inside its own fix.

These tests execute the real method. The module is loaded from disk because the
package conftest stubs `services.*`, and a plain import yields a MagicMock that
satisfies every structural check while being nothing at all.
"""

from __future__ import annotations

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
        "reconciler_under_flap_test", _SLM_ROOT / "services" / "reconciler.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["reconciler_under_flap_test"] = module
    spec.loader.exec_module(module)
    return module


reconciler = _load_real_reconciler()

_HEARTBEAT_TIMEOUT_S = 90


def _service(tracker):
    """A stand-in carrying only what `_clear_tracker_if_recovered` reads."""
    return SimpleNamespace(_remediation_tracker=tracker, _heartbeat_timeout=_HEARTBEAT_TIMEOUT_S)


def _clear(beat_offset_s, last_attempt_offset_s, count=1):
    """Run the real method for a node whose beat/attempt sit at given offsets from now.

    Offsets are seconds in the past. Returns the tracker afterwards, or None if
    the entry was removed entirely.
    """
    now = datetime.now(timezone.utc)
    node_id = "node-under-test"
    tracker = {node_id: {"count": count, "last_attempt": now - timedelta(seconds=last_attempt_offset_s)}}
    node = SimpleNamespace(node_id=node_id, last_heartbeat=now - timedelta(seconds=beat_offset_s))

    reconciler.ReconcilerService._clear_tracker_if_recovered(_service(tracker), node)
    return tracker.get(node_id)


def test_the_real_module_was_loaded_not_a_stub():
    """`hasattr`/`callable` are true of any MagicMock and cannot tell the two apart."""
    assert not isinstance(reconciler.ReconcilerService, MagicMock)
    assert inspect.isfunction(reconciler.ReconcilerService._clear_tracker_if_recovered)


def test_a_stale_flap_heartbeat_does_not_clear_the_counter():
    """The #14454 regression.

    The beat is newer than the last attempt -- so the old condition cleared --
    but it is already older than the staleness cutoff, which is why the node is
    sitting in the degraded set at all. Counting that as recovery is what let a
    flapping node reset forever.
    """
    tracker = _clear(beat_offset_s=_HEARTBEAT_TIMEOUT_S + 60, last_attempt_offset_s=_HEARTBEAT_TIMEOUT_S + 120)

    assert tracker is not None, "the tracker was removed on a stale heartbeat"
    assert tracker["count"] == 1, (
        "a stale flap heartbeat reset the attempt counter — the node can never reach "
        "MAX_REMEDIATION_ATTEMPTS and never escalates (#14454)"
    )


def test_a_flapping_node_still_reaches_max_attempts():
    """The behaviour that matters, across cycles rather than in one call.

    Each cycle the agent restarts, lands one heartbeat, is rejected, and goes
    stale. If clearing fires on that, `count` oscillates 1, 0, 1, 0 and the
    escalation event is unreachable.
    """
    node_id = "node-under-test"
    tracker: dict = {}

    for cycle in range(reconciler.MAX_REMEDIATION_ATTEMPTS):
        now = datetime.now(timezone.utc)
        attempt_at = now - timedelta(seconds=_HEARTBEAT_TIMEOUT_S + 120)
        # one beat, after the attempt but already stale by the time we look
        node = SimpleNamespace(node_id=node_id, last_heartbeat=now - timedelta(seconds=_HEARTBEAT_TIMEOUT_S + 30))
        previous = tracker.get(node_id, {"count": 0})
        tracker[node_id] = {"count": previous["count"], "last_attempt": attempt_at}

        reconciler.ReconcilerService._clear_tracker_if_recovered(_service(tracker), node)

        current = tracker.get(node_id) or {"count": 0}
        tracker[node_id] = {"count": current["count"] + 1, "last_attempt": now}

    assert tracker[node_id]["count"] >= reconciler.MAX_REMEDIATION_ATTEMPTS, (
        f"after {reconciler.MAX_REMEDIATION_ATTEMPTS} flap cycles the count is "
        f"{tracker[node_id]['count']} — escalation is unreachable (#14454)"
    )


def test_a_current_heartbeat_does_clear_the_counter():
    """The case the clearing exists for must keep working.

    A node heartbeating right now has genuinely recovered; refusing to clear
    would leave it exhausted and unrepairable, which is the #14344-review bug
    this method was added to prevent.
    """
    tracker = _clear(beat_offset_s=1, last_attempt_offset_s=300, count=3)

    assert tracker is not None, "the entry was deleted rather than reset"
    assert tracker["count"] == 0, "a current heartbeat did not clear the attempt history"


def test_clearing_preserves_the_cooldown():
    """Deleting the whole entry bypassed REMEDIATION_COOLDOWN too.

    `_check_remediation_limits` re-fetches an empty tracker and sees no
    `last_attempt`, so the node becomes immediately remediable again. Only the
    escalation count should be forgiven, not the pacing.
    """
    now = datetime.now(timezone.utc)
    node_id = "node-under-test"
    last_attempt = now - timedelta(seconds=5)
    tracker = {node_id: {"count": 2, "last_attempt": last_attempt}}
    node = SimpleNamespace(node_id=node_id, last_heartbeat=now)

    reconciler.ReconcilerService._clear_tracker_if_recovered(_service(tracker), node)

    assert node_id in tracker, "the tracker entry was deleted, so the cooldown is bypassed"
    assert tracker[node_id]["last_attempt"] == last_attempt, "last_attempt was discarded — cooldown bypassed (#14454)"


def test_a_beat_older_than_the_attempt_is_still_ignored():
    """Unchanged from the original guard, kept pinned."""
    tracker = _clear(beat_offset_s=10, last_attempt_offset_s=5, count=2)

    assert tracker is not None and tracker["count"] == 2, "a beat predating the attempt cleared the counter"
