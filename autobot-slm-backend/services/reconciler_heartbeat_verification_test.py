# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""`_heartbeat_returned` is executed here, not read (#14344).

Its sibling `reconciler_remediation_outcome_test.py` asserts on the AST: which
value `success` is bound to, that the timings are env-backed. Those rules are
about the *shape* of the fix and they cannot see whether the polling loop works.

Review of this PR made the gap concrete: `_heartbeat_returned` rewritten as
``if False: return True`` / ``return False`` — success permanently unreachable,
every node marching to `exhausted` — satisfies every structural rule, because
both constants still appear as returns. So does a reversed comparison.

These drive the real function with a stateful fake session instead. The module's
sqlalchemy and model names are MagicMocks under the package conftest, which is
harmless: `select(Node)` is only handed to the fake, and what is under test is
the loop, the comparison and the timeout.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import ModuleType, SimpleNamespace

_SLM_ROOT = Path(__file__).resolve().parent.parent
if str(_SLM_ROOT) not in sys.path:
    sys.path.insert(0, str(_SLM_ROOT))

# Imported outright rather than via importorskip: a skip would take the guard
# below with it, and "these tests never ran" would read exactly like "these
# tests passed" — which is the failure mode this PR exists to fix, one layer up.
import services.reconciler as reconciler  # noqa: E402


def test_the_module_and_method_are_really_here():
    """Pin what the rules below are actually bound to."""
    assert hasattr(reconciler, "ReconcilerService")
    assert callable(getattr(reconciler.ReconcilerService, "_heartbeat_returned", None))


class _FakeSessions:
    """Yields a session whose query returns the next scripted node row."""

    def __init__(self, beats):
        self._beats = list(beats)
        self.reads = 0

    @asynccontextmanager
    async def session(self):
        yield SimpleNamespace(execute=self._execute)

    async def _execute(self, _query):
        beat = self._beats[self.reads] if self.reads < len(self._beats) else self._beats[-1]
        self.reads += 1
        row = None if beat is _MISSING else SimpleNamespace(last_heartbeat=beat)
        return SimpleNamespace(scalar_one_or_none=lambda: row)


_MISSING = object()


@contextmanager
def _patched(sessions, wait_s, poll_s):
    """Install the fake session factory and shrink the timings.

    `_heartbeat_returned` does `from services.database import db_service` at call
    time, so the module has to exist then. It is created here when absent rather
    than fetched with `.get()` — a None module would raise during setup, and a
    test that dies before exercising anything is not a failing test, it is an
    absent one.
    """
    name = "services.database"
    created = name not in sys.modules
    if created:
        sys.modules[name] = ModuleType(name)
    db_module = sys.modules[name]
    original = getattr(db_module, "db_service", None)
    db_module.db_service = sessions

    prev_wait = reconciler.REMEDIATION_HEARTBEAT_WAIT_S
    prev_poll = reconciler.REMEDIATION_HEARTBEAT_POLL_S
    reconciler.REMEDIATION_HEARTBEAT_WAIT_S = wait_s
    reconciler.REMEDIATION_HEARTBEAT_POLL_S = poll_s
    try:
        yield
    finally:
        reconciler.REMEDIATION_HEARTBEAT_WAIT_S = prev_wait
        reconciler.REMEDIATION_HEARTBEAT_POLL_S = prev_poll
        if created:
            del sys.modules[name]
        else:
            db_module.db_service = original


def _run(beats, wait_s=5, poll_s=0, restarted_at=None):
    """Execute the real `_heartbeat_returned` against a scripted heartbeat series."""
    restarted_at = restarted_at or datetime.now(timezone.utc)
    sessions = _FakeSessions(beats)

    with _patched(sessions, wait_s, poll_s):
        node = SimpleNamespace(node_id="node-under-test", last_heartbeat=None)
        result = asyncio.run(
            reconciler.ReconcilerService._heartbeat_returned(SimpleNamespace(), node, restarted_at)
        )

    return result, sessions.reads


def test_a_heartbeat_after_the_restart_is_success():
    """The whole point: the agent came back."""
    later = datetime.now(timezone.utc) + timedelta(seconds=30)
    verified, reads = _run([None, None, later])

    assert verified is True, "a heartbeat newer than the restart was not counted as success"
    assert reads >= 3, f"returned after {reads} reads — it did not actually poll for the later beat"


def test_no_heartbeat_is_a_failure_and_the_loop_ends():
    """Returning True on timeout is the original bug, restated.

    Success resets the attempt counter, so a verification that cannot fail
    leaves remediation unable to ever reach MAX_REMEDIATION_ATTEMPTS.
    """
    verified, reads = _run([None] * 50, wait_s=0.05)

    assert verified is False, "a node that never heartbeated was reported as remediated"
    assert reads >= 1, "the window expired without the row being read even once"


def test_a_heartbeat_older_than_the_restart_is_not_success():
    """The reversed-comparison mutation.

    A stale timestamp from before the restart is exactly what a node stuck in
    the #14350 401 loop has — it heartbeated successfully once, at enrollment.
    """
    stale = datetime.now(timezone.utc) - timedelta(hours=6)
    verified, _ = _run([stale] * 20, wait_s=0.05)

    assert verified is False, "a heartbeat predating the restart was accepted as proof of recovery"


def test_a_heartbeat_exactly_at_the_restart_is_not_success():
    """`>` not `>=`: the beat has to be strictly after the restart."""
    now = datetime.now(timezone.utc)
    verified, _ = _run([now] * 20, wait_s=0.05, restarted_at=now)

    assert verified is False, "a heartbeat at the exact restart instant was treated as a later one"


def test_a_missing_node_row_is_a_failure_not_a_crash():
    """A deleted or not-yet-visible row must fail the verification quietly.

    An exception here would propagate out of `_remediate_node` and abort the
    whole reconciliation pass for every remaining node.
    """
    verified, _ = _run([_MISSING] * 20, wait_s=0.05)

    assert verified is False, "a missing node row did not fail verification"
